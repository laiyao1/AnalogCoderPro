import math
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from opamp import *
circuit = Circuit('RC Phase Shift Oscillator')
# Power supplies
circuit.V('dd', 'Vdd', circuit.gnd, 5@u_V)
circuit.V('ref', 'Vref', circuit.gnd, 2.5@u_V)  # Virtual ground at Vdd/2
# Declare the opamp subcircuit
circuit.subcircuit(Opamp())
# Connect non-inverting input to Vref (2.5V)
# The inverting input will be connected to the RC network and feedback resistor
# Output node is 'Vout'
# RC phase shift network (three stages)
circuit.R('1', 'Vout', 'N1', 10@u_kΩ)
circuit.C('1', 'N1', 'Vref', 10@u_nF)
circuit.R('2', 'N1', 'N2', 10@u_kΩ)
circuit.C('2', 'N2', 'Vref', 10@u_nF)
circuit.R('3', 'N2', 'N3', 10@u_kΩ)
circuit.C('3', 'N3', 'Vref', 10@u_nF)
# Feedback resistor from output to inverting input (Vinn)
circuit.R('f', 'Vout', 'Vinn', 330@u_kΩ)
# The RC network output connects to the inverting input
circuit.R('in', 'N3', 'Vinn', 1@u_Ω)  # Virtually a wire (for node naming clarity)
# Create opamp instance
circuit.X('1', 'Opamp', 'Vref', 'Vinn', 'Vout')
simulator = circuit.simulator()
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

fig, axs = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

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

plt.tight_layout()
plt.savefig('sample_design/p22/p22_waveform.png', dpi=300)


def detect_oscillation_start(vout, time, threshold=0.001):
    dvout = np.abs(np.diff(vout))
    window_size = len(dvout) // 50
    window_size = max(window_size, 10)
    
    std_values = []
    for i in range(window_size, len(dvout)):
        window = dvout[i-window_size:i]
        std_values.append(np.std(window))
    
    std_values = np.array(std_values)
    threshold_value = threshold * np.max(std_values)
    start_indices = np.where(std_values > threshold_value)[0]
    
    if len(start_indices) > 0:
        oscillation_start_idx = start_indices[0] + window_size
        oscillation_start_idx = min(oscillation_start_idx, len(time)-1)
        return oscillation_start_idx
    else:
        return int(len(time) * 0.7)

def analyze_last_section(vout, time, fraction=0.3):
    start_idx = int(len(time) * (1 - fraction))
    return vout[start_idx:], time[start_idx:]

last_vout, last_time = analyze_last_section(vout, time, 0.3)

peaks, _ = find_peaks(last_vout)
troughs, _ = find_peaks(-last_vout)

error = 0

if len(peaks) > 2 and len(troughs) > 2:
    amplitudes = []
    
    for peak in peaks:
        nearest_trough_idx = np.argmin(np.abs(troughs - peak))
        nearest_trough = troughs[nearest_trough_idx]
        amplitude = np.abs(last_vout[peak] - last_vout[nearest_trough])
        amplitudes.append(amplitude)
    
    amplitudes = np.array(amplitudes)
    
    peak_times = last_time[peaks]
    periods = np.diff(peak_times)
    
    if len(periods) > 2:
        average_period = np.mean(periods)
        period_variation = np.std(periods) / average_period
        
        print(f"Detected {len(peaks)} peaks in the oscillation section")
        print(f"Average oscillation period: {average_period:.6f} s")
        print(f"Maximum amplitude: {np.max(amplitudes):.6f} V")
        
        if period_variation < 0.2:
            print("The oscillator works correctly and produces periodic oscillations")
        else:
            print("Periodicity is inconsistent, oscillation may not be ideal")
            error = 1
    else:
        print("Not enough peaks detected to determine periodicity")
        error = 1
else:
    print("Not enough peaks and troughs detected in the latter part to analyze oscillation")
    error = 1

if error == 1:
    sys.exit(2)
else:
    sys.exit(0)