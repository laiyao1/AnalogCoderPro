# Gilbert Cell Mixer Functionality Test with FFT Analysis
import sys
import numpy as np

detached_voltage_source = ['Vrfp', 'Vrfn', 'Vlop', 'Vlon']
for source in detached_voltage_source:
    circuit.element(source).detach()

# connected Vrfn and Vrfp
circuit.V('rfp', 'Vrfp', circuit.gnd, 2.0@u_V)
circuit.V('rfn', 'Vrfn', 'Vrfp', 0.0@u_V)

# connected Vlop and Vlon
circuit.V('lop', 'Vlop', circuit.gnd, 4.0@u_V)
circuit.V('lon', 'Vlon', 'Vlop', 0.0@u_V)

# Sweep the Vlop to get the operating point
simulator_dc = circuit.simulator(temperature=25, nominal_temperature=25)
try:
    analysis = simulator_dc.dc(Vlop=slice(0, 5, 0.1))
except Exception as e:
    print(f"Error during DC simulation: {e}")
    sys.exit(2)

# find the best operating point
voutp = np.array(analysis['Voutp'])
vlop = np.array(analysis['Vlop'])


# find the best operating point for Vrfp which can make the Voutp closest to 2.5V
best_i = 0
best_vlop = 2.5
for i in range(len(voutp)):
    # If current voutp is closer to 2.5V than the previously found best
    if abs(voutp[i] - 2.5) < abs(voutp[best_i] - 2.5):
        best_i = i
        best_vlop = vlop[i]
        best_voutp = voutp[i]
    # If current voutp is equally distant from 2.5V as the previously found best
    elif abs(voutp[i] - 2.5) == abs(voutp[best_i] - 2.5):
        # When multiple vlop values meet the requirements, we need to select the one with voutp closest to 2.5V
        # Since abs(voutp[i] - 2.5) == abs(voutp[best_i] - 2.5), we need to compare actual values
        # Choose the one closer to 2.5V (to handle cases where one is above 2.5 and one is below)
        if abs(voutp[i] - 2.5) == (voutp[i] - 2.5):  # Current value is >= 2.5
            if abs(voutp[best_i] - 2.5) != (voutp[best_i] - 2.5) or vlop[i] > best_vlop:
                best_i = i
                best_vlop = vlop[i]
                best_voutp = voutp[i]


print(f"Best Vlop: {best_vlop:.2f} V, Best Voutp: {best_voutp:.2f} V")

detached_voltage_source = ['Vrfp', 'Vrfn', 'Vlop', 'Vlon']
for source in detached_voltage_source:
    circuit.element(source).detach()

circuit.SinusoidalVoltageSource('rfp', 'Vrfp', circuit.gnd,
                              amplitude=0.1@u_V, frequency=1@u_kHz,
                              dc_offset=2.0@u_V, offset = 2.0@u_V,
                              ac_magnitude=0.1@u_V,
                              delay=0)
circuit.SinusoidalVoltageSource('rfn', 'Vrfn', circuit.gnd,
                              amplitude=0.1@u_V, frequency=1@u_kHz,
                              dc_offset=2.0@u_V, offset = 2.0@u_V,
                              ac_magnitude=0.1@u_V,
                              delay=0.5@u_ms)
circuit.SinusoidalVoltageSource('lop', 'Vlop', circuit.gnd,
                                amplitude=0.1@u_V, frequency=1.2@u_kHz,
                                dc_offset=best_vlop@u_V, offset = best_vlop@u_V,
                                ac_magnitude=0.1@u_V,
                                delay=0)
circuit.SinusoidalVoltageSource('lon', 'Vlon', circuit.gnd,
                                amplitude=0.1@u_V, frequency=1.2@u_kHz,
                                dc_offset=best_vlop@u_V, offset = best_vlop@u_V,
                                ac_magnitude=0.1@u_V,
                                delay=1/(2*1.2e3)@u_s)


circuit.R('R_filter_p', 'Voutp', 'Vdd', 1@u_kOhm)
circuit.C('C_filter_p', 'Voutp', 'Vdd', 10@u_nF)

circuit.R('R_filter_n', 'Voutn', 'Vdd', 1@u_kOhm)
circuit.C('C_filter_n', 'Voutn', 'Vdd', 10@u_nF)


simulator = circuit.simulator()

# Perform transient analysis to get mixer output
print("Performing transient analysis to obtain mixing output...")
sampling_rate = 1 / (20 * 1.2e3)  # Sampling rate 20x higher than LO frequency
simulation_time = 20e-3  # Observe 20ms, multiple cycles of RF and LO
try:
    analysis = simulator.transient(step_time=sampling_rate, end_time=simulation_time)
except Exception as e:
    print(f"Error during transient simulation: {e}")
    sys.exit(2)

# Extract signals
time = analysis.time
voutp = analysis['Voutp']
voutn = analysis['Voutn']
vlop = analysis['Vlop']
vlon = analysis['Vlon']
vrfp = analysis['Vrfp']
vrfn = analysis['Vrfn']
vout_diff = voutp - voutn  # Differential output

# Perform FFT analysis

from scipy.fft import fft
from matplotlib import pyplot as plt

# Calculate FFT
n = len(time)
fft_vout = fft(vout_diff)
fft_magnitude = np.abs(fft_vout) / n * 2  # Normalize magnitude
freq = np.fft.fftfreq(n, sampling_rate)  # Frequency axis

# Keep only positive frequencies
positive_freq_mask = freq > 0
freq = freq[positive_freq_mask]
fft_magnitude = fft_magnitude[positive_freq_mask]

# Output major frequency components
print("\nFFT Analysis Results - Major Frequency Components:")
# Find top 5 frequency components
indices = np.argsort(fft_magnitude)[::-1][:5]
for i in indices:
    print(f"Frequency: {freq[i]:.1f} Hz, Magnitude: {fft_magnitude[i]:.6f} V")

# Check for mixing products
rf_freq = 1e3  # 1 kHz
lo_freq = 1.2e3  # 1.2 kHz
expected_if_down = abs(lo_freq - rf_freq)  # Down-conversion: 200 Hz
expected_if_up = lo_freq + rf_freq  # Up-conversion: 2.2 kHz

# Search for expected IF frequencies in FFT results
tolerance = 50  # Hz
found_if_down = False
found_if_up = False
if_down_magnitude = 0
if_up_magnitude = 0

for i, f in enumerate(freq):
    if abs(f - expected_if_down) < tolerance and fft_magnitude[i] > 1e-3:
        found_if_down = True
        if_down_magnitude = fft_magnitude[i]
        print(f"\nDetected down-conversion IF signal (LO-RF): {f:.1f} Hz, Magnitude: {if_down_magnitude:.6f} V")
    
    if abs(f - expected_if_up) < tolerance and fft_magnitude[i] > 1e-3:
        found_if_up = True
        if_up_magnitude = fft_magnitude[i]
        print(f"Detected up-conversion IF signal (LO+RF): {f:.1f} Hz, Magnitude: {if_up_magnitude:.6f} V")

# Plot transient simulation and FFT results
plt.figure(figsize=(12, 10))

# Subplot 1: Input signals - RF pair
plt.subplot(3, 2, 1)
plt.plot(time*1000, vrfp, label='RF+')
plt.plot(time*1000, vrfn, label='RF-')
plt.title('RF Input Signals')
plt.xlabel('Time (ms)')
plt.ylabel('Voltage (V)')
plt.legend()
plt.grid(True)

# Subplot 2: Input signals - LO pair
plt.subplot(3, 2, 2)
plt.plot(time*1000, vlop, label='LO+')
plt.plot(time*1000, vlon, label='LO-')
plt.title('LO Input Signals')
plt.xlabel('Time (ms)')
plt.ylabel('Voltage (V)')
plt.legend()
plt.grid(True)

# Subplot 3: Output signals - Voutp, Voutn
plt.subplot(3, 2, 3)
plt.plot(time*1000, voutp, label='OUT+')
plt.plot(time*1000, voutn, label='OUT-')
plt.title('Output Signals')
plt.xlabel('Time (ms)')
plt.ylabel('Voltage (V)')
plt.legend()
plt.grid(True)

# Subplot 4: Differential output
plt.subplot(3, 2, 4)
plt.plot(time*1000, vout_diff)
plt.title('Differential Output (OUT+ - OUT-)')
plt.xlabel('Time (ms)')
plt.ylabel('Voltage (V)')
plt.grid(True)

# Subplot 5: FFT of differential output - Full spectrum
plt.subplot(3, 2, 5)
max_freq_display = 5000  # Limit to 5kHz for better visibility
mask = freq < max_freq_display
plt.plot(freq[mask], fft_magnitude[mask])
plt.title('FFT Spectrum Analysis')
plt.xlabel('Frequency (Hz)')
plt.ylabel('Magnitude (V)')
plt.grid(True)

# Mark key frequencies
plt.axvline(x=rf_freq, color='b', linestyle='--', label='RF')
plt.axvline(x=lo_freq, color='m', linestyle='--', label='LO')
if found_if_down:
    plt.axvline(x=expected_if_down, color='r', linestyle='--', label='IF down')
if found_if_up:
    plt.axvline(x=expected_if_up, color='g', linestyle='--', label='IF up')
plt.legend()

# Subplot 6: FFT - Zoomed in on important frequencies
plt.subplot(3, 2, 6)
zoom_mask = (freq < 3000) & (freq > 0)  # Focus on 0-3kHz range
plt.plot(freq[zoom_mask], fft_magnitude[zoom_mask])
plt.title('FFT Spectrum (Zoomed)')
plt.xlabel('Frequency (Hz)')
plt.ylabel('Magnitude (V)')
plt.grid(True)

# Mark and annotate key frequencies in zoomed view
key_freqs = [rf_freq, lo_freq, expected_if_down, expected_if_up]
key_labels = ['RF (1kHz)', 'LO (1.2kHz)', 'IF down (200Hz)', 'IF up (2.2kHz)']
key_colors = ['b', 'm', 'r', 'g']

for f, label, color in zip(key_freqs, key_labels, key_colors):
    if f < 3000:  # Only mark if in zoomed range
        plt.axvline(x=f, color=color, linestyle='--')
        # Find closest frequency in our FFT data
        idx = np.argmin(np.abs(freq - f))
        if idx < len(freq) and zoom_mask[idx]:
            plt.annotate(label, 
                         xy=(freq[idx], fft_magnitude[idx]),
                         xytext=(10, 10), 
                         textcoords='offset points',
                         arrowprops=dict(arrowstyle='->'),
                         color=color)

plt.tight_layout()
plt.savefig('[FIGURE_PATH].png')
# plt.show()

# Evaluate mixer performance
if found_if_down and found_if_up:
    print("\nMixer functioning correctly: Mixing products detected!")
    
    # Calculate conversion efficiency
    rf_index = np.argmin(np.abs(freq - rf_freq))
    rf_magnitude = fft_magnitude[rf_index]
    
    if found_if_down:
        conversion_gain_down = 20 * np.log10(if_down_magnitude / rf_magnitude)
        print(f"Down-conversion gain: {conversion_gain_down:.2f} dB")
    
    if found_if_up:
        conversion_gain_up = 20 * np.log10(if_up_magnitude / rf_magnitude)
        print(f"Up-conversion gain: {conversion_gain_up:.2f} dB")
    
    # Evaluate LO leakage
    lo_index = np.argmin(np.abs(freq - lo_freq))
    lo_leakage = fft_magnitude[lo_index]
    if found_if_down:
        lo_rejection = 20 * np.log10(if_down_magnitude / lo_leakage)
        print(f"LO rejection ratio: {lo_rejection:.2f} dB")
    
    # Overall evaluation
    print("\nMixer performance assessment:")
    if found_if_down and if_down_magnitude > 1e-3:
        print("✓ Down-conversion functioning properly")
    if found_if_up and if_up_magnitude > 1e-3:
        print("✓ Up-conversion functioning properly")
    
    print("The Gilbert Cell Mixer is functioning correctly.")
    print("Plots saved as 'mixer_analysis.png'")
    sys.exit(0)  # Exit with success status code
else:
    print("\nMixer malfunction: Expected mixing products not detected!")
    print("Check the following possible issues:")
    print("1. RF and LO signal amplitudes might be insufficient")
    print("2. Circuit connections might be incorrect")
    print("Plots saved as 'mixer_analysis.png'")
    sys.exit(2)  # Exit with error status code