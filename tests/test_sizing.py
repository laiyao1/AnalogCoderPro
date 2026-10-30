"""Regression checks; no LLM calls or simulator library required."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

import numpy as np
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sizing", ROOT / "optimize/circuit_optimizer_helper.py"
)
sizing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sizing)


class SizingTests(unittest.TestCase):
    def test_validates_generated_parameter_space(self):
        bounds = {"w": {"min": 1e-6, "max": 20e-6, "log": True}}
        sizing.validate_parameters({"w": 10e-6}, bounds)
        for params, ranges in (
            ({"other": 10e-6}, bounds),
            ({"w": 30e-6}, bounds),
            ({"w": float("nan")}, bounds),
            ({"w": 1}, {"w": {"min": 0, "max": 2, "log": True}}),
            ({}, {}),
        ):
            with self.subTest(params=params), self.assertRaises(ValueError):
                sizing.validate_parameters(params, ranges)

    def test_results_never_overwrite_source(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("circuit.py", "p59_0_0_optimize.py", "optimize.py"):
                path = Path(directory) / name
                path.write_text("# original circuit\n")
                result = sizing.result_path(path, "multi_run_summary.json")
                result.write_text("{}")
                self.assertNotEqual(result, path)
                self.assertEqual(path.read_text(), "# original circuit\n")

    def test_examples_load_from_outside_their_directory(self):
        for name in ("amplifier", "opamp"):
            with self.subTest(name=name):
                create, initial, _ = sizing.load_optimizer(
                    ROOT / f"optimize/examples/{name}_optimize.py"
                )
                circuit = create(initial)
                self.assertIn("Vdd", circuit.element_names)
                self.assertAlmostEqual(float(circuit.element("Vdd").dc_value), 1.2)
                self.assertNotIn("c_load", initial)

    def test_objective_scores_preserve_benchmark_conventions(self):
        expected = {"gain": 40.0, "gbw": 0.00505, "fom": 0.42083333333333334}
        for differential in (False, True):
            for target, expected_score in expected.items():
                with self.subTest(differential=differential, target=target):
                    source = types.SimpleNamespace(name="Vdd", dc_value=1.2)
                    circuit = Mock()
                    circuit.element_names = (
                        ["Vdd", "Vinp", "Vinn"] if differential else ["Vdd", "Vin"]
                    )
                    circuit.elements = [source]
                    circuit.element.return_value = source
                    simulator = circuit.simulator.return_value
                    simulator.operating_point.return_value = types.SimpleNamespace(
                        branches={"vdd": -0.001}
                    )
                    output = types.SimpleNamespace(
                        as_ndarray=lambda: np.array([100.0, 10.0, 0.1]) * 1e-9
                    )
                    response = {"vout": output}
                    simulator.ac.return_value = MagicMock(
                        **{
                            "__getitem__": Mock(side_effect=response.__getitem__),
                            "frequency.as_ndarray.return_value": np.array(
                                [1.0, 100.0, 10000.0]
                            ),
                        }
                    )
                    score, info = sizing.evaluate_circuit(circuit, target)
                    self.assertAlmostEqual(score, expected_score)
                    self.assertAlmostEqual(info["gbw"], 5050.0)
                    self.assertAlmostEqual(info["power"], 1.2)
                    self.assertEqual(
                        info["load"], {"gain": None, "gbw": 10, "fom": 100}[target]
                    )
                    if target == "gain":
                        circuit.C.assert_not_called()
                    else:
                        circuit.C.assert_called_once_with(
                            "load",
                            "Vout",
                            circuit.gnd,
                            "10p" if target == "gbw" else "100p",
                        )

    def test_extracts_fenced_and_plain_python_responses(self):
        tree = ast.parse((ROOT / "run.py").read_text())
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "extract_code"
        )
        namespace = {
            "ast": ast,
            "re": __import__("re"),
            "args": types.SimpleNamespace(ngspice=False),
        }
        exec(
            compile(ast.Module(body=[function], type_ignores=[]), "run.py", "exec"),
            namespace,
        )
        extract = namespace["extract_code"]
        code = (
            "def create_circuit(params):\n"
            "    return params\n"
            "initial_params = {'w': 1.0}\n"
            "param_ranges_definition = {'w': {'min': 0.5, 'max': 2.0}}\n"
        )
        for response in (
            code,
            "```python\n" + code + "```",
            "# parameterized circuit\n" + code,
        ):
            with self.subTest(response=response[:20]):
                error, output = extract(response)
                self.assertEqual(error, 0)
                ast.parse(output)
                self.assertIn("def create_circuit", output)
                self.assertIn("initial_params", output)
        for response in (
            "",
            "   ",
            "Here is your corrected circuit.",
            "hello",
            "def broken(:",
        ):
            self.assertEqual(extract(response), (1, ""))

    def test_default_model_omits_unsupported_sampling_parameters(self):
        tree = ast.parse((ROOT / "run.py").read_text())
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "sampling_options"
        )
        namespace = {}
        exec(
            compile(ast.Module(body=[function], type_ignores=[]), "run.py", "exec"),
            namespace,
        )
        options = namespace["sampling_options"]
        for model in ("gpt-5-mini", "gpt-5-mini-2025-08-07", "gpt-5", "gpt-5.2"):
            self.assertEqual(options(model, 0.8), {})
        self.assertEqual(options("gpt-4.1", 0.8), {"temperature": 0.8})

    def test_generation_launches_canonical_optimizer_with_same_python(self):
        # Load only the function under test: importing run.py would parse CLI
        # arguments and construct API clients.
        tree = ast.parse((ROOT / "run.py").read_text())
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "optimize_code"
        )
        namespace = {
            "__file__": str(ROOT / "run.py"),
            "os": __import__("os"),
            "sys": sys,
            "subprocess": subprocess,
            "client": Mock(),
            "optimize_template": "[CODE]",
            "extract_code": lambda _: (0, "# parameterized circuit"),
            "args": types.SimpleNamespace(
                model="test-model",
                temperature=0.5,
                sizing_runs=2,
                sizing_trials=3,
                sizing_jobs=1,
            ),
        }
        namespace[
            "client"
        ].chat.completions.create.return_value = types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(
                        content="```python\n# parameterized circuit\n```"
                    )
                )
            ]
        )
        options = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "sampling_options"
        )
        exec(
            compile(
                ast.Module(body=[options, function], type_ignores=[]), "run.py", "exec"
            ),
            namespace,
        )
        with tempfile.TemporaryDirectory(prefix="sizing test ") as directory:
            path = Path(directory) / "p59_0_0_success.py"
            path.write_text(
                "circuit = Circuit('test')\nsimulator = circuit.simulator()\n"
            )
            with patch.object(subprocess, "run") as run:
                namespace["optimize_code"](
                    str(path), 59, "Amplifier", "maximize GBW/Power"
                )
            command = run.call_args.args[0]
            self.assertEqual(
                command[:2],
                [sys.executable, str(ROOT / "optimize/circuit_optimizer_helper.py")],
            )
            self.assertEqual(command[2], str(path.with_name("p59_0_0_optimize.py")))
            self.assertEqual(
                command[3:], ["fom", "2", "--n-trials", "3", "--n-jobs", "1"]
            )
            self.assertTrue(run.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
