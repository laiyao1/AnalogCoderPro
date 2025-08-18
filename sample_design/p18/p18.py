from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('Single-Stage Differential Opamp with Resistive Loads')
# Define NMOS model
circuit.model('nmos_model', 'nmos', level=1, kp=100e-6, vto=0.5)
# Power Supply
circuit.V('dd', 'Vdd', circuit.gnd, 5.0)
# Input voltages (for DC operating point)
circuit.V('inp', 'Vinp', circuit.gnd, "dc 1.0 ac 1n")
circuit.V('inn', 'Vinn', circuit.gnd, "dc 1.0 ac 1n")
# Bias voltage for tail current source
circuit.V('bias', 'Vbias', circuit.gnd, 1.0) # Vbias = Vth + 0.5V = 1.0V
# Differential Pair
# M1: Drain=Vout, Gate=Vinp, Source=SourceDiff, Bulk=SourceDiff
circuit.MOSFET('1', 'Vout', 'Vinp', 'SourceDiff', 'SourceDiff', model='nmos_model', w=50e-6, l=1e-6)
# M2: Drain=Drain2, Gate=Vinn, Source=SourceDiff, Bulk=SourceDiff
circuit.MOSFET('2', 'Drain2', 'Vinn', 'SourceDiff', 'SourceDiff', model='nmos_model', w=50e-6, l=1e-6)
# Tail current source
# Mtail: Drain=SourceDiff, Gate=Vbias, Source=0, Bulk=0
circuit.MOSFET('tail', 'SourceDiff', 'Vbias', circuit.gnd, circuit.gnd, model='nmos_model', w=20e-6, l=1e-6)
# Load resistors
# R1: Vdd to Vout (drain of M1)
circuit.R('1', 'Vdd', 'Vout', 10@u_kΩ)
# R2: Vdd to Drain2 (drain of M2)
circuit.R('2', 'Vdd', 'Drain2', 10@u_kΩ)
simulator = circuit.simulator()

try:
    analysis = simulator.operating_point()
    fopen = open("sample_design/p18/p18_op.txt", "w")
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