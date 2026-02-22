del_vname = []
for element in circuit.elements:
    v_name = element.name
    if element.name.lower().startswith("v") and "bias" not in element.name.lower() and "ref" not in element.name.lower():
        del_vname.append(v_name)

pin_name = "Vinp"
pin_name_n = "Vinn"
for element in circuit.elements:
    if element.name.lower().startswith("x"):
        opamp_element = element
        pin_name = str(opamp_element.pins[0].node)
        pin_name_n = str(opamp_element.pins[1].node)
        break

params = {pin_name: 2.51, pin_name_n: 2.5}

simulator = circuit.simulator()
simulator.initial_condition(**params)

try:
    analysis = simulator.transient(step_time=1@u_us, end_time=20@u_ms)
except:
    print("analysis failed.")
    sys.exit(2)

node = 'Vout'
# find any node with "vout"
has_node = False
for element in circuit.elements:
    # get pins
    for pin in element.pins:
        if "vout" == str(pin.node).lower():
            has_node = True
            node = str(pin.node)
            break
if has_node == False:
    for element in circuit.elements:
        for pin in element.pins:
            if "vout" in str(pin.node).lower():
                node = str(pin.node)
                break

import numpy as np
# Get the output node voltage
vout = np.array(analysis[node])

vlist = {}
for node_name in analysis.nodes.keys():
    vlist[node_name.lower()] = np.array(analysis[node_name])

time = np.array(analysis.time)

from scipy.signal import find_peaks, firwin, lfilter
import sys
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter

fig, axs = plt.subplots(3, 1, figsize=(14, 14), sharex=False)

key_output = node.lower()
axs[0].plot(time, vlist[key_output], color='darkgreen', linewidth=3, label=key_output)
axs[0].set_title('Output Signal', fontsize=16)
axs[0].set_ylabel('Voltage [V]', fontsize=14)
axs[0].tick_params(axis='both', which='major', labelsize=12)
axs[0].grid(True, linestyle='--', alpha=0.7)
axs[0].legend(fontsize=12, loc='best')

axs[0].yaxis.set_major_formatter(FormatStrFormatter('%.2f'))

feedback_node = None
ref_node = None
input_nodes = []

for node_name in vlist.keys():
    if 'feedback' in node_name or 'fb' in node_name:
        feedback_node = node_name
    elif 'ref' in node_name or 'vref' in node_name:
        ref_node = node_name
    elif node_name in [pin_name.lower(), pin_name_n.lower()]:
        input_nodes.append(node_name)
    elif ('in' in node_name or 'node' in node_name) and node_name != key_output:
        input_nodes.append(node_name)

if not input_nodes:
    for node_name in vlist.keys():
        if (node_name != key_output and 
            node_name != feedback_node and 
            node_name != ref_node and
            'vdd' not in node_name and 
            'vcc' not in node_name and
            'bias' not in node_name):
            input_nodes.append(node_name)
            if len(input_nodes) >= 3:
                break

if feedback_node:
    axs[1].plot(time, vlist[feedback_node], color='crimson', linewidth=2.5, label=feedback_node)
if ref_node:
    axs[1].plot(time, vlist[ref_node], color='navy', linewidth=2.5, label=ref_node)

colors = ['darkorange', 'purple', 'teal', 'olive', 'brown']
for i, node_name in enumerate(input_nodes):
    axs[1].plot(time, vlist[node_name], color=colors[i % len(colors)], linewidth=2, label=node_name)

axs[1].set_title('Input, Reference and Feedback Signals', fontsize=16)
axs[1].set_xlabel('Time [s]', fontsize=14)
axs[1].set_ylabel('Voltage [V]', fontsize=14)
axs[1].tick_params(axis='both', which='major', labelsize=12)
axs[1].grid(True, linestyle='--', alpha=0.7)
axs[1].legend(fontsize=12, loc='best')

axs[1].yaxis.set_major_formatter(FormatStrFormatter('%.2f'))

vout_min = np.min(vlist[key_output])
vout_max = np.max(vlist[key_output])
vout_range = vout_max - vout_min
axs[0].set_ylim([vout_min - 0.1 * vout_range, vout_max + 0.1 * vout_range])

all_values = []
if feedback_node:
    all_values.extend(vlist[feedback_node])
if ref_node:
    all_values.extend(vlist[ref_node])
for node_name in input_nodes:
    all_values.extend(vlist[node_name])

if all_values:
    y_min = np.min(all_values)
    y_max = np.max(all_values)
    y_range = y_max - y_min
    axs[1].set_ylim([y_min - 0.1 * y_range, y_max + 0.1 * y_range])

axs[1].xaxis.set_major_formatter(FormatStrFormatter('%.4f'))

def analyze_last_section(vout, time, fraction=0.5):
    start_idx = int(len(time) * (1 - fraction))
    return vout[start_idx:], time[start_idx:]

last_vout, last_time = analyze_last_section(vout, time, 0.5)

last_vout_ac = last_vout - np.mean(last_vout)

dt = np.mean(np.diff(last_time))
sampling_freq = 1.0 / dt

fft_result = np.fft.fft(last_vout_ac)
fft_freq = np.fft.fftfreq(len(last_vout_ac), dt)

positive_freq_idx = fft_freq > 0
fft_freq_positive = fft_freq[positive_freq_idx]
fft_magnitude = np.abs(fft_result[positive_freq_idx]) * 2 / len(last_vout_ac)

axs[2].plot(fft_freq_positive, fft_magnitude, color='blue', linewidth=2)
axs[2].set_title('FFT Spectrum (Latter Half of Signal)', fontsize=16)
axs[2].set_xlabel('Frequency [Hz]', fontsize=14)
axs[2].set_ylabel('Magnitude [V]', fontsize=14)
axs[2].tick_params(axis='both', which='major', labelsize=12)
axs[2].grid(True, linestyle='--', alpha=0.7)
axs[2].set_xlim([0, sampling_freq / 2])

peak_idx = np.argmax(fft_magnitude)
dominant_freq = fft_freq_positive[peak_idx]
dominant_magnitude = fft_magnitude[peak_idx]

axs[2].axvline(x=dominant_freq, color='red', linestyle='--', linewidth=2, 
               label=f'Peak: {dominant_freq:.2f} Hz ({dominant_magnitude:.4f} V)')
axs[2].legend(fontsize=12, loc='best')

print(f"\nFFT Analysis:")
print(f"Dominant frequency: {dominant_freq:.2f} Hz")
print(f"Dominant frequency magnitude: {dominant_magnitude:.6f} V")
print(f"Sampling frequency: {sampling_freq:.2f} Hz")

plt.tight_layout()
plt.savefig('[FIGURE_PATH].png', dpi=300)

amplitude = np.max(last_vout) - np.min(last_vout)

from scipy.signal import find_peaks

height_threshold = np.mean(last_vout)
min_distance = max(5, len(last_vout) // 100)

peaks, _ = find_peaks(last_vout, height=height_threshold, distance=min_distance)
troughs, _ = find_peaks(-last_vout, height=-np.min(last_vout), distance=min_distance)

error = 0

if len(peaks) > 2:
    peak_times = last_time[peaks]
    periods = np.diff(peak_times)
    
    average_period = np.mean(periods)
    period_variation = np.std(periods) / average_period
    
    print(f"\nPeak Analysis:")
    print(f"Detected {len(peaks)} peaks in the latter half of the signal")
    print(f"Average oscillation period: {average_period:.6f} s")
    print(f"Frequency from peaks: {1/average_period:.2f} Hz")
    print(f"Maximum amplitude: {amplitude:.6f} V")

    if amplitude > 0.000005:
        if period_variation < 0.2:
            print("The oscillator works correctly and produces periodic oscillations")
        else:
            print("Periodicity is inconsistent, oscillation may not be ideal")
            error = 1
    else:
        print("The oscillation amplitude is too small")
        error = 1
else:
    print("Not enough peaks detected in the latter half to determine periodicity")
    error = 1

if error == 1:
    sys.exit(2)
else:
    sys.exit(0)