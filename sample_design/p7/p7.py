from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
# Define the circuit
circuit = Circuit('CMOS Inverter')
# 1. Power supply
circuit.V('dd', 'Vdd', circuit.gnd, 5@u_V)
# 2. Define models for NMOS and PMOS with typical parameters
# These are generic models; for detailed design, use specific parameters
circuit.model('nmos', 'nmos', level=1, vto=0.7, kp=2e-3)  # NMOS threshold ~0.7V
circuit.model('pmos', 'pmos', level=1, vto=-0.7, kp=1.5e-3)  # PMOS threshold ~-0.7V
# 3. Add a voltage source for Vin
# For example, a DC voltage at 0V (logic LOW), can be swept later
circuit.V('in', 'Vin', circuit.gnd, 0@u_V)
# 4. Create NMOS transistor
# Correct order: name, drain, gate, source, bulk, model, w, l
circuit.MOSFET('M_N', 'Vout', 'Vin', 'GND', 'GND', model='nmos', w=10e-6, l=1e-6)
# 5. Create PMOS transistor
# Drain connected to Vout, gate to Vin, source to Vdd
circuit.MOSFET('M_P', 'Vout', 'Vin', 'Vdd', 'Vdd', model='pmos', w=10e-6, l=1e-6)
# 6. (Optional) Add a load resistor if needed for analysis
# Not necessary for basic inverter function
# 7. Ready for simulation
simulator = circuit.simulator()

try:
    analysis = simulator.operating_point()
    fopen = open("sample_design/p7/p7_op.txt", "w")
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



