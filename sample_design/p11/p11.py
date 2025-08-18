import math
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
circuit = Circuit('Passive High-Pass Filter')
# Input voltage source (DC for operating point)
circuit.V('in', 'Vin', circuit.gnd, 1.0) # 1V DC
# Capacitor in series with input
circuit.C('1', 'Vin', 'Vout', 10@u_nF)
# Resistor from output to ground
circuit.R('1', 'Vout', circuit.gnd, 10@u_kΩ)
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

# Get frequency response data
frequencies = np.array(ac_analysis.frequency)

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

vout_ac = np.array(ac_analysis[node])
gain_db = 20 * np.log10(np.abs(vout_ac))
phase = np.angle(vout_ac, deg=True)

# Create frequency domain plot
plt.figure(figsize=(10, 6))
plt.semilogx(frequencies, gain_db)
plt.title('Frequency Response of High-Pass Filter')
plt.xlabel('Frequency [Hz]')
plt.ylabel('Gain [dB]')
plt.grid(True)

plt.axhline(y=-3, color='g', linestyle='--', label='-3dB Point')
plt.legend()

plt.tight_layout()
plt.savefig('gpt-4.1/p43/8/p43_8_0_figure.png')

# 基本高通滤波器验证 - 包括单调性检查
# 1. 检查高频增益
high_freq_gain = gain_db[-1]  # 最高频率的增益
print(f"Gain at highest frequency ({frequencies[-1]:.2f} Hz): {high_freq_gain:.2f} dB")

# 2. 检查低频衰减
low_freq_gain = gain_db[0]  # 最低频率的增益
print(f"Gain at lowest frequency ({frequencies[0]:.2f} Hz): {low_freq_gain:.2f} dB")
low_freq_attenuation = high_freq_gain - low_freq_gain
print(f"Low frequency attenuation: {low_freq_attenuation:.2f} dB")

# 3. 找出近似-3dB点
idx_3db = np.argmin(np.abs(gain_db - (high_freq_gain-3)))
cutoff_freq = frequencies[idx_3db]
print(f"Approximate -3dB cutoff frequency: {cutoff_freq:.2f} Hz")

# 4. 检查单调性
# 使用平滑技术减少测量噪声的影响
window_size = min(11, len(gain_db) // 20)  # 使用窗口平滑
if window_size % 2 == 0:  # 确保窗口大小为奇数
    window_size += 1
    
if window_size > 2:  # 如果有足够的点进行平滑
    from scipy.signal import savgol_filter
    smoothed_gain = savgol_filter(gain_db, window_size, 1)  # 使用1阶多项式平滑
else:
    smoothed_gain = gain_db
    
# 计算平滑后增益的差分 - 注意高通滤波器应该是随频率增加而增加
diff_gain = np.diff(smoothed_gain)
non_monotonic_points = np.sum(diff_gain < -0.5)  # 允许0.5dB的微小减小

if non_monotonic_points > 0:
    monotonic_percentage = 100 * (1 - non_monotonic_points / len(diff_gain))
    print(f"Warning: Gain is not strictly monotonically increasing.")
    print(f"Monotonicity: {monotonic_percentage:.1f}% of frequency points")
    if monotonic_percentage < 90:  # 如果非单调点超过10%
        print("This may not be a well-behaved high-pass filter.")
else:
    print("Filter response is monotonically increasing with frequency, as expected.")

# 5. 判断是否符合高通特性
if low_freq_attenuation > 2 and (non_monotonic_points == 0 or monotonic_percentage >= 90):
    print("The circuit exhibits proper high-pass filter characteristics.")
    sys.exit(0)
else:
    print("The circuit does not show expected high-pass filter characteristics.")
    sys.exit(2)