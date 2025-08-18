from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('NMOS Inverter with Resistor Load')
# Define NMOS Model
circuit.model('nmos', 'nmos', level=1, kp=200e-6, vto=0.7)
# Power supply
circuit.V('dd', 'Vdd', circuit.gnd, 5@u_V)
# Input node
# Vin will be a voltage source or a test signal, for now we set it as a DC source
circuit.V('in', 'Vin', circuit.gnd, 0@u_V)  # Can be varied during simulation
# Resistor R between Vdd and Vout
circuit.R('load', 'Vdd', 'Vout', 100@u_kΩ)  # 100kΩ resistor
# NMOS transistor M1
# Drain connected to Vout
# Gate connected to Vin
# Source connected to ground
circuit.MOSFET('M1', 'Vout', 'Vin', circuit.gnd, circuit.gnd, model='nmos')
# The above assumes default width and length for the transistor
# For clarity, specify device parameters if needed
# For example:
# circuit.MOSFET('M1', 'Vout', 'Vin', circuit.gnd, circuit.gnd, model='nmos', w=10e-6, l=1e-6)
simulator = circuit.simulator()

try:
    analysis = simulator.operating_point()
    fopen = open("sample_design/p6/p6_op.txt", "w")
    for node in analysis.nodes.values(): 
        fopen.write(f"{str(node)}\t{float(analysis[str(node)][0]):.6f}\n")
    fopen.close()
except Exception as e:
    print("Analysis failed due to an error:")
    print(str(e))

analysis = simulator.operating_point()
for node in analysis.nodes.values(): 
    print(f"{str(node)}\t{float(analysis[str(node)][0]):.6f}")
vin_name = ""
for element in circuit.elements:
    for pin in element.pins:
        if "vin" in str(pin.node).lower() and element.name.lower().startswith("v"):
            vin_name = element.name
            break

circuit.element(vin_name).dc_value = "5"

simulator2 = circuit.simulator()
analysis2 = simulator2.operating_point()


node = 'vout'

has_node = False
# find any node with "vout"
for element in circuit.elements:
    # get pins
    for pin in element.pins:
        if "vout" == str(pin.node).lower():
            has_node = True
            break
if has_node == False:
    for element in circuit.elements:
        for pin in element.pins:
            if "vout" in str(pin.node).lower():
                node = str(pin.node)
                break

vout2 = float(analysis2[node][0])

circuit.element(vin_name).dc_value = "0"

simulator3 = circuit.simulator()
analysis3 = simulator3.operating_point()

vout3 = float(analysis3[node][0])

import sys
if vout2 <= 2.5 and vout3 >= 2.5 and vout3 - vout2 >= 1.0:
    print("The circuit functions correctly.\n")
    sys.exit(0)

print("The circuit does not function correctly.\n"
    "It can not invert the input voltage.\n"
    f"When input is 5V, output is {vout2:.2f}V.\n"
    f"When input is 0V, output is {vout3:.2f}V.\n"
    "Please fix the wrong operating point.\n")

sys.exit(2)



