from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from model import nmos_params, pmos_params
def create_circuit(params):
    circuit = Circuit('Telescopic Cascode Amplifier')
    # Define the MOSFET models
    circuit.model('nmos_model', 'nmos', **nmos_params)
    circuit.model('pmos_model', 'pmos', **pmos_params)
    # Power Supply (fixed)
    circuit.V('dd', 'Vdd', circuit.gnd, 1.2@u_V)
    # Input Signal and Bias Voltages (fixed)
    circuit.V('in', 'Vin', circuit.gnd, 0.9)  # Input bias (Vth + 0.2V)
    # Parameterized Bias Voltages
    circuit.V('casc', 'Vcasc', circuit.gnd, params['v_casc']@u_V)  # Cascode bias
    circuit.V('bias_p', 'Vbias_p', circuit.gnd, params['v_bias_p']@u_V)  # PMOS load bias
    circuit.V('bias_n', 'Vbias_n', circuit.gnd, params['v_bias_n']@u_V)  # Tail current bias
    # Transistors (parameterized widths)
    # Input Stage: M1 (NMOS)
    circuit.MOSFET('1', 'Drain1', 'Vin', 'Source1', circuit.gnd,
                  model='nmos_model', w=params['w_M1'], l=0.045e-6)
    # Cascode Stage: M4 (NMOS)
    circuit.MOSFET('4', 'Vout', 'Vcasc', 'Drain1', circuit.gnd,
                  model='nmos_model', w=params['w_M4'], l=0.045e-6)
    # Active Load: M2 (PMOS)
    circuit.MOSFET('2', 'Vout', 'Vbias_p', 'Vdd', 'Vdd',
                  model='pmos_model', w=params['w_M2'], l=0.045e-6)
    # Tail Current Source: M3 (NMOS)
    circuit.MOSFET('3', 'Source1', 'Vbias_n', circuit.gnd, circuit.gnd,
                  model='nmos_model', w=params['w_M3'], l=0.045e-6)
    # Load capacitance is fixed; the evaluator selects 10pF for GBW or 100pF for FoM.
    circuit.C('L', 'Vout', circuit.gnd, "100p")
    return circuit
# Optimization parameter search ranges
param_ranges_definition = {
    # Transistor widths (1-500× length, log scale)
    'w_M1': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # Input NMOS width
    'w_M2': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # PMOS load width
    'w_M3': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # Tail current NMOS width
    'w_M4': {'min': 0.045e-6, 'max': 22.5e-6, 'log': True},  # Cascode NMOS width
    # Bias voltages (0.8-1.2× original, constrained to <1.2V)
    'v_casc': {'min': 0.336, 'max': 0.504},   # Cascode bias (original 0.42V)
    'v_bias_p': {'min': 0.624, 'max': 0.936}, # PMOS bias (original 0.78V)
    'v_bias_n': {'min': 0.336, 'max': 0.504}, # Tail bias (original 0.42V)
}
# Initial parameter values (EXACT original circuit values)
initial_params = {
    # Transistor widths
    'w_M1': 10e-6,    # Original M1 width
    'w_M2': 20e-6,    # Original M2 width
    'w_M3': 5e-6,     # Original M3 width
    'w_M4': 10e-6,    # Original M4 width
    # Bias voltages
    'v_casc': 0.42,   # Original cascode bias
    'v_bias_p': 0.78, # Original PMOS bias
    'v_bias_n': 0.42, # Original tail bias
}
