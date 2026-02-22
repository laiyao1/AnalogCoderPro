from openai import OpenAI
import openai
import argparse
import re
import os
import subprocess
import time
import pandas as pd
import sys
import shutil

import base64

parser = argparse.ArgumentParser()
parser.add_argument('--model', type=str, default="gpt-5-mini")
parser.add_argument('--temperature', type=float, default=0.5)
parser.add_argument('--num_per_task', type=int, default=30)
parser.add_argument('--num_of_retry', type=int, default=3)
parser.add_argument("--num_of_done", type=int, default=0)
parser.add_argument("--task_id", type=int, default=1)
parser.add_argument("--ngspice", action="store_true", default=False)
parser.add_argument("--no_prompt", action="store_true", default=False)
parser.add_argument("--no_tool", action="store_true", default=False)
parser.add_argument("--no_context", action="store_true", default=False)
parser.add_argument("--no_chain", action="store_true", default=False)
parser.add_argument("--retrieval", action="store_true", default=False)
parser.add_argument("--port", type=int, default=5000)
parser.add_argument("--no_vlm", action="store_true")
parser.add_argument("--api_key", type=str, default=None, help="API key (or set OPENAI_API_KEY)")
parser.add_argument("--base_url", type=str, default=None, help="API base URL (or set OPENAI_BASE_URL)")

args = parser.parse_args()
args.api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
args.base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")

if "gpt-5" in args.model:
    args.temperature = 1
if args.task_id > 50:
    args.temperature += 0.3

complex_task_type = ['Oscillator', 'Integrator', 'Differentiator', 'OscillatorFFT',
                     'Adder', 'Subtractor', 'Schmitt', 'VCO', 'PLL', 'Comparator',
                     'Mixer',
                     'BandPass', 'BandStop', 'LowPass', 'HighPass'
                     ]
bias_usage = "Please increase the gain as much as possible to maintain oscillation."


dc_sweep_template = open("dc_sweep_template.py", "r").read()

pyspice_template = """
try:
    analysis = simulator.operating_point()
    fopen = open("[OP_PATH]", "w")
    for node in analysis.nodes.values(): 
        fopen.write(f"{str(node)}\\t{float(analysis[str(node)][0]):.6f}\\n")
    fopen.close()
except Exception as e:
    print("Analysis failed due to an error:")
    print(str(e))
"""


output_netlist_template = """
source = str(circuit)
print(source)
"""

import_template = """
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
"""


sin_voltage_source_template = """
circuit.SinusoidalVoltageSource('sin', 'Vin', circuit.gnd, 
    ac_magnitude=1@u_nV, dc_offset={0}, amplitude=1@u_nV, offset={0})
"""


optimize_template = open("optimize_template.md", "r").read()
global client


client = OpenAI(api_key=args.api_key, base_url=args.base_url)

client_vlm = None
vlm_model = args.model
if not args.no_vlm:
    client_vlm = OpenAI(api_key=args.api_key, base_url=args.base_url)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_code(generated_content):
    empty_code_error = 0
    assert generated_content != "", "generated_content is empty"
    regex = r"```.*?\n(.*?)```"
    matches = list(re.finditer(regex, generated_content, re.DOTALL))
    
    if not matches:
        empty_code_error = 1
        return empty_code_error, ""

    last_match = matches[-1]
    
    try:
        code = last_match.group(1)
        code = "\n".join([line for line in code.split("\n") if len(line.strip()) > 0])
    except:
        code = ""
        empty_code_error = 1
        return empty_code_error, code

    if not args.ngspice:
        if "from PySpice.Spice.Netlist import Circuit" not in code:
            code = "from PySpice.Spice.Netlist import Circuit\n" + code
        if "from PySpice.Unit import *" not in code:
            code = "from PySpice.Unit import *\n" + code
        
    new_code = ""
    for line in code.split("\n"):
        new_code += line + "\n"
        if "circuit.simulator()" in line:
            break

    return empty_code_error, new_code

def run_code(file):
    simulation_error = 0
    execution_error = 0
    execution_error_info = ""
    floating_node = ""
    try:
        result = subprocess.run(["python", "-u", file], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, env=os.environ.copy())
        if len(result.stdout.split("\n")) >= 2 and ("failed" in result.stdout.split("\n")[-2] or "failed" in result.stdout.split("\n")[-1]):
            if len(result.stdout.split("\n")) >= 2:
                if "check node" in result.stdout.split("\n")[1]:
                    # print("simulation error, check node")
                    simulation_error = 1
                    floating_node = result.stdout.split("\n")[1].split()[-1]
                    # print("floating_node", floating_node)
                else:
                    execution_error = 1
                    if "ERROR" in result.stdout.split("\n")[1]:
                        execution_error_info = "ERROR" + result.stdout.split("\n")[1].split("ERROR")[-1]
                    elif "Error" in result.stdout.split("\n")[1]:
                        execution_error_info = "Error" + result.stdout.split("\n")[1].split("Error")[-1]
                    if len(result.stdout.split("\n"))>=3 and "ERROR" in result.stdout.split("\n")[2]:
                        execution_error_info += "\nERROR" + result.stdout.split("\n")[2].split("ERROR")[-1]
                    elif len(result.stdout.split("\n"))>=3 and "Error" in result.stdout.split("\n")[2]:
                        execution_error_info += "\nError" + result.stdout.split("\n")[2].split("Error")[-1]
                    if len(result.stdout.split("\n"))>=4 and "ERROR" in result.stdout.split("\n")[3]:
                        execution_error_info += "\nERROR" + result.stdout.split("\n")[3].split("ERROR")[-1]
                    elif len(result.stdout.split("\n"))>=4 and "Error" in result.stdout.split("\n")[3]:
                        execution_error_info += "\nError" + result.stdout.split("\n")[3].split("Error")[-1]
            if len(result.stderr.split("\n")) >= 2:
                if "check node" in result.stderr.split("\n")[1]:
                    simulation_error = 1
                    floating_node = result.stderr.split("\n")[1].split()[-1]
                else:
                    execution_error = 1
                    if "ERROR" in result.stderr.split("\n")[1]:
                        execution_error_info = "ERROR" + result.stderr.split("\n")[1].split("ERROR")[-1]
                    elif "Error" in result.stderr.split("\n")[1]:
                        execution_error_info = "Error" + result.stderr.split("\n")[1].split("Error")[-1]
                    if len(result.stdout.split("\n"))>=3 and "ERROR" in result.stderr.split("\n")[2]:
                        execution_error_info += "\nERROR" + result.stderr.split("\n")[2].split("ERROR")[-1]
                    elif len(result.stdout.split("\n"))>=3 and "Error" in result.stdout.split("\n")[2]:
                        execution_error_info += "\nError" + result.stdout.split("\n")[2].split("Error")[-1]
                    if len(result.stdout.split("\n"))>=4 and "ERROR" in result.stderr.split("\n")[3]:
                        execution_error_info += "\nERROR" + result.stderr.split("\n")[3].split("ERROR")[-1]
                    elif len(result.stdout.split("\n"))>=4 and "Error" in result.stderr.split("\n")[3]:
                        execution_error_info += "\nError" + result.stderr.split("\n")[3].split("Error")[-1]
            if simulation_error == 1:
                execution_error = 0
            if execution_error_info == "" and execution_error == 1:
                execution_error_info = "Simulation failed."
        code_content = open(file, "r").read()
        if "circuit.X" in code_content:
            execution_error_info += "\nPlease avoid using the subcircuit (X) in the code."
        if "error" in result.stdout.lower() and not "<<NAN, error".lower() in result.stdout.lower() and simulation_error == 0:
            execution_error = 1
            execution_error_info = result.stdout + result.stderr
        return execution_error, simulation_error, execution_error_info, floating_node
    except subprocess.CalledProcessError as e:
        print(f"error when running: {e}")
        print("stderr", e.stderr, file=sys.stderr)
        if "failed" in e.stdout:
            if len(e.stderr.split("\n")) >= 2:
                if "check node" in e.stderr.split("\n")[1]:
                    simulation_error = 1
                    floating_node = e.stderr.split("\n")[1].split()[-1]
        execution_error = 1
        
        execution_error_info = e.stdout + e.stderr
        if simulation_error == 1:
            execution_error = 0
            execution_error_info = "Simulation failed."
        return execution_error, simulation_error, execution_error_info, floating_node
    except subprocess.TimeoutExpired:
        print(f"Time out error when running code.")
        execution_error = 1
        execution_error_info = "Time out error when running code.\n"
        execution_error_info = "Suggestion: Avoid letting users input in Python code.\n"
        return execution_error, simulation_error, execution_error_info, floating_node




def check_netlist(netlist_path, operating_point_path, input, output, task_id, task_type, optimize = False):
    warning = 0
    warning_message = ""
    if not os.path.exists(operating_point_path):
        return 0, ""
    fopen_op = open(operating_point_path, 'r').read()
    for input_node in input.split(", "):
        if input_node.lower() not in fopen_op.lower():
            warning_message += "The given input node ({}) is not found in the netlist.\n".format(input_node)
            warning = 1
    for output_node in output.split(", "):
        if output_node.lower() not in fopen_op.lower():
            warning_message += "The given output node ({}) is not found in the netlist.\n".format(output_node)
            warning = 1

    if warning == 1:
        warning_message += "Suggestion: You can replace the nodes actually used for input/output with the given names. Please rewrite the corrected complete code.\n"

    if task_type == "Inverter":
        return warning, warning_message
    vdd_voltage = 5.0
    vinn_voltage = 1.0
    vinp_voltage = 1.0
    for line in fopen_op.split("\n"):
        line = line.lower()
        if line.startswith("vdd"):
            vdd_voltage = float(line.split("\t")[-1])
        if line.startswith("vinn"):
            vinn_voltage = float(line.split("\t")[-1])
        if line.startswith("vinp"):
            vinp_voltage = float(line.split("\t")[-1])
    
    if vinn_voltage != vinp_voltage:
        warning_message += "The given input voltages of Vinn and Vinp are not equal.\n"
        warning = 1
        warning_message += "Suggestion: Please make sure the input voltages are equal.\n"
    
    fopen_netlist = open(netlist_path, 'r')
    voltages = {}
    for line in fopen_op.split("\n"):
        if line.strip() == "":
            continue
        node, voltage = line.split()
        voltages[node] = float(voltage)
    voltages["0"] = 0
    voltages["gnd"] = 0

    vthn = 0.5
    vthp = 0.5

    if optimize:
        vthn = 0.01
        vthp = 0.01
    miller_node_1 = None
    miller_node_2 = None
    resistance_exist = 0
    has_diodeload = 0
    first_stage_out = None
    for line in fopen_netlist.readlines():
        if line.startswith('.'):
            continue
        if line.startswith("C"):
            if task_id == 9:
                miller_node_1 = line.split()[1].lower()
                miller_node_2 = line.split()[2].lower()
        if line.startswith("R"):
            resistance_exist = 1
        if line.startswith("M"):
            name, drain, gate, source, bulk, model = line.split()[:6]
            name = name[1:]
            drain = drain.lower()
            source = source.lower()
            bulk = bulk.lower()
            gate = gate.lower()
            mos_type = "NMOS" if "nmos" in model.lower() else "PMOS"
            if task_id == 4:
                if drain == "vin" or gate == "vin":
                    warning_message += (f"For a common-gate amplifier, the vin should be connected to source.\n")
                    warning_message += (f"Suggestion: Please connect the vin to the source node.\n")
                    warning = 1
            elif task_id == 3:
                if drain == "vout" or gate == "vout":
                    warning_message += (f"For a common-drain amplifier, the vout should be connected to source.\n")
                    warning_message += (f"Suggestion: Please connect the vout to the source node.\n")
                    warning = 1
            elif task_id == 10:
                if gate == drain:
                    has_diodeload = 1
                    
            elif task_id == 9:
                if gate == "vin":
                    first_stage_out = drain
            
            if mos_type == "NMOS":
                vds_error = 0
                if voltages[drain] == 0.0:
                    if drain.lower() == "0" or drain.lower() == "gnd":
                        warning_message += (f"Suggetions: Please avoid connect {mos_type} {name} drain to the ground.\n")
                    else:
                        vds_error = 1
                        warning_message += (f"For {mos_type} {name}, the drain node ({drain}) voltage is 0.\n")
                elif voltages[drain] < voltages[source]:
                    vds_error = 1
                    warning_message += (f"For {mos_type} {name}, the drain node ({drain}) voltage is lower than the source node ({source}) voltage.\n")
                if vds_error == 1:
                    warning_message += (f"Suggestion: Please set {mos_type} {name} with an activated state and make sure V_DS > V_GS - V_TH.\n")
                vgs_error = 0
                if voltages[gate] == voltages[source]:
                    if gate == source:
                        warning_message += (f"For {mos_type} {name}, the gate node ({gate}) is connected to the source node ({source}).\n")
                        warning_message += (f"Suggestion: Please {mos_type} {name}, please divide its gate ({gate}) and source ({source}) connection.\n")
                    else:
                        vgs_error = 1
                        warning_message += (f"For {mos_type} {name}, the gate node ({gate}) voltage is equal to the source node ({source}) voltage.\n")
                elif voltages[gate] < voltages[source]:
                    vgs_error = 1
                    warning_message += (f"For {mos_type} {name}, the gate node ({gate}) voltage is lower than the source node ({source}) voltage.\n")
                elif voltages[gate] <= voltages[source] + vthn:
                    vgs_error = 1
                    warning_message += (f"For {mos_type} {name}, the gate node ({gate}) voltage is lower than the source node ({source}) voltage plus the threshold voltage.\n")
                if vgs_error == 1:
                    warning_message += (f"Suggestion: Please set {mos_type} {name} with an activated state by increasing the gate voltage or decreasing the source voltage and make sure V_GS > V_TH.\n")
            if mos_type == "PMOS":
                vds_error = 0
                if voltages[drain] == vdd_voltage:
                    if drain.lower() == "vdd":
                        warning_message += (f"Suggestion: Please avoid connect {mos_type} {name} drain to the vdd.\n")
                    else:
                        vds_error = 1
                        warning_message += (f"For {mos_type} {name}, the drain node ({drain}) voltage is V_dd.\n")
                elif voltages[drain] > voltages[source]:
                    vds_error = 1
                    warning_message += (f"For {mos_type} {name}, the drain node ({drain}) voltage is higher than the source node ({source}) voltage.\n")
                if vds_error == 1:
                    warning_message += (f"Suggestion: Please set {mos_type} {name} with an activated state and make sure V_DS < V_GS - V_TH.\n")
                vgs_error = 0
                if voltages[gate] == voltages[source]:
                    if gate == source:
                        warning_message += (f"For {mos_type} {name}, the gate node ({gate}) is connected to the source node ({source}).\n")
                        warning_message += f"Suggestion: Please {mos_type} {name}, please divide its gate ({gate}) and source ({source}) connection.\n"
                    else:
                        vgs_error = 1
                        warning_message += (f"For {mos_type} {name}, the gate node ({gate}) voltage is equal to the source node ({source}) voltage.\n")
                elif voltages[gate] > voltages[source]:
                    vgs_error = 1
                    warning_message += (f"For {mos_type} {name}, the gate node ({gate}) voltage is higher than the source node ({source}) voltage.\n")
                elif voltages[gate] >= voltages[source] - vthp:
                    vgs_error = 1
                    warning_message += (f"For {mos_type} {name}, the gate node ({gate}) voltage is higher than the source node ({source}) voltage plus the threshold voltage.\n")
                if vgs_error == 1:
                    warning_message += (f"Suggestion: Please set {mos_type} {name} with an activated state by decreasing the gate voltage or incresing the source voltage and make sure V_GS < V_TH.\n")

    if task_id in [1, 2, 3, 4, 5, 6, 8, 13]:
        if resistance_exist == 0:
            warning_message += "There is no resistance in the netlist.\n"
            warning_message += "Suggestion: Please add a resistance load in the netlist.\n"
            warning = 1
    if task_id == 9:
        if first_stage_out == None:
            warning_message += "There is no first stage output in the netlist.\n"
            warning_message += "Suggestion: Please add a first stage output in the netlist.\n"
            warning = 1
        elif (first_stage_out == miller_node_1 and miller_node_2 == "vout") or (first_stage_out == miller_node_2 and miller_node_1 == "vout"):
            pass
        elif miller_node_1 == None:
            warning_message += "There no Miller capacitor in the netlist.\n"
            warning_message += "Suggestion: Please correctly connect the Miller compensation capacitor."
            warning = 1
        else:
            warning_message += "The Miller compensation capacitor is not correctly connected.\n"
            warning_message += "Suggestion: Please correctly connect the Miller compensation capacitor."
            warning = 1
    if task_id == 10 and has_diodeload == 0:
        warning_message += "There is no diode-connected load in the netlist.\n"
        warning_message += "Suggestion: Please add a diode-connected load in the netlist.\n"
        warning = 1
    warning_message = warning_message.strip()
    if warning_message == "":
        warning = 0
    else:
        warning = 1
        warning_message = "According to the operating point check, there are some issues, which defy the general operating principles of MOSFET devices. \n" + warning_message + "\n"
        warning_message += "\nPlease help me fix the issues and rewrite the corrected complete code.\n"
    return warning, warning_message

    
def check_function(task_id, code_path, task_type):
    fwrite_code_path = "{}_check.py".format(code_path.rsplit(".", 1)[0])
    fwrite_code = open(fwrite_code_path, 'w')
    if task_type == "CurrentMirror":
        test_code = open("problem_check/CurrentMirror.py", "r").read()
        code = open(code_path, 'r').read()
        code = code + "\n" + test_code
        fwrite_code.write(code)
        fwrite_code.close()
    elif task_type == "Amplifier" or task_type == "Opamp":
        voltage = "1.0"
        test_code = open(f"problem_check/{task_type}.py", "r").read()
        for line in open(code_path, 'r').readlines():
            if line.startswith("circuit.V") and "vin" in line.lower():
                
                parts = line.split("#")[0].strip().rstrip(")").split(",")
                raw_voltage = parts[-1].strip()
                if raw_voltage[0] == "\"" or raw_voltage[0] == "'":
                    raw_voltage = raw_voltage[1:-1]
                if "dc" in raw_voltage.lower():
                    voltage = raw_voltage.split(" ")[1]
                else:
                    voltage = raw_voltage
                new_voltage = " \"dc {} ac 1n\"".format(voltage)
                parts[-1] = new_voltage
                line = ",".join(parts) + ")\n"

            fwrite_code.write(line)
        fwrite_code.write("\n")
        fwrite_code.write(test_code)
        fwrite_code.close()
    elif task_type == "Inverter":
        test_code = open("problem_check/Inverter.py", "r").read()
        code = open(code_path, 'r').read()
        code = code + "\n" + test_code
        fwrite_code.write(code)
        fwrite_code.close()
    else:
        return 0, ""
    try:
        result = subprocess.run(["python", "-u", fwrite_code_path], check=True, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
        func_error = 0
        return_message = ""
    except subprocess.CalledProcessError as e:
        func_error = 1
        return_message = "\n".join(e.stdout.split("\n"))

    return func_error, return_message

import numpy as np
def get_best_voltage(dc_file_path, target_voltage=2.5):
    fopen = open(dc_file_path, 'r')
    vin = np.array([float(x) for x in fopen.readline().strip().split(" ")])
    vout = np.array([float(x) for x in fopen.readline().strip().split(" ")])
    if np.max(vout) - np.min(vout) < 1e-6:
        return 1, 0

    distances = np.abs(vout - target_voltage)
    min_distance = np.min(distances)
    min_indices = np.where(distances == min_distance)[0]
    best_index = min_indices[np.argmin(np.abs(vin[min_indices] - target_voltage))]
    
    return 0, vin[best_index]


def get_vin_name(netlist_content, task_type):
    vinn_name = "in"
    vinp_name = None
    for line in netlist_content.split("\n"):
        if not line.lower().startswith("v"):
            continue
        if len(line.lower().split()) < 2:
            continue
        if task_type == "Amplifier" and "vin" in line.lower().split()[1]:
            vinn_name = line.split()[0][1:]
        if task_type == "Opamp" and "vinp" in line.lower().split()[1]:
            vinp_name = line.split()[0][1:]
        if task_type == "Opamp" and "vinn" in line.lower().split()[1]:
            vinn_name = line.split()[0][1:]
    return vinn_name, vinp_name


def replace_voltage(raw_code, best_voltage, vinn_name, vinp_name):
    target_sources = []
    if vinn_name:
        target_sources.append(vinn_name.lower())
    if vinp_name:
        target_sources.append(vinp_name.lower())

    replacements = 0
    new_code_lines = []
    for line_num, line in enumerate(raw_code.split("\n"), 1):
        if "circuit.v(" in line.lower():
            try:
                start_idx = line.lower().find("circuit.v(")
                open_parens = 1
                close_idx = start_idx + len("circuit.v(")
                while open_parens > 0 and close_idx < len(line):
                    if line[close_idx] == '(':
                        open_parens += 1
                    elif line[close_idx] == ')':
                        open_parens -= 1
                    close_idx += 1
                if open_parens == 0:
                    v_def = line[start_idx:close_idx]
                    v_parts = v_def.split(',')
                    name_part = v_parts[0].split('(')[1].strip()
                    if (name_part.startswith("'") and name_part.endswith("'")) or \
                       (name_part.startswith('"') and name_part.endswith('"')):
                        name_part = name_part[1:-1]
                    if name_part.lower() in target_sources:
                        if len(v_parts) >= 3:
                            last_part = v_parts[-1].strip()
                            if '#' in last_part:
                                value_part, comment = last_part.split('#', 1)
                                new_last_part = f" {best_voltage} #{comment}"
                            else:
                                if ')' in last_part:
                                    new_last_part = f" {best_voltage})"
                                else:
                                    new_last_part = f" {best_voltage}"
                            v_parts[-1] = new_last_part
                            new_v_def = ','.join(v_parts)
                            line = line[:start_idx] + new_v_def + line[close_idx:]
                            replacements += 1
            except Exception as e:
                pass
        new_code_lines.append(line)
    return "\n".join(new_code_lines)

def connect_vinn_vinp(dc_sweep_code, vinn_name, vinp_name):
    new_code = ""
    for line in dc_sweep_code.split("\n"):
        if not line.lower().startswith("circuit.v"):
            new_code += line + "\n"
            continue
        if vinp_name is not None and (line.lower().startswith(f"circuit.v('{vinp_name.lower()}'") or line.lower().startswith(f"circuit.v(\"{vinp_name.lower()}\"")):
            new_line = "circuit.V('dc', 'Vinn', 'Vinp', 0.0)\n"
            new_code += new_line
        else:
            new_code += line + "\n"
    return new_code

def get_subcircuits_info(subcircuits, 
                    lib_data_path = "lib_info.tsv", task_data_path = "problem_set.tsv"):
    lib_df = pd.read_csv(lib_data_path, delimiter='\t')
    task_df = pd.read_csv(task_data_path, delimiter='\t')
    columns = ["Id", "Circuit Type", "Gain/Differential-mode gain (dB)", "Common-mode gain (dB)", "Input", "Output"]
    subcircuits_df = pd.DataFrame(columns=columns)
    for sub_id in subcircuits:
        sub_type = task_df.loc[task_df['Id'] == sub_id, 'Type'].item()
        sub_gain = float(lib_df.loc[lib_df['Id'] == sub_id, 'Av (dB)'].item())
        sub_com_gan = float(lib_df.loc[lib_df['Id'] == sub_id, 'Com Av (dB)'].item())
        sub_gain = "{:.2f}".format(sub_gain)
        sub_com_gan = "{:.2f}".format(sub_com_gan)
        sub_input = task_df.loc[task_df['Id'] == sub_id, 'Input'].item()
        input_node_list = sub_input.split(", ")
        input_node_list = [node for node in input_node_list if "bias" not in node]
        sub_input = ", ".join(input_node_list)

        sub_output = task_df.loc[task_df['Id'] == sub_id, 'Output'].item()
        output_node_list = sub_output.split(", ")
        output_node_list = [node for node in output_node_list if "outn" not in node and "outp" not in node]
        sub_output = ",".join(output_node_list)
        
        new_row = {'Id': sub_id, "Circuit Type": sub_type, "Gain/Differential-mode gain (dB)": sub_gain, "Common-mode gain (dB)": sub_com_gan, "Input": sub_input, "Output": sub_output}
        subcircuits_df = pd.concat([subcircuits_df, pd.DataFrame([new_row])], ignore_index=True)
    subcircuits_info = subcircuits_df.to_csv(sep='\t', index=False)
    return subcircuits_info


def get_note_info(subcircuits,
                    lib_data_path = "lib_info.tsv", task_data_path = "problem_set.tsv"):
    lib_df = pd.read_csv(lib_data_path, delimiter='\t')
    task_df = pd.read_csv(task_data_path, delimiter='\t')
    note_info = ""

    for sub_id in subcircuits:
        sub_type = task_df.loc[task_df['Id'] == sub_id, 'Type'].item()
        sub_name = task_df.loc[task_df['Id'] == sub_id, 'Submodule Name'].item()
        sub_bias_voltage = lib_df.loc[lib_df['Id'] == sub_id, 'Voltage Bias'].item()
        if "Amplifier" not in sub_type and "Opamp" not in sub_type:
            continue
        sub_phase = lib_df.loc[lib_df['Id'] == sub_id, 'Vin(n) Phase'].item()
        if sub_type == "Amplifier":
            if sub_phase == "inverting":
                other_sub_phase = "non-inverting"
            else:
                other_sub_phase = "inverting"
            note_info += f"The Vin of {sub_name} is the {sub_phase} input.\n"
            note_info += f"There is NO in {other_sub_phase} input in {sub_name}.\n"
            note_info += f"The DC operating voltage for Vin is {sub_bias_voltage} V.\n"
        elif sub_type == "Opamp":
            if sub_phase == "inverting":
                other_sub_phase = "non-inverting"
            else:
                other_sub_phase = "inverting"
            note_info += f"The Vinn of {sub_name} is the {sub_phase} input.\n"
            note_info += f"The Vinp of {sub_name} is the {other_sub_phase} input.\n"
            note_info += f"The DC operating voltage for Vinn/Vinp is {sub_bias_voltage} V.\n"
    return note_info, sub_bias_voltage


def get_call_info(subcircuits,
                    lib_data_path = "lib_info.tsv", task_data_path = "problem_set.tsv"):
    template = '''```python
from p[ID]_lib import *
# declare the subcircuit
circuit.subcircuit([SUBMODULE_NAME]())
# create a subcircuit instance
circuit.X('1', '[SUBMODULE_NAME]', [INPUT_OUTPUT])
```
'''
    lib_df = pd.read_csv(lib_data_path, delimiter='\t')
    task_df = pd.read_csv(task_data_path, delimiter='\t')
    call_info = ""
    for it, subcircuit in enumerate(subcircuits):
        sub_id = subcircuit
        sub_name = task_df.loc[task_df['Id'] == sub_id, 'Submodule Name'].item()
        input_nodes = task_df.loc[task_df['Id'] == sub_id, 'Input'].item()
        output_nodes = task_df.loc[task_df['Id'] == sub_id, 'Output'].item()
        sub_info = template.replace('[SUBMODULE_NAME]', sub_name)
        input_node_list = input_nodes.split(", ")
        input_node_list = [node for node in input_node_list if "bias" not in node]
        input_info = ", ".join([f"'{input_node}'" for input_node in input_node_list])
        output_node_list = output_nodes.split(", ")
        output_node_list = [node for node in output_node_list if "outn" not in node and "outp" not in node]
        output_info = ", ".join([f"'{output_node}'" for output_node in output_node_list])
        if input_info !=  "" and output_info != "":
            input_output = f"{input_info}, {output_info}"
        elif input_info == "":
            input_output = f"{output_info}"
        else:
            input_output = f"{input_info}"
        sub_info = sub_info.replace('[INPUT_OUTPUT]', input_output)
        sub_info = sub_info.replace('[ID]', str(sub_id))
        call_info += sub_info
    return call_info

global generator
generator = None


def write_pyspice_code(sp_code_path, code_path, op_path):
    sp_code = open(sp_code_path, 'r')
    code = open(code_path, 'w')
    import_template = """import math
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
"""
    code.write(import_template)
    subcircuits_used = set()
    sp_code.seek(0)
    for line in sp_code.readlines():
        line = line.strip()
        if line.startswith('X'):
            parts = line.split()
            if len(parts) >= 3:
                subckt_name = parts[-1]
                subcircuits_used.add(subckt_name)
    for subckt in subcircuits_used:
        code.write(f"from {subckt.lower()} import *\n")
    
    code.write("\n# Create the circuit\n")
    code.write("circuit = Circuit('circuit')\n\n")
    sp_code.seek(0)
    for line in sp_code.readlines():
        line = line.strip()
        if not line or line.startswith('*'):
            continue
        if line.startswith('.subckt') or line.startswith('.ends'):
            continue
        if line.startswith(".model"):
            parts = line.split()
            if len(parts) >= 3:
                model_name = parts[1]
                model_type = parts[2]
                params_str = ' '.join(parts[3:])
                param_dict = parse_model_params(params_str)
                param_args = ', '.join([f"{k}='{v}'" for k, v in param_dict.items()])
                code.write(f"circuit.model('{model_name}', '{model_type}', {param_args})\n")
        elif line.startswith('X'):
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0][1:]  # 去掉'X'
                subckt_name = parts[-1]
                nodes = parts[1:-1]
                code.write(f"circuit.subcircuit({subckt_name}())\n")
                nodes_str = ', '.join([f"'{node}'" for node in nodes])
                code.write(f"circuit.X('{name}', '{subckt_name}', {nodes_str})\n")
        elif line[0].upper() in ['R', 'C', 'L', 'V', 'I']:
            element_type = line[0].upper()
            parts = line.split()
            if len(parts) >= 4:
                name = parts[0][1:]
                n1 = parts[1]
                n2 = parts[2]
                if n1 == '0' or n1.lower() == 'gnd':
                    n1 = 'circuit.gnd'
                else:
                    n1 = f"'{n1}'"
                    
                if n2 == '0' or n2.lower() == 'gnd':
                    n2 = 'circuit.gnd'
                else:
                    n2 = f"'{n2}'"
                if element_type in ['V', 'I'] and parts[3].upper() == 'DC' and len(parts) >= 5:
                    value = f"'{parts[4]}'"
                else:
                    value = f"'{parts[3]}'"
                
                code.write(f"circuit.{element_type}('{name}', {n1}, {n2}, {value})\n")
        elif line.startswith('M'):
            parts = line.split()
            if len(parts) >= 6:
                name = parts[0][1:]
                drain = f"'{parts[1]}'"
                gate = f"'{parts[2]}'"
                source = f"'{parts[3]}'"
                bulk = f"'{parts[4]}'"
                model = parts[5]
                params = {}
                for part in parts[6:]:
                    if '=' in part:
                        key, val = part.split('=')
                        if key.upper() in ['W', 'L']:
                            params[key.lower()] = f"'{val}'"
                
                param_str = ', '.join([f"{k}={v}" for k, v in params.items()])
                if param_str:
                    code.write(f"circuit.MOSFET('{name}', {drain}, {gate}, {source}, {bulk}, model='{model}', {param_str})\n")
                else:
                    code.write(f"circuit.MOSFET('{name}', {drain}, {gate}, {source}, {bulk}, model='{model}')\n")
        elif line.startswith('.'):
            code.write(f"# {line}\n")
    
    code.write("\n# Simulator\n")
    code.write("simulator = circuit.simulator()\n")
    code.write(pyspice_template.replace("[OP_PATH]", op_path))
    code.close()
    sp_code.close()

def parse_model_params(params_str):
    import re
    param_dict = {}
    params_str = params_str.strip('()')
    param_pattern = r'(\w+)\s*=\s*([^\s]+)'
    matches = re.findall(param_pattern, params_str)
    
    for key, value in matches:
        param_dict[key] = value
    
    return param_dict


def optimize_code(code_path, task_id, task_type, task):
    code = ""
    with open(code_path, 'r') as f:
        lines = f.readlines()
        start_marker = "circuit = Circuit"
        end_marker = "simulator = circuit"
        
        recording = False
        for line in lines:
            if start_marker in line:
                recording = True
                code += line
            elif end_marker in line:
                recording = False
                break
            elif recording:
                code += line
    optimize_prompt = optimize_template.replace("[CODE]", code)
    while True:
        try:
            prompt_path = code_path.replace("_success.py", "_optimize_prompt.md")
            with open(prompt_path, 'w') as f:
                f.write(optimize_prompt)
            completion = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system", "content": "You are an analog integrated circuits expert."},
                    {"role": "user", "content": optimize_prompt}
                ],
                temperature=args.temperature)
            if completion is None or type(completion)== str or completion.choices[0].message.content is None:
                time.sleep(30)
            else:
                result = completion.choices[0].message.content
                answer_path = code_path.replace("_success.py", "_optimize_answer.md")
                with open(answer_path, 'w') as f:
                    f.write(result)
                empty_code_error, answer_code = extract_code(result)
                if empty_code_error == 0:
                    break
        except Exception as e:
            print(e)
            print("sleep 30s")
            time.sleep(30)
    answer_code_path = code_path.replace("_success.py", "_optimize.py")
    answer_code_name = answer_code_path.split("/")[-1]
    with open(answer_code_path, 'w') as f:
        f.write(answer_code)
    
    base_path = os.path.dirname(code_path)
    shutil.copy("optimize/circuit_optimizer_helper.py", base_path)
    if "voltage gain" in task.lower():
        target = "gain"
    elif "gbw" in task.lower():
        if "gbw/power" in task.lower():
            target = "fom"
        else:
            target = "gbw"
    else:
        target = "fom"
        
    os.system(f"cd {base_path} && python circuit_optimizer_helper.py {answer_code_name} {target}")

    

def work(task, input, output, task_id, it, background, task_type, flog = None, 
            money_quota = 100, subcircuits = None, normal_vout = None, testbench = None,
            optimize = False):

    global generator

    total_tokens = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    if task_type in complex_task_type:
        bias_voltage = 2.5

    if task_type not in complex_task_type or args.no_tool:
        if args.ngspice:
            fopen = open('prompt_template_ngspice.md','r')
        else:
            fopen = open('prompt_template.md','r')
        
        if args.no_prompt:
            fopen = open('prompt_template_wo_prompt.md', 'r')
        elif args.no_context:
            fopen = open('prompt_template_wo_context.md', 'r')
        elif args.no_chain:
            fopen = open('prompt_template_wo_chain_of_thought.md', 'r')
        elif args.no_tool and task_type in complex_task_type:
            fopen = open('prompt_template_wo_tool.md', 'r')
        
        
        if optimize:
            fopen = open("prompt_template_optimize.md", 'r')
        
        prompt = fopen.read()

        prompt = prompt.replace('[TASK]', task)
        prompt = prompt.replace('[INPUT]', input)
        prompt = prompt.replace('[OUTPUT]', output)
        

    else:
        if task_type not in ["Mixer", "BandPass", "BandStop", "LowPass", "HighPass"]:
            file_name = "prompt_template_complex"
        else:
            file_name = "prompt_template"
        if args.no_context:
            file_name += "_wo_context"
        
        if args.ngspice:
            file_name += "_ngspice"

        if args.no_chain:
            file_name += "_wo_chain_of_thought"
        
        fopen = open(f"{file_name}.md", "r")
        prompt = fopen.read()

        prompt = prompt.replace('[TASK]', task)
        prompt = prompt.replace('[INPUT]', input)
        prompt = prompt.replace('[OUTPUT]', output)
        if task_type == "Oscillator":
            prompt += bias_usage
    prompt_vlm_template = open("vlm_debug_prompt.md", 'r').read()

    if background is not None:
        prompt += "\n\nHint Background: \n" + background + "\n## Answer \n"

    fopen.close()

    fopen_exe_error = open('execution_error.md', 'r')
    prompt_exe_error = fopen_exe_error.read()
    fopen_exe_error.close()

    fopen_sim_error = open('simulation_error.md', 'r')
    prompt_sim_error = fopen_sim_error.read()
    fopen_sim_error.close()

    messages = [
            {"role": "system", "content": "You are an analog integrated circuits expert."},
            {"role": "user", "content": prompt}
            ]
    if "o1" in args.model:
        messages.pop(0)
    elif "deepseek" in args.model:
        messages.pop(0)
        messages[0]["content"] = "You are an analog integrated circuits expert." + messages[0]["content"]
    
    retry = True

    while retry:
        try:
            print("start {} completion".format(args.model))
            completion = client.chat.completions.create(
                model=args.model,
                messages=messages,
                temperature=args.temperature
            )
            if completion is None or type(completion) == str or completion.choices[0].message.content is None:
                time.sleep(30)
            else:
                break
        except openai.APIStatusError as e:
            print("Encountered an APIStatusError. Details:")
            print(e)
            time.sleep(30)

    if "gpt" in args.model or "gemini" in args.model or "deepseek" in args.model or "qwen" in args.model.lower() or "claude" in args.model.lower() or "o1" in args.model:
        answer = completion.choices[0].message.content
    else:
        answer = completion['message']['content']
    
    if hasattr(completion, 'usage'):
        total_tokens += completion.usage.total_tokens
        total_prompt_tokens += completion.usage.prompt_tokens
        total_completion_tokens += completion.usage.completion_tokens
        print(f"\n=== Token Usage (Initial Request) ===")
        print(f"Prompt tokens: {completion.usage.prompt_tokens}")
        print(f"Completion tokens: {completion.usage.completion_tokens}")
        print(f"Total tokens: {completion.usage.total_tokens}")
        print(f"Cumulative total: {total_tokens}")
        print(f"===================================\n")

    if "gpt-3" in args.model:
        model_dir = 'gpt3p5'
    elif "deepseek-chat" in args.model:
        model_dir = "deepseek-v3"
    else:
        model_dir = str(args.model).replace(":", "-").replace("/", "-")
    
    if args.ngspice:
        model_dir += '_ngspice'
    
    if args.no_prompt:
        model_dir += "_no_prompt"
    elif args.no_context:
        model_dir += "_no_context"
    elif args.no_chain:
        model_dir += "_no_chain"
    
    if args.no_vlm:
        model_dir += "_no_vlm"
    
    if args.num_of_retry > 3:
        model_dir += "_retry_{}".format(args.num_of_retry)
    
    if args.no_tool:
        model_dir += "_no_tool"
    
    if not os.path.exists(model_dir):
        try:
            os.mkdir(model_dir)
        except:
            pass
    if not os.path.exists('{}/p{}'.format(model_dir, task_id)):
        try:
            os.mkdir('{}/p{}'.format(model_dir, task_id))
        except:
            pass

    empty_code_error, raw_code = extract_code(answer)
    operating_point_path = "{}/p{}/{}/p{}_{}_{}_op.txt".format(model_dir, task_id, it, task_id, it, 0)
    if not args.ngspice and "simulator = circuit.simulator()" not in raw_code:
        raw_code += "\nsimulator = circuit.simulator()\n"
    if args.ngspice and ".end" in raw_code:
        raw_code = raw_code.replace(".end", "")

    code_id = 0
    if not args.ngspice:
        if task_type != "Oscillator" and task_type != "Mixer":
            code = raw_code + pyspice_template.replace("[OP_PATH]", operating_point_path)
        else:
            code = raw_code
    else:
        code = raw_code

    fwrite_input = open('{}/p{}/p{}_{}_input.txt'.format(model_dir, task_id, task_id, it), 'w')
    fwrite_input.write(prompt)
    fwrite_input.flush()
    fwrite_output = open('{}/p{}/p{}_{}_output.txt'.format(model_dir, task_id, task_id, it), 'w')
    fwrite_output.write(answer)
    fwrite_output.flush()
    
    existing_code_files = os.listdir("{}/p{}".format(model_dir, task_id))
    for existing_code_file in existing_code_files:
        if existing_code_file.endswith(".sp"):
            os.remove("{}/p{}/{}".format(model_dir, task_id, existing_code_file))
        if existing_code_file.endswith("_op.txt"):
            os.remove("{}/p{}/{}".format(model_dir, task_id, existing_code_file))

    if os.path.exists("{}/p{}/{}".format(model_dir, task_id, it)):
        existing_code_files = os.listdir("{}/p{}/{}".format(model_dir, task_id, it))
        for existing_code_file in existing_code_files:
            if os.path.isfile("{}/p{}/{}/{}".format(model_dir, task_id, it, existing_code_file)):
                try:
                    os.remove("{}/p{}/{}/{}".format(model_dir, task_id, it, existing_code_file))
                except:
                    pass

    while code_id < args.num_of_retry:
        messages.append({"role": "assistant", "content": answer})

        if not os.path.exists("{}/p{}/{}".format(model_dir, task_id, it)):
            os.mkdir("{}/p{}/{}".format(model_dir, task_id, it))

        code_path = '{}/p{}/{}/p{}_{}_{}.py'.format(model_dir, task_id, it, task_id, it, code_id)
        if args.ngspice:
            code_path = code_path.replace(".py", ".sp")
        fwrite_code = open(code_path, 'w')
        fwrite_code.write(code)
        fwrite_code.close()

        if args.ngspice:
            sp_code_path = code_path
            code_path = code_path.replace(".sp", ".py")
            write_pyspice_code(sp_code_path, code_path, operating_point_path)
            answer_code = open(code_path, 'r').read()
            code = answer_code
        else:
            answer_code = code
        
        if optimize:
            shutil.copy("mosfet_model/model.py", "/".join(code_path.split("/")[:-1]))
        
        if task_type in complex_task_type and not args.no_tool:
            shutil.copy("opamp.py", "/".join(code_path.split("/")[:-1]))
        
        execution_error, simulation_error, execution_error_info, floating_node = run_code(code_path)

        dc_sweep_error = 0
        dc_sweep_success = 0

        if execution_error == 0 and simulation_error == 0:
            if task_type not in complex_task_type:
                # basic task
                _, code_netlist = None, answer_code
                code_netlist += output_netlist_template
                code_netlist_path = "{}/p{}/{}/p{}_{}_{}_netlist_gen.py".format(model_dir, task_id, it, task_id, it, code_id)
                fwrite_code_netlist = open(code_netlist_path, 'w')
                fwrite_code_netlist.write(code_netlist)
                fwrite_code_netlist.close()
                
                netlist_path = "{}/p{}/{}/p{}_{}_{}_netlist.sp".format(model_dir, task_id, it, task_id, it, code_id)
                result = subprocess.run(["python", "-u", code_netlist_path], check=True, text=True, 
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
                netlist_file_path = "{}/p{}/{}/p{}_{}_{}_netlist.sp".format(model_dir, task_id, it, task_id, it, code_id)
                fwrite_netlist = open(netlist_file_path, 'w')
                fwrite_netlist.write("\n".join(result.stdout.split("\n")[1:]))
                fwrite_netlist.close()

                ## special for Opamp: dc sweep
                
                if "Opamp" in task_type or "Amplifier" in task_type:
                    vinn_name = "in"
                    vinp_name = "inp"
                    netlist_content = open(netlist_file_path, 'r').read()
                    vinn_name, vinp_name = get_vin_name(netlist_content, task_type)
                    dc_sweep_code_path = '{}/p{}/{}/p{}_{}_{}_dc_sweep.py'.format(model_dir, task_id, it, task_id, it, code_id)
                    dc_file_path = '{}/p{}/{}/p{}_{}_{}_dc.txt'.format(model_dir, task_id, it, task_id, it, code_id)
                    _, dc_sweep_code = None, answer_code
                    if "simulator = circuit.simulator()" not in dc_sweep_code:
                        dc_sweep_code += "\nsimulator = circuit.simulator()\n"
                    if task_type == "Opamp":
                        dc_sweep_code = connect_vinn_vinp(dc_sweep_code, vinn_name, vinp_name)
                    dc_sweep_code += dc_sweep_template.replace("[IN_NAME]", vinn_name).replace("[DC_PATH]", dc_file_path)
                    fwrite_dc_sweep_code = open(dc_sweep_code_path, 'w')
                    fwrite_dc_sweep_code.write(dc_sweep_code)
                    fwrite_dc_sweep_code.close()
                    try:
                        subprocess.run(["python", "-u", dc_sweep_code_path], check=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
                        target_voltage = 2.5 if not optimize else 0.6
                        dc_sweep_error, best_voltage = get_best_voltage(dc_file_path, target_voltage)
                        file_name = "{}/p{}/{}/p{}_{}_{}_best_voltage.txt".format(model_dir, task_id, it, task_id, it, code_id)
                        with open(file_name, 'w') as f:
                            f.write(str(best_voltage))
                        assert dc_sweep_error == 0
                        os.rename(code_path, code_path + ".bak")
                        _, raw_code = None, answer_code
                        if "simulator = circuit.simulator()" not in raw_code:
                            raw_code += "\nsimulator = circuit.simulator()\n"
                        new_code = replace_voltage(raw_code, best_voltage, vinn_name, vinp_name)
                        # write new op analysis code
                        with open(f"{code_path}", "w") as f:
                            f.write(new_code)
                        execution_error_1, simulation_error_1, execution_error_info_1, floating_node_1 = run_code(code_path)
                        assert execution_error_1 == 0
                        assert simulation_error_1 == 0
                        # All dc sweep passed
                        # generate a new netlist with the best voltage, replace _gen.py and .sp
                        new_code_netlist = new_code + output_netlist_template
                        code_netlist_path = "{}/p{}/{}/p{}_{}_{}_netlist_gen.py".format(model_dir, task_id, it, task_id, it, code_id)
                        fwrite_code_netlist = open(code_netlist_path, 'w')
                        fwrite_code_netlist.write(new_code_netlist)
                        fwrite_code_netlist.close()
                        netlist_path = "{}/p{}/{}/p{}_{}_{}_netlist.sp".format(model_dir, task_id, it, task_id, it, code_id)
                        result = subprocess.run(["python", "-u", code_netlist_path], check=True, text=True, 
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
                        netlist_file_path = "{}/p{}/{}/p{}_{}_{}_netlist.sp".format(model_dir, task_id, it, task_id, it, code_id)
                        fwrite_netlist = open(netlist_file_path, 'w')
                        fwrite_netlist.write("\n".join(result.stdout.split("\n")[1:]))
                        fwrite_netlist.close()
                        dc_sweep_success = 1
                    except:
                        if os.path.exists(code_path + ".bak"):
                            shutil.copy(code_path + ".bak", code_path)

                warning, warning_message = check_netlist(netlist_path, operating_point_path, input, output, task_id, task_type, optimize)
                if warning == 0:
                    func_error, func_error_message = check_function(task_id, code_path, task_type)
                    func_error_message = func_error_message.replace("Unsupported Ngspice version 38", "")
                    func_error_message = func_error_message.replace("Unsupported Ngspice version 36", "")
                    if func_error ==0:
                        os.rename(code_path, code_path.rsplit(".", 1)[0] + "_success.py")
                        token_info_path = f'{model_dir}/p{task_id}/{it}/token_info_retry{code_id}.txt'
                        with open(token_info_path, 'w') as ftmp_write:
                            ftmp_write.write(f"Retry: {code_id}\n")
                            ftmp_write.write(f"Total tokens: {total_tokens}\n")
                            ftmp_write.write(f"Total prompt tokens: {total_prompt_tokens}\n")
                            ftmp_write.write(f"Total completion tokens: {total_completion_tokens}\n")
                            ftmp_write.write(f"Status: Success\n")
                        
                        optimize_code_path = code_path.rsplit(".", 1)[0] + "_success.py"
                        if optimize:
                            optimize_code(optimize_code_path, task_id, task_type, task)
                        break
            else:
                # complex task
                pyspice_template_complex = open(f"problem_check/{task_type}.py", "r").read()
                figure_path = "{}/p{}/{}/p{}_{}_{}_figure".format(model_dir, task_id, it, task_id, it, code_id)

                if not args.ngspice:
                    code = raw_code + pyspice_template_complex.replace("[FIGURE_PATH]", figure_path).replace('[BIAS_VOLTAGE]', str(bias_voltage))
                else:
                    # code extract before line 'simulator = circuit.simulator()'
                    code = code.split("simulator = circuit.simulator()")[0] + "simulator = circuit.simulator()\n" + pyspice_template_complex.replace("[FIGURE_PATH]", figure_path).replace('[BIAS_VOLTAGE]', str(bias_voltage))
                
                if "import math" not in code:
                    code = "import math\n" + code
                shutil.copy(code_path, code_path.rsplit(".", 1)[0] + "_op.py")
                print("copy file {} to {}".format(code_path, code_path.rsplit(".", 1)[0] + "_op.py"))
                with open(f"{code_path}", "w") as f:
                    f.write(code)
                execution_error, simulation_error, execution_error_info, floating_node = run_code(code_path)
                if execution_error == 0 and simulation_error == 0:
                    os.rename(code_path, code_path.rsplit(".", 1)[0]+"_success.py")
                    token_info_path = f'{model_dir}/p{task_id}/{it}/token_info_retry{code_id}.txt'
                    with open(token_info_path, 'w') as ftmp_write:
                        ftmp_write.write(f"Retry: {code_id}\n")
                        ftmp_write.write(f"Total tokens: {total_tokens}\n")
                        ftmp_write.write(f"Total prompt tokens: {total_prompt_tokens}\n")
                        ftmp_write.write(f"Total completion tokens: {total_completion_tokens}\n")
                        ftmp_write.write(f"Status: Success\n")
                    
                    break
        
        # Ignore the compatible error
        execution_error_info = execution_error_info.replace("Unsupported Ngspice version 38", "")
        execution_error_info = execution_error_info.replace("Unsupported Ngspice version 36", "")

        if dc_sweep_error == 1:
            new_prompt = "According to dc sweep analysis, changing the input voltage does not change the output voltage. Please check the netlist and rewrite the complete code.\n"
            new_prompt += "Reference operating point:\n"
            op_content = open(operating_point_path, 'r').read()
            new_prompt += op_content

            ftmp = open("{}/p{}/{}/dc_sweep_error_{}".format(model_dir, task_id, it, code_id), "w")
            ftmp.close()
        else:
            if dc_sweep_success == 1:
                new_prompt = f"According to dc sweep analysis, the best input voltage is {best_voltage}. Please use this voltage.\n"
            else:
                new_prompt = ""
            if empty_code_error == 1:
                new_prompt += "There is no complete code in your reply. Please generate a complete code."
                ftmp = open("{}/p{}/{}/empty_error_{}".format(model_dir, task_id, it, code_id), "w")
                ftmp.close()
            elif simulation_error == 1:
                new_prompt += prompt_sim_error.replace("[NODE]", floating_node)
                ftmp = open("{}/p{}/{}/simulation_error_{}".format(model_dir, task_id, it, code_id), "w")
                ftmp.close()
            elif execution_error == 1:
                figure_path = "{}/p{}/{}/p{}_{}_{}_figure.png".format(model_dir, task_id, it, task_id, it, code_id)
                if os.path.exists(figure_path) and client_vlm is not None and code_id < args.num_of_retry - 1:
                    
                    prompt_vlm = prompt_vlm_template
                    prompt_vlm = prompt_vlm.replace("[TASK]", task)
                    prompt_vlm = prompt_vlm.replace("[NORMAL_VOUT]", normal_vout)
                    prompt_vlm = prompt_vlm.replace("[TESTBENCH]", testbench)
                    prompt_vlm_path = "{}/p{}/{}/p{}_{}_{}_prompt_vlm.md".format(model_dir, task_id, it, task_id, it, code_id)
                    with open(prompt_vlm_path, "w") as f:
                        f.write(prompt_vlm)
                    base64_image = encode_image(figure_path)
                    messages_vlm = [
                        {"role": "system", "content": "You are an analog integrated circuits expert."},
                        {"role": "user", "content": 
                            [   {"type": "text", "text": prompt_vlm},
                                {"type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}",
                                        "detail": "auto"
                                    }
                                }
                            ]
                        }
                    ]
                    vlm_retry = 3
                    while vlm_retry > 0:
                        completion_vlm = client_vlm.chat.completions.create(
                            model = vlm_model,
                            messages = messages_vlm,
                            temperature = 0.0,
                        )
                        if (completion_vlm is None or
                            isinstance(completion_vlm, str) or
                            not hasattr(completion_vlm, 'choices') or
                            not completion_vlm.choices or
                            completion_vlm.choices[0].message.content is None):
                            time.sleep(30)
                        else:
                            answer_vlm = completion_vlm.choices[0].message.content
                            break
                        vlm_retry -= 1
                    answer_vlm_path = "{}/p{}/{}/p{}_{}_{}_answer_vlm.md".format(model_dir, task_id, it, task_id, it, code_id)
                    with open(answer_vlm_path, "w") as f:
                        f.write(answer_vlm)
                    execution_error_info += "\n\nWaveform Analysis:\n" + answer_vlm
                
                new_prompt += "\n" + prompt_exe_error.replace("[ERROR]", execution_error_info)
                ftmp = open("{}/p{}/{}/execution_error_{}".format(model_dir, task_id, it, code_id), "w")
                ftmp.close()
            elif warning == 1:
                warning_lines = warning_message.splitlines()
                if len(warning_lines) > 15:
                    warning_message = '\n'.join(warning_lines[:15]) + "\n... (message truncated)"
                new_prompt += warning_message
                ftmp = open("{}/p{}/{}/mosfet_connection_error_{}".format(model_dir, task_id, it, code_id), "w")
                ftmp.close()
            elif func_error == 1:
                func_error_lines = func_error_message.splitlines()
                if len(func_error_lines) > 15:
                    func_error_message = '\n'.join(func_error_lines[:15]) + "\n... (message truncated)"
                new_prompt += func_error_message
                new_prompt += "\nPlease rewrite the corrected complete code."
                ftmp = open("{}/p{}/{}/function_error_{}".format(model_dir, task_id, it, code_id), "w")
                ftmp.close()
            else:
                assert False

        token_info_path = f'{model_dir}/p{task_id}/{it}/token_info_retry{code_id}.txt'
        with open(token_info_path, 'w') as ftmp_write:
            ftmp_write.write(f"Retry: {code_id}\n")
            ftmp_write.write(f"Total tokens: {total_tokens}\n")
            ftmp_write.write(f"Total prompt tokens: {total_prompt_tokens}\n")
            ftmp_write.write(f"Total completion tokens: {total_completion_tokens}\n")
            ftmp_write.write(f"Status: Failed\n")
        
        code_id += 1
        if code_id >= args.num_of_retry:
            break
        messages.append({"role": "user", "content": new_prompt})

        retry = True
        while retry:
            try:
                completion = client.chat.completions.create(
                    model=args.model,
                    messages=messages,
                    temperature=args.temperature
                )
                if completion is None or type(completion) == str or completion.choices[0].message.content is None:
                    time.sleep(30)
                else:
                    break
            except openai.APIStatusError as e:
                print("Encountered an APIStatusError. Details:")
                print(e)
                time.sleep(30)

        fwrite_input.write("\n----------\n")
        fwrite_input.write(new_prompt)
        fwrite_input.flush()

        if "gpt" in args.model or "gemini" in args.model or "deepseek" in args.model or "qwen" in args.model.lower() or "claude" in args.model.lower() or "o1" in args.model:
            answer = completion.choices[0].message.content
        else:
            answer = completion['message']['content']
        
        if hasattr(completion, 'usage'):
            total_tokens += completion.usage.total_tokens
            total_prompt_tokens += completion.usage.prompt_tokens
            total_completion_tokens += completion.usage.completion_tokens
            print(f"\n=== Token Usage (Retry {code_id}) ===")
            print(f"Prompt tokens: {completion.usage.prompt_tokens}")
            print(f"Completion tokens: {completion.usage.completion_tokens}")
            print(f"Total tokens: {completion.usage.total_tokens}")
            print(f"Cumulative total: {total_tokens}")
            print(f"===================================\n")

        fwrite_output.write("\n----------\n")
        fwrite_output.write(answer)

        empty_code_error,         raw_code = extract_code(answer)

        operating_point_path = "{}/p{}/{}/p{}_{}_{}_op.txt".format(model_dir, task_id, it, task_id, it, code_id)
        if "simulator = circuit.simulator()" not in raw_code:
            raw_code += "\nsimulator = circuit.simulator()\n"
        code = raw_code + pyspice_template.replace("[OP_PATH]", operating_point_path)

    fwrite = open('{}/p{}/{}/p{}_{}_messages.txt'.format(model_dir, task_id, it, task_id, it), 'w')
    fwrite.write(str(messages))
    fwrite.close()
    fwrite_input.close()
    fwrite_output.close()

    final_token_summary_path = f'{model_dir}/p{task_id}/{it}/token_summary_final.txt'
    with open(final_token_summary_path, 'w') as f:
        f.write(f"Task ID: {task_id}\n")
        f.write(f"Iteration: {it}\n")
        f.write(f"Total retries: {code_id}\n")
        f.write(f"=" * 50 + "\n")
        f.write(f"Total tokens used: {total_tokens}\n")
        f.write(f"Total prompt tokens: {total_prompt_tokens}\n")
        f.write(f"Total completion tokens: {total_completion_tokens}\n")
        f.write(f"=" * 50 + "\n")

    print(f"\n=== Final Token Usage Summary ===")
    print(f"Total retries: {code_id}")
    print(f"Total prompt tokens: {total_prompt_tokens}")
    print(f"Total completion tokens: {total_completion_tokens}")
    print(f"Total tokens: {total_tokens}")
    print(f"Token info saved to: {final_token_summary_path}")
    print(f"================================\n")

    return money_quota

def get_retrieval(task, task_id):
    prompt = open('retrieval_prompt.md', 'r').read()
    prompt = prompt.replace('[TASK]', task)
    messages = [
            {"role": "system", "content": "You are an analog integrated circuits expert."},
            {"role": "user", "content": prompt}
        ]
    if "gpt" in args.model and args.retrieval:
        try:
            completion = client.chat.completions.create(
                model=args.model,
                messages=messages,
                temperature=args.temperature
            )
        except openai.APIStatusError as e:
            print("Encountered an APIStatusError. Details:")
            print(e)
            print("sleep 30 seconds")
            time.sleep(30)
        answer = completion.choices[0].message.content
        fretre_path = os.path.join(args.model.replace("-", ""), f"p{str(task_id)}", "retrieve.txt")
        fretre = open(fretre_path, "w")
        fretre.write(answer)
        fretre.close()
        regex = r".*?```.*?\n(.*?)```"
        matches = re.finditer(regex, answer, re.DOTALL)
        first_match = next(matches, None)
        match_res = first_match.group(1)
        subcircuits = eval(match_res)
    else:
        # use default subcircuits
        subcircuits = [11]
    return subcircuits



def main():
    data_path = 'problem_set.tsv'
    df = pd.read_csv(data_path, delimiter='\t')
    remaining_money = 2
    for index, row in df.iterrows():
        circuit_id = row['Id']
        if circuit_id != args.task_id:
            continue
        for it in range(args.num_of_done, args.num_per_task):
            subcircuits = None
            work(row['Circuit'], row['Input'].strip(), row['Output'].strip(), circuit_id, it,
                 None, row['Type'], None, money_quota=remaining_money,
                 subcircuits=subcircuits, normal_vout=row['Normal'], testbench=row['Testbench'],
                 optimize=circuit_id > 50)


if __name__ == "__main__":
    main()
