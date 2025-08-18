from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
# Define the circuit
circuit = Circuit('Single-Stage Common-Gate Amplifier - Corrected')
# Define NMOS model
circuit.model('nmos_model', 'nmos', level=1, kp=100e-6, vto=0.5)
# Power supply
circuit.V('dd', 'Vdd', circuit.gnd, 5.0)  # 5V supply
# Bias voltage at gate to set the bias point
circuit.V('bias', 'Vbias', circuit.gnd, 2.0)  # Higher bias voltage to ensure V_GS > V_TH
# Input signal at source (Vin)
# During simulation, Vin will be a time-varying source or DC value
# Here, for operating point, we can set a DC value, say 0.5V
# For transient analysis, a voltage source with AC or waveform can be used
# For now, set a DC value for initial operating point
circuit.V('in', 'Vin', circuit.gnd, "dc 0.5 ac 1n")
# Device: M1 (NMOS)
# Drain connected to Vdd through Rload
# Gate connected to Vbias
# Source connected to Vin
W = 50e-6
L = 1e-6
circuit.MOSFET('M1', 'Vout', 'Vbias', 'Vin', 'Vin', model='nmos_model', w=W, l=L)
# Load resistor at drain
R_value = 10e3  # 10 kΩ
circuit.R('load', 'Vout', 'Vdd', R_value)
# Note: For operating point analysis, Vin is DC at 0.5V
# For transient analysis, replace 'Vin' with a time-dependent source
# Initialize simulator
simulator = circuit.simulator()

try:
    analysis = simulator.operating_point()
    fopen = open("sample_design/p4/p4_op.txt", "w")
    for node in analysis.nodes.values(): 
        fopen.write(f"{str(node)}\t{float(analysis[str(node)][0]):.6f}\n")
    fopen.close()
except Exception as e:
    print("Analysis failed due to an error:")
    print(str(e))

simulator_id = circuit.simulator()
mosfet_names = []
import PySpice.Spice.BasicElement
for element in circuit.elements:
    if isinstance(element, PySpice.Spice.BasicElement.Mosfet):
        mosfet_names.append(element.name)

mosfet_name_ids = []
for mosfet_name in mosfet_names:
    mosfet_name_ids.append(f"@{mosfet_name}[id]")

simulator_id.save_internal_parameters(*mosfet_name_ids)
analysis_id = simulator_id.operating_point()

id_correct = 1
for mosfet_name in mosfet_names:
    mosfet_id = float(analysis_id[f"@{mosfet_name}[id]"][0])
    if mosfet_id < 1e-5:
        id_correct = 0
        print("The circuit does not function correctly. "
          "the current I_D for {} is 0. ".format(mosfet_name)
          .format(mosfet_name))

if id_correct == 0:
    print("Please fix the wrong operating point.\n")
    sys.exit(2)


frequency = 100@u_Hz
analysis = simulator.ac(start_frequency=frequency, stop_frequency=frequency*10, 
    number_of_points=2, variation='dec')

import numpy as np

node = 'vout'

# find whether vout in the circuit

has_node = False
# find any node with "vout"
for element in circuit.elements:
    # get pins
    for pin in element.pins:
        if "vout" == str(pin.node).lower():
            node = str(pin.node)
            has_node = True
            break

if has_node == False:
    for element in circuit.elements:
        for pin in element.pins:
            if "vout" in str(pin.node).lower():
                node = str(pin.node)
                break

output_voltage = analysis[node].as_ndarray()[0]
gain = np.abs(output_voltage / (1e-9))

print(f"Voltage Gain (Av) at 100 Hz: {gain}")

required_gain = 1e-5
import sys
if gain > required_gain:
    print("The circuit functions correctly at 100 Hz.\n")
    sys.exit(0)
else:
    print("The circuit does not function correctly.\n"
          "the gain is less than 1e-5.\n"
          "Please fix the wrong operating point.\n")
    sys.exit(2)