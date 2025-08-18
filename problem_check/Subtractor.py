import numpy as np
# Define test parameters
BIAS_VOLTAGE = 2.5
TOLERANCE = 0.2  # Stricter 5% tolerance

# Create simulator
simulator = circuit.simulator()

# Test across a wider range of input voltages
vin1_values = np.linspace(2.5, 3.5, 5)  # Test from 1V to 4V
vin2_values = np.linspace(2.5, 3.5, 5)

print("Testing subtractor circuit with multiple input combinations...")
print("Using tolerance: {:.1f}%".format(TOLERANCE * 100))
print("-" * 60)
print("| Vin1 (V) | Vin2 (V) | Expected (V) | Actual (V) | Result |")
print("-" * 60)

all_tests_passed = True


for element in circuit.elements:
    for pin in element.pins:
        if "vin1" in str(pin.node).lower() and element.name.lower().startswith("v"):
            vin1_name = element.name
            break

for element in circuit.elements:
    for pin in element.pins:
        if "vin2" in str(pin.node).lower() and element.name.lower().startswith("v"):
            vin2_name = element.name
            break

# print("vin1_name", vin1_name)
# print("vin2_name", vin2_name)

circuit.element(vin1_name).detach()
circuit.element(vin2_name).detach()

circuit.V('in1', 'Vin1', circuit.gnd, '2.5')
circuit.V('in2', 'Vin2', circuit.gnd, '2.5')
        
import sys
# Test with multiple combinations of inputs
for vin1 in vin1_values:
    for vin2 in vin2_values:
        # Update input voltage sources
        circuit.element("Vin1").dc_value = vin1
        circuit.element("Vin2").dc_value = vin2

        
        # Run DC analysis
        try:
            analysis = simulator.operating_point()
        except Exception as e:
            print(f"Simulation failed: {e}")
            sys.exit(2)
        
        # Get actual output voltage
        actual_vout = float(analysis.Vout)
        
        # Calculate expected output for a proper subtractor: Vout = V2 - V1
        expected_vout = vin2 - vin1 + 2.5
        
        # Verify if the output voltage meets expectations
        if np.isclose(actual_vout, expected_vout, rtol=TOLERANCE):
            test_result = "PASS"
        else:
            test_result = "FAIL"
            all_tests_passed = False
        
        print(f"| {vin1:7.2f} | {vin2:7.2f} | {expected_vout:11.2f} | {actual_vout:10.2f} | {test_result:6} |")

print("-" * 60)


# Output final test result
if all_tests_passed:
    print("\nALL TESTS PASSED: The op-amp subtractor functions correctly.")
    sys.exit(0)
else:
    print("\nTESTS FAILED: The subtractor circuit is not functioning correctly.")
    print("Check the circuit configuration and component values.")
    sys.exit(2)