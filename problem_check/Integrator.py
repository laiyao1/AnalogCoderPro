vin_name = ""
for element in circuit.elements:
    if "vin" in [str(pin.node).lower() for pin in element.pins] and element.name.lower().startswith("v"):
        vin_name = element.name

bias_voltage = [BIAS_VOLTAGE]

if vin_name != "":
    circuit.element(vin_name).detach()
    circuit.V('pulse', 'Vin', circuit.gnd, f"dc {bias_voltage} PULSE({bias_voltage-0.5} {bias_voltage+0.5} 1u 1u 1u 10m 20m)")
else:
    circuit.V('in', 'Vin', circuit.gnd, f"dc {bias_voltage} PULSE({bias_voltage-0.5} {bias_voltage+0.5} 1u 1u 1u 10m 20m)")

r_name = None
for element in circuit.elements:
    if element.name.lower().startswith("r1") or element.name.lower().startswith("rr1"):
        r_name = element.name

if r_name is None:
    for element in circuit.elements:
        if element.name.lower().startswith("r"):
            r_name = element.name

if r_name is None:
    print("No resistor found in the netlist. Please check the netlist.")
    sys.exit(2)
circuit.element(r_name).resistance = "10k"

c_name = None
for element in circuit.elements:
    if element.name.lower().startswith("cf") or element.name.lower().startswith("ccf") or element.name.lower().startswith("c1"):
        c_name = element.name

if c_name is None:
    for element in circuit.elements:
        if element.name.lower().startswith("c"):
            c_name = element.name

if c_name is None:
    print("No capacitor found in the netlist. Please check the netlist.")
    sys.exit(2)
circuit.element(c_name).capacitance = "3u"

simulator = circuit.simulator()

try:
    analysis = simulator.transient(step_time=1@u_us, end_time=1000@u_ms, start_time=800@u_ms)
except:
    print("analysis failed.")
    sys.exit(2)

import numpy as np
vlist = {}
for node in analysis.nodes.values():
    vlist[node.name] = np.array(analysis[node.name])

import numpy as np
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

# Plot the step response
time = np.array(analysis.time)
vin = np.array(analysis['vin'])
vout = np.array(analysis['vout'])

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

plt.title('Transient Response of Op-amp Integrator', fontsize=16, fontweight='bold', pad=20)
plt.xlabel('Time [s]', fontsize=14, fontweight='semibold')
plt.ylabel('Voltage [V]', fontsize=14, fontweight='semibold')

plt.grid(True, linestyle='--', alpha=0.6, color='gray', linewidth=0.8)

plt.legend(frameon=True, fancybox=True, shadow=True, ncol=2, 
           loc='best', framealpha=0.9, edgecolor='black')

ax = plt.gca()
ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
ax.xaxis.set_major_formatter(FormatStrFormatter('%.3f'))

ax = plt.gca()
for spine in ax.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(1.2)
    spine.set_color('black')

plt.tick_params(axis='both', which='major', direction='out', length=6, width=1.2)
plt.tick_params(axis='both', which='minor', direction='out', length=4, width=1)

plt.tight_layout()
plt.savefig("[FIGURE_PATH].png", dpi=300, bbox_inches='tight', facecolor='white')

expected_slope = 0.5 / 0.03

from scipy.signal import find_peaks

peaks, _ = find_peaks(vout)
troughs, _ = find_peaks(-vout)

if len(peaks) < 2 or len(troughs) < 2:
    print("No peaks or troughs found in output voltage. Please check the netlist.")
    sys.exit(2)

start = peaks[-2]
end = troughs[troughs > start][0] 

slope, intercept = np.polyfit(time[start:end], vout[start:end], 1)
slope = np.abs(slope)
from scipy.stats import linregress
_, _, r_value, p_value, std_err = linregress(time[start:end], vout[start:end])

import sys
if not np.isclose(slope, expected_slope, rtol=0.3):
    print(f"The circuit does not function correctly as an integrator.\n"
          f"Expected slope: {expected_slope:.2f} V/s | Actual slope: {slope:.2f} V/s\n")
    sys.exit(2)

if not r_value** 2 >= 0.9:
    print("The op-amp integrator does not have a linear response.\n")
    sys.exit(2)

for element in circuit.elements:
    if element.name.lower().startswith("x"):
        x_name = element.name

circuit.element(x_name).detach()
simulator = circuit.simulator()
try:
    analysis = simulator.transient(step_time=1@u_us, end_time=200@u_ms)
except:
    print("The op-amp integrator functions correctly.\n")
    sys.exit(0)

time = np.array(analysis.time)
vin = np.array(analysis['vin'])
vout = np.array(analysis['vout'])

expected_slope = 0.5 / 0.03

from scipy.signal import find_peaks

peaks, _ = find_peaks(vout)
troughs, _ = find_peaks(-vout)

if len(peaks) < 2 or len(troughs) < 2:
    print("The op-amp integrator functions correctly.\n")
    sys.exit(0)

start = peaks[-2]
end = troughs[troughs > start][0] 

slope, intercept = np.polyfit(time[start:end], vout[start:end], 1)
slope = np.abs(slope)
from scipy.stats import linregress
_, _, r_value, p_value, std_err = linregress(time[start:end], vout[start:end])

if np.isclose(slope, expected_slope, rtol=0.5):
    print("The integrator maybe a passive integrator.\n")
    sys.exit(2)

print("The op-amp integrator functions correctly.\n")
sys.exit(0)