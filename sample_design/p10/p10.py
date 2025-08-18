import math
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('Passive Low-Pass Filter')
# DC voltage source to Vin (input node)
circuit.V('in', 'Vin', circuit.gnd, 1.0@u_V)
# Resistor R1 between Vin and Vout
circuit.R('1', 'Vin', 'Vout', 10@u_kΩ)
# Capacitor C1 between Vout and ground
circuit.C('1', 'Vout', circuit.gnd, 10@u_nF)
simulator = circuit.simulator()
has_vin = False
for element in circuit.elements:
    if "vin" in element.name.lower():
        element.dc_value = "dc 2.5 ac 1"
        has_vin = True
        break

if not has_vin:
    circuit.V('in', 'Vin', circuit.gnd, dc_value=0, ac_value=1)

import sys
import numpy as np
import matplotlib.pyplot as plt
try:
    # Only AC analysis
    ac_analysis = simulator.ac(start_frequency=1@u_Hz, stop_frequency=1@u_GHz, 
                              number_of_points=1000, variation='dec')
except:
    print("Analysis failed.")
    sys.exit(2)


node = 'Vout'
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

# Get frequency response data
frequencies = np.array(ac_analysis.frequency)
vout_ac = np.array(ac_analysis[node])
gain_db = 20 * np.log10(np.abs(vout_ac))
phase = np.angle(vout_ac, deg=True)

# Create frequency domain plot
plt.figure(figsize=(10, 6))
plt.semilogx(frequencies, gain_db)
plt.title('Frequency Response of Low-Pass Filter')
plt.xlabel('Frequency [Hz]')
plt.ylabel('Gain [dB]')
plt.grid(True)


plt.axhline(y=-3, color='g', linestyle='--', label='-3dB Point')
plt.legend()

plt.tight_layout()
plt.savefig('sample_design/p10/p10_waveform.png')

low_freq_gain = gain_db[0]
print(f"Gain at lowest frequency ({frequencies[0]:.2f} Hz): {low_freq_gain:.2f} dB")

high_freq_gain = gain_db[-1]
print(f"Gain at highest frequency ({frequencies[-1]:.2f} Hz): {high_freq_gain:.2f} dB")
high_freq_attenuation = low_freq_gain - high_freq_gain
print(f"High frequency attenuation: {high_freq_attenuation:.2f} dB")

idx_3db = np.argmin(np.abs(gain_db - (low_freq_gain-3)))
cutoff_freq = frequencies[idx_3db]
print(f"Approximate -3dB cutoff frequency: {cutoff_freq:.2f} Hz")

window_size = min(11, len(gain_db) // 20)
if window_size % 2 == 0:
    window_size += 1
    
if window_size > 2:
    from scipy.signal import savgol_filter
    smoothed_gain = savgol_filter(gain_db, window_size, 1)
else:
    smoothed_gain = gain_db
    
diff_gain = np.diff(smoothed_gain)
non_monotonic_points = np.sum(diff_gain > 0.5)

if non_monotonic_points > 0:
    monotonic_percentage = 100 * (1 - non_monotonic_points / len(diff_gain))
    print(f"Warning: Gain is not strictly monotonically decreasing.")
    print(f"Monotonicity: {monotonic_percentage:.1f}% of frequency points")
    if monotonic_percentage < 90:
        print("This may not be a well-behaved low-pass filter.")
else:
    print("Filter response is monotonically decreasing with frequency, as expected.")

if high_freq_attenuation > 2 and (non_monotonic_points == 0 or monotonic_percentage >= 90):
    print("The circuit exhibits proper low-pass filter characteristics.")
    sys.exit(0)
else:
    print("The circuit does not show expected low-pass filter characteristics.")
    sys.exit(2)