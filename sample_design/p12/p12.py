import math
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('Passive Band-Pass Filter')
# Input voltage source (DC for operating point)
circuit.V('in', 'Vin', circuit.gnd, 1.0)  # 1V DC
# High-Pass Filter Stage
circuit.C('1', 'Vin', 'N1', 10@u_nF)      # C1: 10 nF
circuit.R('1', 'N1', circuit.gnd, 10@u_kΩ) # R1: 10 kΩ
# Low-Pass Filter Stage
circuit.R('2', 'N1', 'Vout', 10@u_kΩ)     # R2: 10 kΩ
circuit.C('2', 'Vout', circuit.gnd, 10@u_nF) # C2: 10 nF
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
gain_db = 20 * np.log10(np.abs(vout_ac)+1e-12)  # Avoid log(0)
phase = np.angle(vout_ac, deg=True)

# Create frequency domain plot
plt.figure(figsize=(10, 6))
plt.semilogx(frequencies, gain_db)
plt.title('Frequency Response of Band-Pass Filter')
plt.xlabel('Frequency [Hz]')
plt.ylabel('Gain [dB]')
plt.grid(True)

plt.axhline(y=-3, color='g', linestyle='--', label='-3dB Points')
plt.legend()

plt.tight_layout()
plt.savefig('sample_design/p12/p12_waveform.png')

max_gain_idx = np.argmax(gain_db)
max_gain = gain_db[max_gain_idx]
peak_freq = frequencies[max_gain_idx]

print(f"Maximum gain: {max_gain:.2f} dB at frequency {peak_freq:.2e} Hz")

relative_position = max_gain_idx / len(frequencies)
print(f"Relative position in frequency range: {relative_position:.2f}")

min_peak_boost = 10  # dB

high_gain_mask = gain_db > (max_gain - min_peak_boost/2)
low_gain_points = gain_db[~high_gain_mask]
avg_stopband_gain = np.mean(low_gain_points) if len(low_gain_points) > 0 else 0

peak_boost = max_gain - avg_stopband_gain

print(f"Average stopband gain: {avg_stopband_gain:.2f} dB")
print(f"Calculated peak boost: {peak_boost:.2f} dB")

left_side = gain_db[:max_gain_idx]
right_side = gain_db[max_gain_idx+1:]

min_side_length = max(5, len(gain_db) * 0.05)

if len(left_side) < min_side_length or len(right_side) < min_side_length:
    print("WARNING: Peak is very close to frequency range boundary.")

left_avg = np.mean(left_side) if len(left_side) >= min_side_length else None
right_avg = np.mean(right_side) if len(right_side) >= min_side_length else None

left_lower = (left_avg is not None) and (left_avg < max_gain - min_peak_boost)
right_lower = (right_avg is not None) and (right_avg < max_gain - min_peak_boost)

if left_avg is not None:
    print(f"Left side average gain: {left_avg:.2f} dB")
if right_avg is not None:
    print(f"Right side average gain: {right_avg:.2f} dB")

if peak_boost >= min_peak_boost and (left_lower and right_lower):
    print("PASS: This is a band-pass filter.")
    print(f"Center frequency: {peak_freq:.2e} Hz")
    print(f"Peak gain: {max_gain:.2f} dB")
    print(f"Peak boost: {peak_boost:.2f} dB above stopband")
    
    threshold = max_gain - 3
    
    if peak_boost > 30:
        print("This appears to be a high-Q resonant band-pass filter.")
    
    sys.exit(0)
else:
    print("FAIL: This is NOT a band-pass filter.")
    
    if not (left_lower and right_lower):
        if left_lower and not right_lower:
            print("Only left side has low gain - may be a high-pass filter.")
        elif right_lower and not left_lower:
            print("Only right side has low gain - may be a low-pass filter.")
        else:
            print("Neither side shows significantly lower gain.")
    
    if peak_boost < min_peak_boost:
        print(f"The gain variation ({peak_boost:.2f} dB) is insufficient for a band-pass filter.")
    
    if relative_position < 0.1 or relative_position > 0.9:
        if relative_position < 0.1:
            print("Maximum gain is at the low frequency end - likely a low-pass filter.")
        else:
            print("Maximum gain is at the high frequency end - likely a high-pass filter.")
    
    sys.exit(2)