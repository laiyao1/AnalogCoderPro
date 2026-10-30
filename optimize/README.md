# Bayesian device sizing

This directory contains the Optuna TPE sizing stage used after circuit topology
generation. The optimizer searches transistor widths, bias voltages, resistances,
and compensation capacitances while keeping the topology fixed. Each candidate
receives a DC bias search and an AC simulation through PySpice/ngspice.

The implementation and 45nm models were collected from the development
`AnalogCoder-pro` repository. The examples are parameterized circuits generated
for tasks 59 and 60. The amplifier example's load is fixed to match the current
parameterization prompt. Experiment logs, duplicate helpers, and cached studies
are not required to run the optimizer.

## Installation

Use Python 3.10 or later on macOS or Linux. Simulation trials use `fork` to isolate
ngspice crashes, so this implementation does not support native Windows.
Install ngspice **with its shared library**, then the Python dependencies:

```bash
conda create -n analog python=3.10
conda activate analog
conda install -c conda-forge ngspice pyspice
pip install -r requirements-sizing.txt
```

If PySpice cannot locate `libngspice.dylib` on macOS, add the directory containing
that library to `DYLD_LIBRARY_PATH` before starting Python (for example,
`export DYLD_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_LIBRARY_PATH:-}"` for Homebrew).

Run commands below from the repository root. Standalone sizing does not call an
LLM and needs no API key.

## Optimize an existing circuit

Start with a small local run:

```bash
python optimize/circuit_optimizer_helper.py \
  optimize/examples/amplifier_optimize.py fom 1 \
  --n-trials 10 --n-jobs 1 --output-dir results/amplifier

python optimize/circuit_optimizer_helper.py \
  optimize/examples/opamp_optimize.py gain 1 \
  --n-trials 10 --n-jobs 1 --output-dir results/opamp
```

The positional arguments are the circuit module, objective (`gain`, `gbw`, or
`fom`), and number of independent runs. Defaults are `gain`, one run, 1000 trials
per run, and 16 parallel jobs. Use `--n-jobs 1` for a light initial check;
`--no-plots` skips the final optimization history plot. Plots use a noninteractive
backend and never block waiting for a window to close.

A circuit module must export:

```python
def create_circuit(params):
    ...  # return a PySpice Circuit

initial_params = {"width": 10e-6}
param_ranges_definition = {
    "width": {"min": 45e-9, "max": 22.5e-6, "log": True},
}
```

The dictionaries must have identical nonempty keys, finite bounds, and initial
values inside the ranges. Logarithmic ranges must be positive. The loader makes
the module's directory and `mosfet_model/` available for `from model import
nmos_params, pmos_params`.

Follow `optimize_template.md` when parameterizing new circuits: keep VDD at 1.2V,
keep transistor lengths and load capacitances fixed, and preserve original
parameter values in `initial_params`. Name the supply source `Vdd`, the input
source `Vin` (amplifier) or `Vinp`/`Vinn` (op-amp), and the output node `Vout`.
The evaluator identifies the circuit type and finds its DC bias using these
names. Custom model files should live beside the input module; relative SPICE
include paths should be replaced with absolute paths because trials run in
temporary directories.

## Objectives and benchmark tasks

| Tasks | Objective | Returned score | Output load |
| --- | --- | --- | --- |
| 51–54 | Voltage gain | DC gain in dB | Circuit's original load |
| 55–58 | GBW | Unity gain frequency in MHz | 10 pF |
| 59–62 | FoM | GBW (MHz) × load (pF) / power (mW) | 100 pF |
| 63–66 | FoM, topology-only prompt ablation | Same FoM | 100 pF |

The helper retains the development implementation's definition of GBW as the
first downward unity gain crossing in the sampled AC response (1Hz to 10GHz).
If no crossing is found, it uses the final sampled frequency. GBW/FoM apply the
original penalty when DC linear gain is below one. These conventions matter
when comparing results with another circuit evaluator. Failed simulations receive
penalty scores (`-500` for gain, `-10` for GBW/FoM); inspect logs before interpreting
an optimization as a valid circuit result. Short smoke runs validate execution;
they are not a reproduction of the paper's performance measurements.

## Generate and size a new topology

The existing `run.py` invokes sizing automatically after an optimization task's
generated circuit passes the function check. Configure the LLM via environment
variables or the existing `--api_key`/`--base_url` arguments:

```bash
export OPENAI_API_KEY="your-key"
# Optional: export OPENAI_BASE_URL="your-provider-endpoint"
python run.py --task_id=59 --num_per_task=1 --model=gpt-5-mini \
  --sizing-trials=1000 --sizing-jobs=16 --sizing-runs=1
```

This workflow makes model API calls. It writes the parameterization prompt,
answer, and `*_optimize.py` beside the generated topology, then launches the
canonical optimizer with the same Python interpreter. Optimization failures are
reported through the subprocess exit status.

## Results

For an input named `amplifier_optimize.py`, the output directory contains:

- `amplifier_runN_initial_params.txt`: baseline parameters and measurements for each run.
- `amplifier_multi_run_summary.json`: independent runs, best parameters, and aggregate statistics.
- `amplifier_best_overall_result.txt`: winning parameters and measured performance.
- `amplifier_best_overall_circuit.cir`: the biased, sized SPICE netlist.
- `best_optuna_study.pkl`: winning study for local analysis.
- `optuna_log_*.log`, frequency response plots, and `multiple_runs_history.png`.

Use a separate output directory for each circuit or invocation. Existing files
with these names are replaced on rerun. Source modules are never used as result
files, even when their names do not end with `_optimize.py`.

## Validation

```bash
python -m unittest discover -s tests -v
```

The regression checks cover generated parameter validation, source-safe output
names, and the generation-to-sizing command. For an actual simulator smoke test,
run the two short optimization commands above and inspect the reported metrics.
