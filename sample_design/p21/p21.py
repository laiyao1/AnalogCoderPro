from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('Single-Stage Telescopic Cascode Opamp')
# MOSFET Models
circuit.model('nmos_model', 'nmos', level=1, kp=100e-6, vto=0.5)
circuit.model('pmos_model', 'pmos', level=1, kp=50e-6, vto=-0.5)
# Power Supply
circuit.V('dd', 'Vdd', circuit.gnd, 5.0)
# Input sources (DC bias for now)
circuit.V('inp', 'Vinp', circuit.gnd, "dc 1.0 ac 1n")
circuit.V('inn', 'Vinn', circuit.gnd, "dc 1.0 ac 1n")
# Bias voltages (choose values to ensure all devices are in saturation)
circuit.V('bias1', 'Vbias1', circuit.gnd, 0.7)   # Tail NMOS bias (Vgs > Vth)
circuit.V('bias2', 'Vbias2', circuit.gnd, 1.2)   # NMOS cascode bias (> Vth)
circuit.V('bias3', 'Vbias3', circuit.gnd, 4.0)   # PMOS load bias (Vdd - |Vth| - margin)
circuit.V('bias4', 'Vbias4', circuit.gnd, 3.5)   # PMOS cascode bias (Vdd - |Vth| - margin)
# Tail current source NMOS
circuit.MOSFET('9', 'S_tail', 'Vbias1', circuit.gnd, circuit.gnd, model='nmos_model', w=30e-6, l=1e-6)
# Differential input NMOS
circuit.MOSFET('1', 'N1', 'Vinp', 'S_tail', 'S_tail', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('2', 'N2', 'Vinn', 'S_tail', 'S_tail', model='nmos_model', w=50e-6, l=1e-6)
# NMOS cascode
circuit.MOSFET('3', 'Voutp', 'Vbias2', 'N1', 'N1', model='nmos_model', w=50e-6, l=1e-6)
circuit.MOSFET('4', 'Vout', 'Vbias2', 'N2', 'N2', model='nmos_model', w=50e-6, l=1e-6)
# PMOS active load
circuit.MOSFET('5', 'Voutp', 'Vbias3', 'S5', 'S5', model='pmos_model', w=70e-6, l=1e-6)
circuit.MOSFET('6', 'Vout', 'Vbias3', 'S6', 'S6', model='pmos_model', w=70e-6, l=1e-6)
# PMOS cascode
circuit.MOSFET('7', 'S5', 'Vbias4', 'Vdd', 'Vdd', model='pmos_model', w=70e-6, l=1e-6)
circuit.MOSFET('8', 'S6', 'Vbias4', 'Vdd', 'Vdd', model='pmos_model', w=70e-6, l=1e-6)
simulator = circuit.simulator()

try:
    analysis = simulator.operating_point()
    fopen = open("sample_design/p21/p21_op.txt", "w")
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

node = "Vout"

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

print(f"Common-Mode Gain (Av) at 100 Hz: {gain}")

vinn_name = ""
for element in circuit.elements:
    # print("element name", element.name)
    # for pin in element.pins:
    #     print("pin name", pin.node)
    if "vinn" in [str(pin.node).lower() for pin in element.pins] and element.name.lower().startswith("v"):
        vinn_name = element.name


circuit.element(vinn_name).dc_value += " 180"

simulator2 = circuit.simulator()
analysis2 = simulator2.ac(start_frequency=frequency, stop_frequency=frequency, 
                        number_of_points=1, variation='dec')

output_voltage2 = np.abs(analysis2[node].as_ndarray()[0])
gain2 = output_voltage2 / (1e-9)

print(f"Differential-Mode Gain (Av) at 100 Hz: {gain2}")

required_gain = 1e-5
import sys

if gain < gain2 - 1e-5 and gain2 > required_gain:
    print("The circuit functions correctly at 100 Hz.\n")
    sys.exit(0)

if gain >= gain2 - 1e-5:
    print("Common-Mode gain is larger than Differential-Mode gain.\n")

if gain2 < required_gain:
    print("Differential-Mode gain is smaller than 1e-5.\n")

print("The circuit does not function correctly.\n"
    "Please fix the wrong operating point.\n")
sys.exit(2)