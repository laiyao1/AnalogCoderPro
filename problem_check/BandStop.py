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
plt.title('Frequency Response of Band-Stop Filter')
plt.xlabel('Frequency [Hz]')
plt.ylabel('Gain [dB]')
plt.grid(True)

plt.axhline(y=-3, color='g', linestyle='--', label='-3dB Points')
plt.legend()

plt.tight_layout()
plt.savefig('[FIGURE_PATH].png')

min_gain_idx = np.argmin(gain_db)
min_gain = gain_db[min_gain_idx]
notch_freq = frequencies[min_gain_idx]

print(f"Minimum gain: {min_gain:.2f} dB at frequency {notch_freq:.2e} Hz")

relative_position = min_gain_idx / len(frequencies)
print(f"Relative position in frequency range: {relative_position:.2f}")

min_notch_depth = 10  # dB

low_gain_mask = gain_db < (min_gain + min_notch_depth/2)
high_gain_points = gain_db[~low_gain_mask]
avg_passband_gain = np.mean(high_gain_points) if len(high_gain_points) > 0 else 0

notch_depth = avg_passband_gain - min_gain

print(f"Average passband gain: {avg_passband_gain:.2f} dB")
print(f"Calculated notch depth: {notch_depth:.2f} dB")

left_side = gain_db[:min_gain_idx]
right_side = gain_db[min_gain_idx+1:]

min_side_length = max(5, len(gain_db) * 0.05)

if len(left_side) < min_side_length or len(right_side) < min_side_length:
    print("WARNING: Notch is very close to frequency range boundary.")

left_avg = np.mean(left_side) if len(left_side) >= min_side_length else None
right_avg = np.mean(right_side) if len(right_side) >= min_side_length else None

left_higher = (left_avg is not None) and (left_avg > min_gain + min_notch_depth)
right_higher = (right_avg is not None) and (right_avg > min_gain + min_notch_depth)

if left_avg is not None:
    print(f"Left side average gain: {left_avg:.2f} dB")
if right_avg is not None:
    print(f"Right side average gain: {right_avg:.2f} dB")

if notch_depth >= min_notch_depth and (left_higher and right_higher):
    print("PASS: This is a band-stop filter.")
    print(f"Notch frequency: {notch_freq:.2e} Hz")
    print(f"Notch depth: {notch_depth:.2f} dB")
    
    threshold = avg_passband_gain - 3
    
    if notch_depth > 30:
        print("This appears to be a deep notch filter.")
    
    sys.exit(0)
else:
    print("FAIL: This is NOT a band-stop filter.")
    
    if not (left_higher and right_higher):
        if left_higher and not right_higher:
            print("Only left side has high gain - may be a low-pass filter.")
        elif right_higher and not left_higher:
            print("Only right side has high gain - may be a high-pass filter.")
        else:
            print("Neither side shows significantly higher gain.")
    
    if notch_depth < min_notch_depth:
        print(f"The gain variation ({notch_depth:.2f} dB) is insufficient for a band-stop filter.")
    
    sys.exit(2)