from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('Three-Stage Common-Source Amplifier with Proper Biasing')
# Define NMOS model parameters
circuit.model('nmos_model', 'nmos', level=1, kp=100e-6, vto=0.5)
# Power supply
circuit.V('dd', 'Vdd', circuit.gnd, 5.0)
# Input voltage source
circuit.V('in', 'Vin', circuit.gnd, "dc 1.0 ac 1n")
# Bias voltage for drain of M1 (gate of M2)
circuit.V('bias_M2_gate', 'Bias_M2', 'Drain1', 2.0)  # 2V bias to ensure M2 is on
# Load resistors
R1_value = 10e3  # 10kΩ
R2_value = 10e3
R3_value = 10e3
# First stage: M1
circuit.MOSFET('M1', 'Drain1', 'Vin', circuit.gnd, circuit.gnd, model='nmos_model', w=50e-6, l=1e-6)
circuit.R('R1', 'Drain1', 'Vdd', R1_value)
# Second stage: M2
circuit.MOSFET('M2', 'Drain2', 'Bias_M2', 'Drain1', circuit.gnd, model='nmos_model', w=50e-6, l=1e-6)
circuit.R('R2', 'Drain2', 'Vdd', R2_value)
# Third stage: M3
circuit.MOSFET('M3', 'Vout', 'Drain2', circuit.gnd, circuit.gnd, model='nmos_model', w=50e-6, l=1e-6)
circuit.R('R3', 'Vout', 'Vdd', R3_value)
# Simulation setup
simulator = circuit.simulator()

try:
    analysis = simulator.operating_point()
    fopen = open("sample_design/p2/p2_op.txt", "w")
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