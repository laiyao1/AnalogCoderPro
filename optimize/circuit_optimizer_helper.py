"""Bayesian device sizing with isolated ngspice trials and Optuna TPE sampling.

Circuit modules supply a factory, initial parameter values, and search bounds.
The CLI runs independent optimization studies and exports the winning circuit.
"""

import argparse
import importlib.util
import json
import logging
import multiprocessing as mp
import os
import pickle
import sys
import tempfile
import time
import traceback
from datetime import datetime
from functools import partial
from pathlib import Path
from queue import Empty

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import optuna
from PySpice.Unit import u_GHz, u_Hz

optuna.logging.set_verbosity(optuna.logging.WARNING)

SIMULATION_TIMEOUT_SECONDS = 20
AC_INPUT_AMPLITUDE = 1e-9


def load_optimizer(optimize_file_path):
    """Load and validate a parameterized circuit module."""
    if not os.path.exists(optimize_file_path):
        raise FileNotFoundError(f"Optimize file does not exist: {optimize_file_path}")

    optimize_file_path = Path(optimize_file_path).resolve()
    # Generated modules use `from model import ...`; support both adjacent models
    # and the canonical model shipped with this repository.
    for directory in (
        Path(__file__).resolve().parents[1] / "mosfet_model",
        optimize_file_path.parent,
    ):
        sys.path.insert(0, str(directory))
    module_name = optimize_file_path.stem

    spec = importlib.util.spec_from_file_location(module_name, optimize_file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    validate_parameters(module.initial_params, module.param_ranges_definition)
    return module.create_circuit, module.initial_params, module.param_ranges_definition


def validate_parameters(initial_params, ranges):
    """Reject malformed generated search spaces before starting simulations."""
    if not ranges or set(initial_params) != set(ranges):
        raise ValueError(
            "initial_params and param_ranges_definition must have the same nonempty keys"
        )
    for name, bounds in ranges.items():
        low, high, initial = (
            float(bounds["min"]),
            float(bounds["max"]),
            float(initial_params[name]),
        )
        if not all(np.isfinite(value) for value in (low, high, initial)):
            raise ValueError(f"{name}: bounds and initial value must be finite")
        if not low <= initial <= high:
            raise ValueError(
                f"{name}: initial value {initial} is outside [{low}, {high}]"
            )
        if bounds.get("log", False) and low <= 0:
            raise ValueError(f"{name}: logarithmic bounds must be positive")


def result_path(file_path, suffix):
    """Keep output names distinct, including inputs not ending in optimize.py."""
    path = Path(file_path)
    stem = path.stem
    if stem.endswith("_optimize"):
        stem = stem[: -len("_optimize")]
    elif stem == "optimize":
        stem = "circuit"
    return path.with_name(f"{stem}_{suffix}")


def find_dc_operating_point(simulator, v_name, circuit=None):
    """Search coarse-to-fine input biases for an output near half the supply."""
    is_opamp = "Vinn" in circuit.element_names if circuit is not None else False

    if is_opamp and circuit is not None:
        inp_node = "Vinp"
        inn_node = "Vinn"

        if "Vinp" not in circuit.element_names or "Vinn" not in circuit.element_names:
            potential_pairs = [
                ["Vinp", "Vinn"],
                ["VINP", "VINN"],
                ["Vin+", "Vin-"],
                ["Inp", "Inn"],
                ["IN+", "IN-"],
                ["Vp", "Vn"],
            ]

            for pair in potential_pairs:
                if (
                    pair[0] in circuit.element_names
                    and pair[1] in circuit.element_names
                ):
                    inp_node = pair[0]
                    inn_node = pair[1]
                    break

        try:
            circuit.V("short", inp_node, inn_node, 0)
            print(
                f"Added short between {inp_node} and {inn_node} for op-amp DC analysis"
            )
            for element in circuit.elements:
                if element.name.lower() in ["vinn", "vin-", "inn", "in-", "vn"]:
                    vinn_name = element.name
                    break
            delete_name = vinn_name
            delete_pin1 = circuit.element(vinn_name).pins[0].node
            delete_pin2 = circuit.element(vinn_name).pins[1].node
            delete_dc_value = circuit.element(vinn_name).dc_value
            circuit.element(vinn_name).detach()
            simulator = circuit.simulator()
        except Exception as e:
            raise RuntimeError(
                "Failed to connect differential inputs for DC analysis"
            ) from e

    v_dd_value = 1.2

    if circuit is not None:
        try:
            for vdd_name in ["Vdd", "VDD", "vdd", "vcc", "VCC"]:
                try:
                    if vdd_name in circuit.element_names:
                        dc_value = circuit.element(vdd_name).dc_value
                        if dc_value is not None:
                            if isinstance(dc_value, str):
                                v_dd_value = float(dc_value.split()[0])
                            else:
                                v_dd_value = float(dc_value)
                            break
                except Exception:
                    continue
        except Exception as e:
            print(f"Cannot determine VDD value, using default 1.2V: {e}")

    initial_vin = v_dd_value / 2
    target_vout = v_dd_value / 2

    min_voltage = 0.3
    max_voltage = v_dd_value - 0.3

    search_scales = [
        {
            "name": "coarse",
            "range": [min_voltage, max_voltage],
            "step": (max_voltage - min_voltage) / 20,
        },
        {
            "name": "medium",
            "range_size": (max_voltage - min_voltage) / 4,
            "step": (max_voltage - min_voltage) / 200,
        },
        {
            "name": "fine",
            "range_size": (max_voltage - min_voltage) / 40,
            "step": (max_voltage - min_voltage) / 2000,
        },
    ]

    best_vin = initial_vin
    best_diff = float("inf")

    print(f"Looking for DC operating point for {'op-amp' if is_opamp else 'amplifier'}")

    for i, scale in enumerate(search_scales):
        try:
            if i == 0:
                v_min, v_max = scale["range"]
            else:
                half_range = scale["range_size"] / 2
                v_min = max(min_voltage, best_vin - half_range)
                v_max = min(max_voltage, best_vin + half_range)

            dc_analysis = simulator.dc(**{v_name: slice(v_min, v_max, scale["step"])})

            vout_values = dc_analysis["Vout"].as_ndarray()
            vin_values = dc_analysis[v_name].as_ndarray()

            current_best_vin = best_vin
            current_best_diff = float("inf")

            for j, vout in enumerate(vout_values):
                diff = abs(float(vout) - target_vout)

                if diff < current_best_diff:
                    current_best_diff = diff
                    current_best_vin = float(vin_values[j])
                elif abs(diff - current_best_diff) < 1e-6:
                    if abs(float(vin_values[j]) - target_vout) < abs(
                        current_best_vin - target_vout
                    ):
                        current_best_vin = float(vin_values[j])

            best_vin = current_best_vin
            best_diff = current_best_diff

            print(
                f"{scale['name']} scan: Vin ≈ {best_vin:.6f}V with Vout diff = {best_diff:.6f}V"
            )

        except Exception as e:
            print(f"DC {scale['name']} analysis failed: {e}")
            traceback.print_exc()

    if circuit is not None and "Vshort" in circuit.element_names:
        try:
            circuit.element("Vshort").detach()
            circuit.V(delete_name[1:], delete_pin1, delete_pin2, delete_dc_value)
            print("Removed short circuit for op-amp DC analysis")
        except Exception as e:
            print(f"Failed to remove short circuit: {e}")

    return best_vin


def evaluate_circuit(circuit, optimization_target="gain", logger=None):
    """Measure gain, unity gain frequency, and power using benchmark conventions."""
    if "Vinn" in circuit.element_names:
        circuit_type = "opamp"
    else:
        circuit_type = "amplifier"

    print(f"Detected circuit type: {circuit_type}")

    minimum_value = _failure_score(optimization_target)

    if optimization_target == "gbw" or optimization_target == "fom":
        for element in circuit.elements:
            if element.name.lower() in ["cload", "cl"]:
                delete_name = element.name
                circuit.element(delete_name).detach()
                break

        if optimization_target == "gbw":
            circuit.C("load", "Vout", circuit.gnd, "10p")
        else:
            circuit.C("load", "Vout", circuit.gnd, "100p")

    try:
        simulator = circuit.simulator(temp=25)
        dc_analysis = simulator.operating_point()

        dc_value = circuit.element("Vdd").dc_value
        assert dc_value == 1.2, "Vdd value should be 1.2V"

        if type(dc_value) == str:
            v_dd_value = float(dc_value.split()[0])
        else:
            v_dd_value = float(dc_value)

        assert v_dd_value > 0, "Vdd value should be greater than 0"

        power = 0
        for element in circuit.elements:
            if element.name.startswith("V") and hasattr(element, "dc_value"):
                source_name = element.name.lower()

                if source_name in dc_analysis.branches:
                    current = float(dc_analysis.branches[source_name])
                    if type(element.dc_value) == str:
                        if element.dc_value.startswith("dc"):
                            voltage = float(element.dc_value.split()[1])
                        else:
                            voltage = float(element.dc_value.split()[0])
                    else:
                        voltage = float(element.dc_value)

                    this_power = voltage * abs(current)
                    power += this_power

        assert power > 0, "Power consumption should be greater than 0"

        if optimization_target == "fom":
            c_load = 100
        elif optimization_target == "gbw":
            c_load = 10
        else:
            c_load = None

        ac_analysis = simulator.ac(
            start_frequency=1 @ u_Hz,
            stop_frequency=10 @ u_GHz,
            number_of_points=100,
            variation="dec",
        )
        output = ac_analysis["vout"].as_ndarray()
        if circuit_type == "amplifier" and np.abs(output[0]) < 1e-30:
            return minimum_value, {}
        frequency = ac_analysis.frequency.as_ndarray()
        gain_db = 20 * np.log10(np.abs(output / AC_INPUT_AMPLITUDE))

        dc_gain = gain_db[0]

        if logger is not None:
            plt.figure(figsize=(10, 6))
            plt.semilogx(frequency, gain_db)
            plt.grid(True)
            plt.xlabel("Frequency (Hz)")
            plt.ylabel("Gain (dB)")
            plt.title(f"{circuit_type.capitalize()} Frequency Response")
            plt.axhline(y=dc_gain - 3, color="r", linestyle="--", label="-3dB point")
            plt.legend()
            plt.tight_layout()
            plt.savefig(f"{circuit_type}_gain_plot.png")
            plt.close()

        linear_gain = 10 ** (dc_gain / 20)

        # The benchmark defines GBW as the first downward unity gain crossing.
        unity_gain_index = None
        for i in range(len(gain_db) - 1):
            if gain_db[i] >= 0 and gain_db[i + 1] < 0:
                unity_gain_index = i
                break

        if unity_gain_index is not None:
            f1, f2 = frequency[unity_gain_index], frequency[unity_gain_index + 1]
            g1, g2 = gain_db[unity_gain_index], gain_db[unity_gain_index + 1]
            unity_gain_frequency = f1 + (f2 - f1) * (0 - g1) / (g2 - g1)
        else:
            # Preserve the original upper-frequency fallback for comparisons.
            unity_gain_frequency = frequency[-1]

        gbw = unity_gain_frequency
        power_mw = power * 1e3

        penalty = 1e-9 if linear_gain < 1 else 1
        if optimization_target == "gain":
            reward = dc_gain
            message = (
                f"{circuit_type.capitalize()} Gain: {dc_gain:.4f} dB, GBW: {gbw:.4f} Hz"
            )
        elif optimization_target == "gbw":
            reward = penalty * gbw * 1e-6
            message = (
                f"{circuit_type.capitalize()} GBW: {reward:.4f} MHz, "
                f"Gain: {dc_gain:.4f} dB, GBW: {gbw:.4f} Hz"
            )
        else:
            reward = penalty * gbw * 1e-6 * c_load / (power * 1e3)
            message = (
                f"{circuit_type.capitalize()} FOM: {reward:.4f} MHz*pF/mW, "
                f"Gain: {dc_gain:.4f} dB, GBW: {gbw:.4f} Hz, "
                f"Power: {power_mw:.4f} mW, Load: {c_load} pF"
            )
        print(message)
        if logger is not None:
            logger.info(message)

        info = {
            "gain": dc_gain,
            "gbw": gbw,
            "power": power_mw,
            "fom": reward,
            "load": c_load,
        }

        return reward, info

    except Exception as e:
        print(f"Evaluation fail: {e}")
        traceback.print_exc()
        info = {"gain": None, "gbw": None, "power": None, "fom": None, "load": 100}
        return minimum_value, info


def set_circuit_bias(circuit, v_name, best_vin):
    """Apply the selected DC bias and a 1nV single-ended or differential AC input."""
    is_opamp = "Vinn" in circuit.element_names

    if is_opamp:
        inp_node = ""
        inn_node = ""

        for element in circuit.elements:
            if element.name.lower().startswith("v"):
                pin_nodes = [str(pin.node).lower() for pin in element.pins]
                if "vinp" in pin_nodes or "vin+" in pin_nodes or "in+" in pin_nodes:
                    inp_node = element.name
                elif "vinn" in pin_nodes or "vin-" in pin_nodes or "in-" in pin_nodes:
                    inn_node = element.name

        if not inp_node or not inn_node:
            potential_pin_names = [
                ["vinp", "vinn"],
                ["vin+", "vin-"],
                ["in+", "in-"],
                ["vp", "vn"],
                ["inp", "inn"],
            ]

            for element in circuit.elements:
                if element.name.lower().startswith("v"):
                    pin_nodes = [str(pin.node).lower() for pin in element.pins]
                    for pair in potential_pin_names:
                        if pair[0] in pin_nodes and not inp_node:
                            inp_node = element.name
                        if pair[1] in pin_nodes and not inn_node:
                            inn_node = element.name

        circuit.element(inp_node).dc_value = f"dc {best_vin:.4f} ac 0.5n"

        circuit.element(inn_node).dc_value = f"dc {best_vin:.4f} ac -0.5n"

        print(
            f"Set op-amp bias: {inp_node}={best_vin:.4f}V, {inn_node}={best_vin:.4f}V (diff mode for AC)"
        )
    else:
        circuit.element(v_name).dc_value = f"dc {best_vin:.4f} ac 1n"

        print(f"Set amplifier bias: {v_name}={best_vin:.4f}V")

    return circuit


def _failure_score(optimization_target):
    """Return the benchmark penalty for failed simulations."""
    if optimization_target not in {"gain", "gbw", "fom"}:
        raise ValueError(f"Unsupported optimization target: {optimization_target}")
    return -500 if optimization_target == "gain" else -10


def _find_input_source(circuit):
    """Find the benchmark's single-ended or positive differential input source."""
    return next(
        (
            element.name
            for element in circuit.elements
            if element.name.lower() in {"vin", "vinp"}
        ),
        None,
    )


def _run_simulation(params, result_queue, create_circuit, optimization_target, logger):
    """Simulate one candidate in a temporary working directory inside the child."""
    original_dir = os.getcwd()
    try:
        with tempfile.TemporaryDirectory(prefix=f"pyspice_{os.getpid()}_") as directory:
            try:
                os.chdir(directory)
                circuit = create_circuit(params)
                v_name = _find_input_source(circuit)
                if v_name is None:
                    raise ValueError("Cannot find input voltage source")
                best_vin = find_dc_operating_point(circuit.simulator(), v_name, circuit)
                circuit = set_circuit_bias(circuit, v_name, best_vin)
                reward, _ = evaluate_circuit(circuit, optimization_target, logger)
                result_queue.put(("success", reward))
            finally:
                os.chdir(original_dir)
    except Exception as error:
        result_queue.put(("error", str(error)))


def objective(
    trial,
    create_circuit,
    params_ranges_definition,
    optimization_target="gain",
    custom_logger=None,
):
    """Sample parameters and evaluate them in a process isolated from ngspice crashes."""
    minimum_value = _failure_score(optimization_target)

    params = {}
    for param_name, range_info in params_ranges_definition.items():
        params[param_name] = trial.suggest_float(
            param_name,
            range_info["min"],
            range_info["max"],
            log=range_info.get("log", False),
        )

    print(f"Trial {trial.number} - Testing parameters: {params}")

    result_queue = mp.Queue()
    sim_process = mp.Process(
        target=_run_simulation,
        args=(params, result_queue, create_circuit, optimization_target, custom_logger),
    )

    sim_process.start()
    sim_process.join(timeout=SIMULATION_TIMEOUT_SECONDS)

    if sim_process.is_alive():
        print(f"Trial {trial.number} - TIMEOUT: Simulation took too long, terminating")
        sim_process.terminate()
        sim_process.join()
        return minimum_value

    try:
        status, result = result_queue.get(timeout=1)
        if status == "success":
            print(f"Trial {trial.number} - SUCCESS: Result = {result}")
            return result
        else:
            print(f"Trial {trial.number} - ERROR: {result}")
            return minimum_value
    except Empty:
        print(
            f"Trial {trial.number} - CRASHED: Process terminated abnormally (segmentation fault)"
        )
        return minimum_value


def plot_optimization_results(study):
    """Save the optimization history and parameter importance plots."""
    try:
        importances = optuna.importance.get_param_importances(study)
        print("\nParameter importance:")
        for key, value in importances.items():
            print(f"    {key}: {value:.3f}")
    except Exception:
        print("Cannot get parameter importance.")

    plt.figure(figsize=(10, 6))
    optuna.visualization.matplotlib.plot_optimization_history(study)
    plt.tight_layout()
    plt.savefig("optimization_history.png")
    plt.close()

    plt.figure(figsize=(10, 6))
    optuna.visualization.matplotlib.plot_param_importances(study)
    plt.tight_layout()
    plt.savefig("param_importance.png")
    plt.close()


def run_optimization(
    n_trials,
    create_circuit,
    params_ranges_definition,
    initial_params,
    optimization_target="gain",
    n_jobs=8,
    file_path=None,
    sampler_seed=42,
):
    """Evaluate the baseline, run one TPE study, and return its results and timing."""
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    validate_parameters(initial_params, params_ranges_definition)
    n_params = len(params_ranges_definition)
    n_startup = int(n_trials * 0.25)

    study_kwargs = {
        "direction": "maximize",
        "sampler": optuna.samplers.TPESampler(
            seed=sampler_seed,
            n_startup_trials=n_startup,
            multivariate=True,
            consider_prior=True,
            prior_weight=1.0,
            n_ei_candidates=24,
            constant_liar=True,
        ),
        "study_name": "amplifier_optimization",
    }

    study = optuna.create_study(**study_kwargs)

    log_file = f"optuna_log_{timestamp}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    optuna_logger = optuna.logging.get_logger("optuna")
    optuna_logger.addHandler(file_handler)
    optuna.logging.set_verbosity(optuna.logging.INFO)

    custom_logger = logging.getLogger("circuit_optimization")
    custom_logger.setLevel(logging.INFO)
    custom_logger.addHandler(file_handler)
    custom_logger.propagate = False

    custom_logger.info(f"===== Optimization started at {timestamp} =====")
    custom_logger.info(
        f"Parameters: n_trials={n_trials}, n_jobs={n_jobs}, optimization_target={optimization_target}"
    )
    custom_logger.info(f"Parameter space dimension: {n_params}")

    # Report the baseline separately; the study contains sampled trials only.
    init_eval_start = time.time()
    circuit = create_circuit(initial_params)

    v_name = _find_input_source(circuit)

    if v_name is None:
        custom_logger.warning("No input voltage source found, using default evaluation")
        initial_value = -10
        info = {}
    else:
        simulator = circuit.simulator()
        best_vin = find_dc_operating_point(simulator, v_name, circuit)
        circuit = set_circuit_bias(circuit, v_name, best_vin)
        initial_value, info = evaluate_circuit(
            circuit, optimization_target=optimization_target, logger=custom_logger
        )

    init_eval_time = time.time() - init_eval_start
    custom_logger.info(
        f"Initial parameter evaluation completed in {init_eval_time:.4f} seconds"
    )
    custom_logger.info(f"Initial parameter performance: {initial_value}")

    if file_path:
        initial_file_path = result_path(file_path, "initial_params.txt")
        with open(initial_file_path, "w") as f:
            f.write("Initial parameters:\n")
            for key, value in initial_params.items():
                f.write(f"{key}: {value}\n")
            f.write(f"Initial performance: {initial_value}\n")
            f.write("Info:\n")
            for key, value in info.items():
                f.write(f"{key}: {value}\n")

    print(f"Log file: {log_file}")

    def log_trial_completion(study, trial):
        if trial.datetime_start is not None and trial.datetime_complete is not None:
            duration = (trial.datetime_complete - trial.datetime_start).total_seconds()
            custom_logger.info(
                "Trial %s completed in %.4f seconds with value: %s",
                trial.number,
                duration,
                trial.value,
            )

    objective_with_params = partial(
        objective,
        create_circuit=create_circuit,
        params_ranges_definition=params_ranges_definition,
        optimization_target=optimization_target,
    )

    optim_start = time.time()
    custom_logger.info(
        f"Starting optimization with {n_trials} trials using {n_jobs} parallel jobs"
    )

    study.optimize(
        objective_with_params,
        n_trials=n_trials,
        n_jobs=n_jobs,
        callbacks=[log_trial_completion],
    )

    optim_time = time.time() - optim_start
    total_time = time.time() - start_time

    custom_logger.info(f"===== Optimization completed =====")
    custom_logger.info(
        f"Optimization process took {optim_time:.4f} seconds ({optim_time/60:.4f} minutes)"
    )
    custom_logger.info(
        f"Total execution time: {total_time:.4f} seconds ({total_time/60:.4f} minutes)"
    )
    custom_logger.info(f"Best value: {study.best_value}")
    custom_logger.info(f"Best parameters: {study.best_params}")

    print(
        f"Optimization completed in {optim_time:.4f} seconds ({optim_time/60:.4f} minutes)"
    )
    print(
        f"Total execution time: {total_time:.4f} seconds ({total_time/60:.4f} minutes)"
    )
    print(f"Results saved to {log_file}")

    optuna_logger.removeHandler(file_handler)
    custom_logger.removeHandler(file_handler)
    file_handler.close()
    return study, custom_logger, initial_value, info, total_time


def plot_multiple_runs(all_results, optimization_target="fom"):
    """Plot the cumulative best completed score for each independent run."""
    plt.figure(figsize=(12, 6))

    for i, study in enumerate(all_results["studies"]):
        # Failed or unfinished trials do not contribute to the history.
        trials = [
            t.value for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE
        ]

        # All supported objectives are maximized.
        cumulative_best = []
        current_best = float("-inf")
        for value in trials:
            current_best = max(current_best, value)
            cumulative_best.append(current_best)

        plt.plot(cumulative_best, alpha=0.6, label=f"Run {i+1}")

    plt.xlabel("Trial Number")
    plt.ylabel(f"Best {optimization_target.upper()} So Far")
    plt.title("Optimization History - Multiple Runs (Cumulative Best)")
    plt.legend()
    plt.grid(True)
    plt.savefig("multiple_runs_history.png", dpi=300, bbox_inches="tight")
    plt.close("all")


def run_multiple_optimizations(
    n_runs,
    n_trials,
    create_circuit,
    params_ranges_definition,
    initial_params,
    optimization_target="gain",
    n_jobs=8,
    file_path=None,
):
    """Run independently seeded studies and report aggregate performance."""

    print(f"\n{'='*80}")
    print(f"Starting {n_runs} optimization runs")
    print(f"{'='*80}\n")

    all_results = {
        "best_values": [],
        "best_params_list": [],
        "run_times": [],
        "initial_value": None,
        "initial_info": None,
        "studies": [],
    }

    for run_idx in range(n_runs):
        print(f"\n{'='*80}")
        print(f"Run {run_idx + 1}/{n_runs}")
        print(f"{'='*80}\n")

        if file_path:
            run_file_path = result_path(file_path, f"run{run_idx + 1}.py")
        else:
            run_file_path = None

        study, _, initial_value, initial_info, run_time = run_optimization(
            n_trials=n_trials,
            create_circuit=create_circuit,
            params_ranges_definition=params_ranges_definition,
            initial_params=initial_params,
            optimization_target=optimization_target,
            n_jobs=n_jobs,
            file_path=run_file_path,
            sampler_seed=42 + run_idx,
        )

        if run_idx == 0:
            all_results["initial_value"] = initial_value
            all_results["initial_info"] = initial_info

        all_results["best_values"].append(study.best_value)
        all_results["best_params_list"].append(study.best_params)
        all_results["run_times"].append(run_time)
        all_results["studies"].append(study)

        print(f"\nRun {run_idx + 1} completed:")
        print(f"  Best value: {study.best_value:.6f}")
        print(f"  Run time: {run_time:.2f} seconds ({run_time/60:.2f} minutes)")

    best_values_array = np.array(all_results["best_values"])
    run_times_array = np.array(all_results["run_times"])

    statistics = {
        "best_value_mean": np.mean(best_values_array),
        "best_value_std": np.std(best_values_array),
        "best_value_min": np.min(best_values_array),
        "best_value_max": np.max(best_values_array),
        "run_time_mean": np.mean(run_times_array),
        "run_time_std": np.std(run_times_array),
        "run_time_min": np.min(run_times_array),
        "run_time_max": np.max(run_times_array),
    }

    all_results["statistics"] = statistics

    print(f"\n{'='*80}")
    print(f"SUMMARY REPORT ({n_runs} runs)")
    print(f"{'='*80}\n")

    print("Initial Performance:")
    print(f"  Value: {all_results['initial_value']:.6f}")
    if all_results["initial_info"]:
        for key, value in all_results["initial_info"].items():
            print(f"  {key}: {value}")

    print("\nOptimization Results:")
    print(
        f"  Best Value (Mean ± Std): {statistics['best_value_mean']:.6f} ± {statistics['best_value_std']:.6f}"
    )
    print(
        f"  Best Value Range: [{statistics['best_value_min']:.6f}, {statistics['best_value_max']:.6f}]"
    )
    print(
        f"  Improvement over Initial: {statistics['best_value_mean'] - all_results['initial_value']:.6f}"
    )
    if abs(all_results["initial_value"]) > 1e-10:
        print(
            f"  Improvement Percentage: {((statistics['best_value_mean'] - all_results['initial_value']) / abs(all_results['initial_value']) * 100):.2f}%"
        )

    print("\nRun Time Statistics:")
    print(
        f"  Mean ± Std: {statistics['run_time_mean']:.2f} ± {statistics['run_time_std']:.2f} seconds"
    )
    print(
        f"  Mean ± Std: {statistics['run_time_mean']/60:.2f} ± {statistics['run_time_std']/60:.2f} minutes"
    )
    print(
        f"  Range: [{statistics['run_time_min']:.2f}, {statistics['run_time_max']:.2f}] seconds"
    )
    print(
        f"  Total Time: {np.sum(run_times_array):.2f} seconds ({np.sum(run_times_array)/60:.2f} minutes)"
    )

    print("\nIndividual Run Results:")
    for i, (value, time_taken) in enumerate(
        zip(all_results["best_values"], all_results["run_times"])
    ):
        print(
            f"  Run {i+1}: Value = {value:.6f}, Time = {time_taken:.2f}s ({time_taken/60:.2f}min)"
        )

    if file_path:
        summary_file = result_path(file_path, "multi_run_summary.json")
        summary_data = {
            "n_runs": n_runs,
            "optimization_target": optimization_target,
            "initial_value": all_results["initial_value"],
            "initial_info": all_results["initial_info"],
            "statistics": statistics,
            "individual_runs": [
                {
                    "run": i + 1,
                    "best_value": all_results["best_values"][i],
                    "best_params": all_results["best_params_list"][i],
                    "run_time": all_results["run_times"][i],
                }
                for i in range(n_runs)
            ],
        }

        with open(summary_file, "w") as f:
            json.dump(summary_data, f, indent=4)

        print(f"\nSummary saved to: {summary_file}")

    print(f"\n{'='*80}\n")

    return all_results


def main(argv=None):
    """Parse CLI options, run sizing, and export the best study and netlist."""
    parser = argparse.ArgumentParser(
        description="Bayesian device sizing with Optuna and PySpice"
    )
    parser.add_argument("path", type=Path, help="parameterized circuit Python file")
    parser.add_argument(
        "target", nargs="?", choices=("gain", "gbw", "fom"), default="gain"
    )
    parser.add_argument("n_runs", nargs="?", type=int, default=1)
    parser.add_argument("--n-trials", type=int, default=1000)
    parser.add_argument("--n-jobs", type=int, default=16)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="results directory (default: directory containing the input)",
    )
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    if args.n_runs < 1 or args.n_trials < 1 or args.n_jobs < 1:
        parser.error("n_runs, --n-trials, and --n-jobs must be positive")
    file_path = args.path.resolve()
    if not file_path.is_file():
        parser.error(f"Circuit file does not exist: {file_path}")
    output_dir = (args.output_dir or file_path.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    create_circuit, initial_params, params_ranges_definition = load_optimizer(file_path)
    print(f"Successfully loaded: {file_path}")
    # Use absolute paths before changing directory. Generated modules and model
    # imports remain available to the isolated simulation processes.
    file_path = str(output_dir / file_path.name)
    os.chdir(output_dir)
    target, n_runs = args.target, args.n_runs
    mp.set_start_method("fork", force=True)

    all_results = run_multiple_optimizations(
        n_runs=n_runs,
        n_trials=args.n_trials,
        create_circuit=create_circuit,
        params_ranges_definition=params_ranges_definition,
        initial_params=initial_params,
        optimization_target=target,
        n_jobs=args.n_jobs,
        file_path=file_path,
    )

    best_run_idx = np.argmax(all_results["best_values"])
    best_study = all_results["studies"][best_run_idx]
    best_trial = best_study.best_trial

    print(f"\nBest overall result from Run {best_run_idx + 1}:")
    print(f"  Value: {best_trial.value:.6f}")
    print("  Params:")
    for key, value in best_trial.params.items():
        print(f"    {key}: {value}")

    best_params = best_trial.params
    best_circuit = create_circuit(best_params)
    simulator = best_circuit.simulator()

    v_name = _find_input_source(best_circuit)
    if v_name is None:
        raise ValueError("Cannot find input voltage source in the best circuit")

    best_vin = find_dc_operating_point(simulator, v_name, best_circuit)
    best_circuit = set_circuit_bias(best_circuit, v_name, best_vin)
    _, info = evaluate_circuit(best_circuit, optimization_target=target, logger=None)

    save_log_path = result_path(file_path, "best_overall_result.txt")
    with open(save_log_path, "w") as f:
        f.write(f"Best result from {n_runs} runs:\n")
        f.write(f"From Run: {best_run_idx + 1}\n")
        f.write(f"Value: {best_trial.value:.6f}\n\n")
        f.write("Params:\n")
        for key, value in best_trial.params.items():
            f.write(f"{key}: {value}\n")
        f.write("\nDetailed Info:\n")
        for key, value in info.items():
            f.write(f"{key}: {value}\n")

    circuit_save_path = result_path(file_path, "best_overall_circuit.cir")
    with open(circuit_save_path, "w") as f:
        f.write(str(best_circuit))

    with open("best_optuna_study.pkl", "wb") as f:
        pickle.dump(best_study, f)

    print("\nOptimization completed.")
    print(f"Best result saved to: {save_log_path}")
    print(f"Best circuit saved to: {circuit_save_path}")

    if not args.no_plots:
        plot_multiple_runs(all_results, target)


if __name__ == "__main__":
    main()
