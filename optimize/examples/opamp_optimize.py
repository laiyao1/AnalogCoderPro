from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from model import nmos_params, pmos_params
def create_circuit(params):
    circuit = Circuit('Telescopic Cascode Amplifier')
    # Define the MOSFET models
    circuit.model('nmos_model', 'nmos', **nmos_params)
    circuit.model('pmos_model', 'pmos', **pmos_params)
    # Power Supply (fixed)
    circuit.V('dd', 'Vdd', circuit.gnd, 1.2)  # 1.2V power supply
    # Bias Voltages (parameterized)
    circuit.V('bn1', 'Vbn1', circuit.gnd, params['v_bn1'])  # Bias for NMOS cascode
    circuit.V('bn2', 'Vbn2', circuit.gnd, params['v_bn2'])  # Bias for NMOS current source
    circuit.V('bp1', 'Vbp1', circuit.gnd, params['v_bp1'])  # Bias for PMOS cascode
    circuit.V('bp2', 'Vbp2', circuit.gnd, params['v_bp2'])  # Bias for PMOS current source
    # Input Differential Signals (fixed)
    circuit.V('inp', 'Vinp', circuit.gnd, 0.9)  # Common mode input voltage
    circuit.V('inn', 'Vinn', circuit.gnd, 0.9)  # Common mode input voltage
    # Input Differential Pair (NMOS)
    circuit.MOSFET('1', 'node1', 'Vinp', 'node_tail', 'node_tail',
                  model='nmos_model', w=params['w_M1'], l=0.045e-6)
    circuit.MOSFET('2', 'node2', 'Vinn', 'node_tail', 'node_tail',
                  model='nmos_model', w=params['w_M2'], l=0.045e-6)
    # NMOS Cascode Devices
    circuit.MOSFET('3', 'node3', 'Vbn1', 'node1', 'node1',
                  model='nmos_model', w=params['w_M3'], l=0.045e-6)
    circuit.MOSFET('4', 'Vout', 'Vbn1', 'node2', 'node2',
                  model='nmos_model', w=params['w_M4'], l=0.045e-6)
    # PMOS Cascode Load
    circuit.MOSFET('5', 'node3', 'Vbp1', 'node5', 'node5',
                  model='pmos_model', w=params['w_M5'], l=0.045e-6)
    circuit.MOSFET('6', 'Vout', 'Vbp1', 'node6', 'node6',
                  model='pmos_model', w=params['w_M6'], l=0.045e-6)
    # PMOS Current Sources
    circuit.MOSFET('7', 'node5', 'Vbp2', 'Vdd', 'Vdd',
                  model='pmos_model', w=params['w_M7'], l=0.045e-6)
    circuit.MOSFET('8', 'node6', 'Vbp2', 'Vdd', 'Vdd',
                  model='pmos_model', w=params['w_M8'], l=0.045e-6)
    # NMOS Tail Current Source
    circuit.MOSFET('9', 'node_tail', 'Vbn2', circuit.gnd, circuit.gnd,
                  model='nmos_model', w=params['w_M9'], l=0.045e-6)
    return circuit
# Optimization parameter search ranges
param_ranges_definition = {
    # Transistor widths (Length fixed at 45nm)
    'w_M1': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # Input pair NMOS (1-500× length)
    'w_M2': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # Input pair NMOS (1-500× length)
    'w_M3': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # NMOS cascode (1-500× length)
    'w_M4': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # NMOS cascode (1-500× length)
    'w_M5': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # PMOS cascode (1-500× length)
    'w_M6': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # PMOS cascode (1-500× length)
    'w_M7': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # PMOS current source (1-500× length)
    'w_M8': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # PMOS current source (1-500× length)
    'w_M9': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # NMOS tail current source (1-500× length)
    # Bias voltages (0.8-1.2× original, capped at 1.2V)
    'v_bn1': {'min': 0.7*0.8, 'max': min(0.7*1.2, 1.2), 'log': False},  # NMOS cascode bias
    'v_bn2': {'min': 0.42*0.8, 'max': min(0.42*1.2, 1.2), 'log': False},  # NMOS current source bias
    'v_bp1': {'min': 0.5*0.8, 'max': min(0.5*1.2, 1.2), 'log': False},  # PMOS cascode bias
    'v_bp2': {'min': 0.5*0.8, 'max': min(0.5*1.2, 1.2), 'log': False},  # PMOS current source bias
}
# Initial parameter values (EXACT original circuit values)
initial_params = {
    # Transistor widths
    'w_M1': 10e-6,
    'w_M2': 10e-6,
    'w_M3': 10e-6,
    'w_M4': 10e-6,
    'w_M5': 20e-6,
    'w_M6': 20e-6,
    'w_M7': 20e-6,
    'w_M8': 20e-6,
    'w_M9': 20e-6,
    # Bias voltages
    'v_bn1': 0.7,
    'v_bn2': 0.42,
    'v_bp1': 0.5,
    'v_bp2': 0.5,
}
