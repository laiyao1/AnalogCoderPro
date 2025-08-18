import math
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from opamp import *
circuit = Circuit('Corrected Opamp Inverting Adder')
# Power supply: 5V single supply
circuit.V('dd', 'Vdd', circuit.gnd, 5@u_V)
# Virtual ground/reference at 2.5V for opamp biasing
circuit.V('ref', 'Vref', circuit.gnd, 2.5@u_V)
# Input voltages (example DC values, you can set as needed)
circuit.V('in1', 'Vin1', circuit.gnd, 3@u_V)
circuit.V('in2', 'Vin2', circuit.gnd, 3@u_V)
# --- MODIFICATION 1: All resistors equal for unity gain from each input ---
R_value = 10@u_kΩ
# --- MODIFICATION 2: Both inputs connect through resistors to summing node 'Vsum' (inverting input) ---
circuit.R('1', 'Vin1', 'Vsum', R_value)  # Vin1 to Vsum
circuit.R('2', 'Vin2', 'Vsum', R_value)  # Vin2 to Vsum
# --- MODIFICATION 3: Feedback resistor from output to Vsum ---
circuit.R('f', 'Vout', 'Vsum', R_value)  # Vout to Vsum
# --- MODIFICATION 4: Non-inverting input of opamp connected to Vref (2.5V) ---
circuit.subcircuit(Opamp())
circuit.X('op', 'Opamp', 'Vref', 'Vsum', 'Vout')
# The circuit now forms a classic inverting adder:
# Vout = 2.5V - [(Vin1 - 2.5V) + (Vin2 - 2.5V)]
#      = -Vin1 - Vin2 + 5V
simulator = circuit.simulator()

bias_voltage = 2.5  # Set bias voltage to 2.5V
v1_amp = 3.0  # Original value from circuit
v2_amp = 3.0  # Original value from circuit
tolerance = 0.2  # 20% tolerance

# Testing approach: We'll run multiple tests to determine if the circuit functions as an adder

# Test 1: Get baseline with original values
simulator = circuit.simulator()
try:
    analysis_baseline = simulator.operating_point()
except Exception as e:
    print(f"DC analysis failed: {str(e)}")
    sys.exit(2)

baseline_output = float(analysis_baseline.Vout)
print(f"Baseline output: {baseline_output:.4f} V with Vin1 = {v1_amp:.4f} V, Vin2 = {v2_amp:.4f} V")

# Test 2: Change Vin1 and check effect
# First, find the Vin1 source to modify
vin1_found = False
for element in circuit.elements:
    if element.name.lower() == 'vin1' or (element.name.lower().startswith('v') and 'vin1' in [str(pin.node).lower() for pin in element.pins]):
        circuit.element(element.name).dc_value = v1_amp + 0.5
        vin1_found = True
        break

if not vin1_found:
    print("Could not find Vin1 source to modify")
    sys.exit(2)

# Run analysis with modified Vin1
simulator = circuit.simulator()
try:
    analysis_vin1_mod = simulator.operating_point()
except Exception as e:
    print(f"DC analysis failed with modified Vin1: {str(e)}")
    sys.exit(2)

vin1_mod_output = float(analysis_vin1_mod.Vout)
vin1_effect = vin1_mod_output - baseline_output
print(f"Effect of increasing Vin1 by 0.5V: {vin1_effect:.4f} V change in output")

# Reset Vin1 to original value
for element in circuit.elements:
    if element.name.lower() == 'vin1' or (element.name.lower().startswith('v') and 'vin1' in [str(pin.node).lower() for pin in element.pins]):
        circuit.element(element.name).dc_value = v1_amp
        break

# Test 3: Change Vin2 and check effect
vin2_found = False
for element in circuit.elements:
    if element.name.lower() == 'vin2' or (element.name.lower().startswith('v') and 'vin2' in [str(pin.node).lower() for pin in element.pins]):
        circuit.element(element.name).dc_value = v2_amp + 0.5
        vin2_found = True
        break

if not vin2_found:
    print("Could not find Vin2 source to modify")
    sys.exit(2)

# Run analysis with modified Vin2
simulator = circuit.simulator()
try:
    analysis_vin2_mod = simulator.operating_point()
except Exception as e:
    print(f"DC analysis failed with modified Vin2: {str(e)}")
    sys.exit(2)

vin2_mod_output = float(analysis_vin2_mod.Vout)
vin2_effect = vin2_mod_output - baseline_output
print(f"Effect of increasing Vin2 by 0.5V: {vin2_effect:.4f} V change in output")

# Verify adder properties
import sys
import numpy as np

# Check if inputs affect the output significantly
if abs(vin1_effect) < 0.05:
    print(f"The circuit is not an adder: Vin1 has minimal effect on output ({vin1_effect:.4f} V change)")
    sys.exit(2)

if abs(vin2_effect) < 0.05:
    print(f"The circuit is not an adder: Vin2 has minimal effect on output ({vin2_effect:.4f} V change)")
    sys.exit(2)

# For a proper inverting adder, increasing input should decrease output
if vin1_effect >= 0:
    print(f"The circuit is not an inverting adder: Increasing Vin1 does not decrease output (effect: {vin1_effect:.4f} V)")
    sys.exit(2)

if vin2_effect >= 0:
    print(f"The circuit is not an inverting adder: Increasing Vin2 does not decrease output (effect: {vin2_effect:.4f} V)")
    sys.exit(2)

# Check if inputs have similar effects (should be approximately equal for equal resistors)
effect_ratio = abs(vin1_effect / vin2_effect)
if not (1-tolerance <= effect_ratio <= 1+tolerance):
    print(f"The circuit has unbalanced input scaling: Vin1 effect = {vin1_effect:.4f} V, Vin2 effect = {vin2_effect:.4f} V")
    sys.exit(2)

# Collect additional test points to verify the adder behavior
test_points = [
    (2.5, 2.5),   # Both at reference
    (3.0, 2.5),   # Only Vin1 above reference
    (2.5, 3.0),   # Only Vin2 above reference
    (3.0, 3.0),   # Both above reference (baseline)
]

results = []
for v1, v2 in test_points:
    # Set Vin1
    for element in circuit.elements:
        if element.name.lower() == 'vin1' or (element.name.lower().startswith('v') and 'vin1' in [str(pin.node).lower() for pin in element.pins]):
            circuit.element(element.name).dc_value = v1
            break
    
    # Set Vin2
    for element in circuit.elements:
        if element.name.lower() == 'vin2' or (element.name.lower().startswith('v') and 'vin2' in [str(pin.node).lower() for pin in element.pins]):
            circuit.element(element.name).dc_value = v2
            break
    
    # Run analysis
    simulator = circuit.simulator()
    try:
        analysis = simulator.operating_point()
        vout = float(analysis.Vout)
        results.append((v1, v2, vout))
    except Exception as e:
        print(f"Analysis failed for Vin1 = {v1:.4f} V, Vin2 = {v2:.4f} V: {str(e)}")

# Calculate the adder's gain factor from data
input_diffs = []
output_diffs = []

for i in range(1, len(results)):
    v1, v2, vout = results[i]
    v1_ref, v2_ref, vout_ref = results[0]  # Reference point (both at 2.5V)
    
    input_diff = (v1 - bias_voltage) + (v2 - bias_voltage)
    output_diff = vout_ref - vout  # For inverting adder, output decreases as input increases
    
    if abs(input_diff) > 0.01:  # Avoid division by near-zero
        input_diffs.append(input_diff)
        output_diffs.append(output_diff)

# Calculate average gain factor
if input_diffs:
    gain_factors = [o/i for i, o in zip(input_diffs, output_diffs)]
    avg_gain = sum(gain_factors) / len(gain_factors)
else:
    avg_gain = 0.5  # Default fallback if we couldn't calculate

# Verify if output follows the adder formula with the determined gain
all_valid = True
for v1, v2, actual_vout in results:
    # Expected output based on inverting adder formula with measured gain
    expected_vout = bias_voltage - avg_gain * ((v1 - bias_voltage) + (v2 - bias_voltage))
    
    # Check if within tolerance
    if not np.isclose(actual_vout, expected_vout, rtol=tolerance):
        all_valid = False
        print(f"Output doesn't match formula at Vin1={v1:.2f}V, Vin2={v2:.2f}V:")
        print(f"  Expected: {expected_vout:.4f}V, Actual: {actual_vout:.4f}V")

if not all_valid:
    print("The circuit does not consistently follow the adder formula within 20% tolerance")
    sys.exit(2)

print("\nThe op-amp adder functions correctly!")
print(f"- Both inputs (Vin1 and Vin2) affect the output")
print(f"- Both have a negative (inverting) effect on the output")
print(f"- The input scaling is balanced (Vin1 effect ≈ Vin2 effect)")
print(f"- The output follows an inverting adder formula: Vout ≈ Vref - {avg_gain:.2f}*((Vin1-Vref) + (Vin2-Vref))")
print(f"- All test points are within {tolerance*100}% tolerance of the expected values")
sys.exit(0)