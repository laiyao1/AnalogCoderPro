vin_name = ""
for element in circuit.elements:
    if "vin" in [str(pin.node).lower() for pin in element.pins] and element.name.lower().startswith("v"):
        vin_name = element.name

bias_voltage = [BIAS_VOLTAGE]

# Detach the previous Vin if it exists and attach a new triangular wave source
if vin_name != "":
    circuit.element(vin_name).detach()
    circuit.V('tri', 'Vin', circuit.gnd, f"dc {bias_voltage} PULSE({bias_voltage-0.5} {bias_voltage+0.5} 0 50m 50m 1n 100m)")
else:
    circuit.V('in', 'Vin', circuit.gnd, f"dc {bias_voltage} PULSE({bias_voltage-0.5} {bias_voltage+0.5} 0 50m 50m 1n 100m)")

# Adjust R1 resistance if needed
for element in circuit.elements:
    if element.name.lower().startswith("rf") or element.name.lower().startswith("rrf") or element.name.lower().startswith("r1"):
        r_name = element.name
circuit.element(r_name).resistance = "10k"

# Adjust C1 capacitance if needed
for element in circuit.elements:
    if element.name.lower().startswith("c1") or element.name.lower().startswith("cc1"):
        c_name = element.name
circuit.element(c_name).capacitance = "3u"

# Initialize the simulator
simulator = circuit.simulator()

import sys
# Perform transient analysis
try:
    analysis = simulator.transient(step_time=1@u_us, end_time=200@u_ms)
except:
    print("analysis failed.")
    sys.exit(2)

import numpy as np
vlist = {}
for node in analysis.nodes.values():
    vlist[node.name] = np.array(analysis[node.name])

import numpy as np
# Extract data from the analysis
time = np.array(analysis.time)
vin = np.array(analysis['vin'])
vout = np.array(analysis['vout'])

import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter

plt.rcParams.update({
    'font.size': 12,
    'axes.titlesize': 16,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
    'lines.linewidth': 2.5
})

# Plot the response
plt.figure(figsize=(12, 8))

colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E', '#7209B7', '#F72585', 
          '#264653', '#2A9D8F', '#E9C46A', '#F4A261', '#E76F51', '#8E44AD', '#3498DB',
          '#E74C3C', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C', '#34495E', '#E67E22']

linestyles = ['-', '--', '-.', ':', '-', '--', '-.', '-', '--', '-.', ':', 
              '-', '--', '-.', ':', '-', '--', '-.', ':', '-', '--']

for i, node in enumerate(analysis.nodes.values()):
    plt.plot(time, vlist[node.name], 
             color=colors[i % len(colors)], 
             linestyle=linestyles[i % len(linestyles)],
             linewidth=2.5,
             label=node.name,
             alpha=0.9)

plt.title('Transient Response of Op-amp Differentiator', fontsize=16, fontweight='bold', pad=20)
plt.xlabel('Time [s]', fontsize=14, fontweight='semibold')
plt.ylabel('Voltage [V]', fontsize=14, fontweight='semibold')

plt.grid(True, linestyle='--', alpha=0.6, color='gray', linewidth=0.8)

plt.legend(frameon=True, fancybox=True, shadow=True, ncol=2, 
           loc='best', framealpha=0.9, edgecolor='black')

ax = plt.gca()
ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
ax.xaxis.set_major_formatter(FormatStrFormatter('%.3f'))

for spine in ax.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(1.2)
    spine.set_color('black')

plt.tick_params(axis='both', which='major', direction='out', length=6, width=1.2)
plt.tick_params(axis='both', which='minor', direction='out', length=4, width=1)

plt.tight_layout()
plt.savefig("[FIGURE_PATH].png", dpi=300, bbox_inches='tight', facecolor='white')

from scipy.signal import find_peaks
# Check for square wave characteristics in the output
# Calculate the mean voltage level of the peaks and troughs

min_height = (max(vout) + min(vout)) / 2
num_of_peaks = 2
min_distance = len(vout) / (2 * num_of_peaks) / 1.5 

peaks, _ = find_peaks(vout, height=min_height, distance=min_distance)
troughs, _ = find_peaks(-vout, height=-min_height, distance=min_distance)

average_peak_voltage = np.mean(vout[peaks])
average_trough_voltage = np.mean(vout[troughs])

if len(peaks) == 0 or len(troughs) == 0:
    print("No peaks or troughs found in output voltage. Please check the netlist.")
    sys.exit(2)

peak_voltages = vout[peaks]
trough_voltages = vout[troughs]
mean_peak = np.mean(peak_voltages)
mean_trough = np.mean(trough_voltages)

def is_square_wave(waveform, mean_peak, mean_trough, rtol=0.1):
    high_level = np.mean([x for x in waveform if x > (mean_peak + mean_trough) / 2])
    low_level = np.mean([x for x in waveform if x <= (mean_peak + mean_trough) / 2])
    is_high_close = np.isclose(high_level, mean_peak, rtol=rtol)
    is_low_close = np.isclose(low_level, mean_trough, rtol=rtol)
    return is_high_close and is_low_close

# Check if the output is approximately a square wave by comparing the mean of the peaks and troughs
if np.isclose(mean_peak - bias_voltage, -mean_trough+ bias_voltage, rtol=0.2) and \
     np.isclose(mean_peak - bias_voltage, 0.6, rtol=0.2) and \
     is_square_wave(vout, mean_peak, mean_trough):  # 20% tolerance
    pass
elif not np.isclose(mean_peak - bias_voltage, -mean_trough+ bias_voltage, rtol=0.2):
    print(f"The circuit does not function correctly as a differentiator.\n"
          f"When the input is a triangle wave and the output is not a square wave.\n")
    sys.exit(2)
elif not is_square_wave(vout, mean_peak, mean_trough):
    print(f"The circuit does not function correctly as a differentiator.\n"
          f"When the input is a triangle wave and the output is not a square wave.\n")
    sys.exit(2)
else:
    print(f"The circuit does not function correctly as a differentiator.\n"
          f"Output voltage peak value is wrong. Mean peak voltage: {mean_peak} V | Mean trough voltage: {mean_trough} V\n")
    sys.exit(2)

for element in circuit.elements:
    if element.name.lower().startswith("x"):
        x_name = element.name

# Detach the subcircuit
circuit.element(x_name).detach()
simulator = circuit.simulator()
try:
    analysis = simulator.transient(step_time=1@u_us, end_time=200@u_ms)
except:
    print("The op-amp differentiator functions correctly.\n")
    sys.exit(0)

time = np.array(analysis.time)
vin = np.array(analysis['vin'])
vout = np.array(analysis['vout'])

min_height = (max(vout) + min(vout)) / 2
num_of_peaks = 2
min_distance = len(vout) / (2 * num_of_peaks) / 1.5 

peaks, _ = find_peaks(vout, height=min_height, distance=min_distance)
troughs, _ = find_peaks(-vout, height=-min_height, distance=min_distance)

average_peak_voltage = np.mean(vout[peaks])
average_trough_voltage = np.mean(vout[troughs])

if len(peaks) == 0 or len(troughs) == 0:
    print(f"The op-amp differentiator functions correctly.\n")
    sys.exit(0)

peak_voltages = vout[peaks]
trough_voltages = vout[troughs]
mean_peak = np.mean(peak_voltages)
mean_trough = np.mean(trough_voltages)

if np.isclose(mean_peak - bias_voltage, -mean_trough+ bias_voltage, rtol=0.2) and np.isclose(mean_peak - bias_voltage, 0.6, rtol=0.2):  # 20% tolerance
    print("The differentiator maybe a passive differentiator.\n")
    sys.exit(2)
elif not np.isclose(mean_peak - bias_voltage, -mean_trough+ bias_voltage, rtol=0.2):
    print(f"The op-amp differentiator functions correctly.\n")
    sys.exit(0)
else:
    print(f"The op-amp differentiator functions correctly.\n")
    sys.exit(0)