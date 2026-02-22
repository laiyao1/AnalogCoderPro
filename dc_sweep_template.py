import numpy as np

# Get the VDD value from the circuit
try:
    dc_value = circuit.element('Vdd').dc_value
    if type(dc_value) == str:
        v_dd_value = float(dc_value.split()[0])
    else:
        v_dd_value = float(dc_value)
except:
    # Try alternative name formats
    try:
        dc_value = circuit.element('VDD').dc_value
        if type(dc_value) == str:
            v_dd_value = float(dc_value.split()[0])
        else:
            v_dd_value = float(dc_value)
    except:
        # Default to 1.2V if VDD cannot be found
        v_dd_value = 1.2

# Define reasonable voltage range for differential amplifier biasing
# Avoid regions too close to rails where transistors might not be in saturation
min_voltage = 0.2
max_voltage = v_dd_value - 0.2  # Avoid saturation region

# Target output voltage is typically VDD/2 for many amplifier circuits
target_vout = v_dd_value / 2

# Save the data to file in two lines
fopen = open("[DC_PATH]", "w")


for element in circuit.elements:
    if element.name == "V[IN_NAME]":
        vin_pin_name = element.pins[0].node
# Three-level scanning strategy
# Level 1: Coarse scan across reasonable operating range
coarse_step = (max_voltage - min_voltage) / 20  # Adaptive step size
analysis_coarse = simulator.dc(V[IN_NAME]=slice(min_voltage, max_voltage, coarse_step))
out_voltage_coarse = np.array(analysis_coarse.Vout)
in_voltage_coarse = np.array(getattr(analysis_coarse, vin_pin_name))

# Find the approximate best point
best_vin_coarse = v_dd_value / 2  # Initial guess
min_diff_coarse = float('inf')
for i, vout in enumerate(out_voltage_coarse):
    diff = abs(float(vout) - target_vout)
    if diff < min_diff_coarse:
        min_diff_coarse = diff
        best_vin_coarse = float(in_voltage_coarse[i])

# Level 2: Medium resolution scan around best point from coarse scan
mid_range = (max_voltage - min_voltage) / 4  # 25% of the range
mid_step = (max_voltage - min_voltage) / 200  # Higher resolution
mid_min = max(min_voltage, best_vin_coarse - mid_range/2)
mid_max = min(max_voltage, best_vin_coarse + mid_range/2)

# get vin pin name



analysis_mid = simulator.dc(V[IN_NAME]=slice(mid_min, mid_max, mid_step))
out_voltage_mid = np.array(analysis_mid.Vout)
in_voltage_mid = np.array(getattr(analysis_mid, vin_pin_name))

# Find the best point in medium resolution scan
best_vin_mid = best_vin_coarse
min_diff_mid = float('inf')
for i, vout in enumerate(out_voltage_mid):
    diff = abs(float(vout) - target_vout)
    if diff < min_diff_mid:
        min_diff_mid = diff
        best_vin_mid = float(in_voltage_mid[i])

# Level 3: Ultra-high resolution scan around best point from medium scan
fine_range = (max_voltage - min_voltage) / 40  # ~2.5% of the range
fine_step = (max_voltage - min_voltage) / 2000  # Ultra-fine resolution
fine_min = max(min_voltage, best_vin_mid - fine_range/2)
fine_max = min(max_voltage, best_vin_mid + fine_range/2)

analysis_fine = simulator.dc(V[IN_NAME]=slice(fine_min, fine_max, fine_step))
out_voltage = np.array(analysis_fine.Vout)
in_voltage = np.array(getattr(analysis_fine, vin_pin_name))

# Print information about the search
print(f"VDD = {v_dd_value:.3f}V, Target Vout = {target_vout:.3f}V")
print(f"Search range: {min_voltage:.3f}V to {max_voltage:.3f}V")
print(f"Coarse scan result: Best Vin ≈ {best_vin_coarse:.6f}V")
print(f"Medium scan result: Best Vin ≈ {best_vin_mid:.6f}V")

# Find best point in fine scan
best_vin_fine = best_vin_mid
best_vout_fine = target_vout
min_diff_fine = float('inf')
for i, vout in enumerate(out_voltage):
    diff = abs(float(vout) - target_vout)
    if diff < min_diff_fine:
        min_diff_fine = diff
        best_vin_fine = float(in_voltage[i])
        best_vout_fine = float(vout)

print(f"Fine scan result: Best Vin = {best_vin_fine:.6f}V (Vout ≈ {best_vout_fine:.6f}V)")

# Combine all results for comprehensive data output
all_out_voltage = np.concatenate((out_voltage_coarse, out_voltage_mid, out_voltage))
all_in_voltage = np.concatenate((in_voltage_coarse, in_voltage_mid, in_voltage))

for item in all_in_voltage:
    fopen.write(f"{item:.6f} ")
fopen.write("\n")
for item in all_out_voltage:
    fopen.write(f"{item:.6f} ")
fopen.write("\n")
fopen.close()