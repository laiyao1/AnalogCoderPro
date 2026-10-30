"""Opt-in runner integration with scripted model replies and real ngspice.

Run with ANALOGCODER_INTEGRATION=1. No external model API is contacted.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]


def circuit_replies(differential):
    """Supply deterministic fixtures for runner integration, not benchmark results."""
    imports = (
        "from PySpice.Spice.Netlist import Circuit\n"
        "from PySpice.Unit import *\n"
        "from model import nmos_params, pmos_params\n"
    )
    body = (
        "circuit = Circuit('Runner Integration Fixture')\n"
        "circuit.model('nmos_model', 'nmos', **nmos_params)\n"
        "circuit.V('dd', 'Vdd', circuit.gnd, 1.2)\n"
    )
    if differential:
        body += (
            "circuit.V('inp', 'Vinp', circuit.gnd, 0.6)\n"
            "circuit.V('inn', 'Vinn', circuit.gnd, 0.6)\n"
            "circuit.MOSFET('1', 'Out1', 'Vinp', 'Tail', 'Tail', model='nmos_model', w=1e-6, l=45e-9)\n"
            "circuit.MOSFET('2', 'Vout', 'Vinn', 'Tail', 'Tail', model='nmos_model', w=1e-6, l=45e-9)\n"
            "circuit.I('tail', 'Tail', circuit.gnd, 200e-6)\n"
            "circuit.R('left', 'Out1', 'Vdd', 1000)\n"
        )
    else:
        body += (
            "circuit.V('in', 'Vin', circuit.gnd, 0.6)\n"
            "circuit.MOSFET('1', 'Vout', 'Vin', circuit.gnd, circuit.gnd, model='nmos_model', w=1e-6, l=45e-9)\n"
        )
    body += (
        "circuit.R('load', 'Vout', 'Vdd', 1000)\n"
        "circuit.C('L', 'Vout', circuit.gnd, '100p')\n"
    )
    topology = imports + body + "simulator = circuit.simulator()\n"
    parameter_body = body.replace("w=1e-6", "w=params['width']").replace(
        "'Vdd', 1000", "'Vdd', params['resistance']"
    )
    parameterized = (
        imports
        + "\ndef create_circuit(params):\n"
        + textwrap.indent(parameter_body + "return circuit\n", "    ")
        + "\ninitial_params = {'width': 1e-6, 'resistance': 1000}\n"
        + "param_ranges_definition = {\n"
        + "    'width': {'min': 45e-9, 'max': 22.5e-6, 'log': True},\n"
        + "    'resistance': {'min': 500, 'max': 2000, 'log': True},\n"
        + "}\n"
    )
    return topology, parameterized


class ScriptedClient:
    """Emulate only model responses; simulator and optimizer execute normally."""

    def __init__(self, task_id):
        self.chat = types.SimpleNamespace(completions=self)
        self.replies = circuit_replies(task_id % 2 == 0)
        self.requests = []

    def create(self, **kwargs):
        if "temperature" in kwargs:
            raise AssertionError("The default gpt-5-mini request must omit temperature")
        self.requests.append(kwargs)
        if len(self.requests) > 2:
            raise AssertionError("Unexpected model retry in the deterministic fixture")
        parameterizing = "parameterized form" in kwargs["messages"][-1]["content"]
        code = self.replies[int(parameterizing)]
        return types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(content=f"```python\n{code}```")
                )
            ],
            usage=types.SimpleNamespace(
                total_tokens=2, prompt_tokens=1, completion_tokens=1
            ),
        )


@unittest.skipUnless(
    os.environ.get("ANALOGCODER_INTEGRATION") == "1",
    "Set ANALOGCODER_INTEGRATION=1 to run real ngspice integration",
)
class RunnerIntegrationTests(unittest.TestCase):
    def test_automatic_sizing_for_both_circuit_types_and_all_objectives(self):
        for task_id, target in (
            (51, "gain"),
            (52, "gain"),
            (55, "gbw"),
            (56, "gbw"),
            (59, "fom"),
            (60, "fom"),
        ):
            with self.subTest(task_id=task_id), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                for path in ROOT.iterdir():
                    if path.is_file() and path.suffix in {".md", ".tsv", ".py"}:
                        shutil.copy2(path, directory / path.name)
                for name in ("optimize", "mosfet_model", "problem_check"):
                    shutil.copytree(
                        ROOT / name,
                        directory / name,
                        ignore=shutil.ignore_patterns("__pycache__"),
                    )
                # A different `python` on PATH must not run any simulation.
                shadow = directory / "shadow-bin"
                shadow.mkdir()
                executable = shadow / "python"
                executable.write_text("#!/bin/sh\nexit 86\n")
                executable.chmod(0o755)
                env = os.environ.copy()
                env["PATH"] = str(shadow) + os.pathsep + env.get("PATH", "")
                env["PYTHONPATH"] = str(ROOT / "tests")
                worker = """
import runpy
import sys
from unittest.mock import patch
from test_runner_integration import ScriptedClient
client = ScriptedClient(int(sys.argv[1]))
sys.argv = ["run.py", "--task_id=" + sys.argv[1], "--num_per_task=1",
            "--num_of_retry=1", "--no_vlm", "--api_key=scripted-placeholder",
            "--sizing-trials=2", "--sizing-jobs=1", "--sizing-runs=1"]
with patch("openai.OpenAI", return_value=client):
    runpy.run_path("run.py", run_name="__main__")
assert len(client.requests) == 2, "Expected topology and parameterization requests"
"""
                result = subprocess.run(
                    [sys.executable, "-u", "-c", worker, str(task_id)],
                    cwd=directory,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stdout[-12000:])
                output = directory / f"gpt-5-mini_no_vlm/p{task_id}/0"
                summary = output / f"p{task_id}_0_0_multi_run_summary.json"
                self.assertTrue(summary.exists(), result.stdout[-12000:])
                data = json.loads(summary.read_text())
                self.assertEqual(data["optimization_target"], target)
                self.assertIsNotNone(data["initial_info"]["gain"])
                self.assertGreater(data["initial_info"]["power"], 0)
                self.assertEqual(len(data["individual_runs"]), 1)
                self.assertTrue(
                    (output / f"p{task_id}_0_0_best_overall_circuit.cir").exists()
                )
                self.assertTrue((output / "multiple_runs_history.png").exists())
                print(f"PASS: automatic sizing task {task_id} ({target})", flush=True)


if __name__ == "__main__":
    unittest.main()
