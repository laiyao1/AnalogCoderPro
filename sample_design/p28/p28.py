import math
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from opamp import *
circuit = Circuit('Non-inverting Schmitt Trigger')
# Power supply
circuit.V('dd', 'Vdd', circuit.gnd, 5@u_V)
# Reference voltage (virtual ground)
circuit.V('ref', 'Vref', circuit.gnd, 2.5@u_V)
# Input voltage (DC operating point)
circuit.V('in', 'Vin', circuit.gnd, 2.7@u_V)
# Declare opamp subcircuit
circuit.subcircuit(Opamp())
# Non-inverting Schmitt trigger configuration:
# Non-inverting input (Vp): receives Vin through R1, feedback from Vout through R2, and pulled to Vref through R3
# Inverting input (Vn): connected to Vref
# Resistor from Vin to non-inverting input
circuit.R('1', 'Vin', 'Vp', 10@u_kΩ)
# Feedback resistor from Vout to non-inverting input
circuit.R('2', 'Vout', 'Vp', 100@u_kΩ)
# Pull-down resistor from non-inverting input to Vref
circuit.R('3', 'Vp', 'Vref', 10@u_kΩ)
# Instantiate opamp: X('name', 'subckt', non-inv, inv, out)
circuit.X('op', 'Opamp', 'Vp', 'Vref', 'Vout')
simulator = circuit.simulator()
for element in circuit.elements:
    if element.name.lower().startswith("vin"):
        v_name = element.name

circuit.element(v_name).detach()
circuit.SinusoidalVoltageSource('in', 'Vin', circuit.gnd, 
                               amplitude=0.8@u_V,
                               offset=2.5@u_V,
                               frequency=0.1@u_kHz)
pin_name = "Vinp"
pin_name_n = "Vinn"
pin_name_out = "Vout"
for element in circuit.elements:
    if element.name.lower().startswith("x"):
        opamp_element = element
        pin_name = str(opamp_element.pins[0].node)
        pin_name_n = str(opamp_element.pins[1].node)
        pin_name_out = str(opamp_element.pins[2].node)
        break

circuit.C('stab1', pin_name, circuit.gnd, 1@u_pF)
circuit.C('stab2', pin_name_n, circuit.gnd, 1@u_pF)
circuit.C('stab3', pin_name_out, circuit.gnd, 1@u_pF)

import sys
try:
    analysis = simulator.transient(step_time=10@u_us, end_time=50@u_ms, 
                                  use_initial_condition=True)
except:
    print("Analysis failed.")
    sys.exit(2)

import numpy as np
# Extract data
time = np.array(analysis.time)
vin = np.array(analysis['Vin'])
vout = np.array(analysis['Vout'])

# Find sections of rising and falling input
# Alternative approach to separate rising and falling data
rising_indices = np.where(np.diff(vin) > 0)[0]
falling_indices = np.where(np.diff(vin) < 0)[0]

# Extract rising and falling data
vin_rising = vin[rising_indices]
vout_rising = vout[rising_indices]
vin_falling = vin[falling_indices]
vout_falling = vout[falling_indices]

# Set threshold for detecting trigger points (half of power supply)
threshold = 2.5

# ===========================================
# First plot basic waveforms for debugging
# ===========================================

import matplotlib.pyplot as plt
plt.figure(figsize=(12, 12))

# First subplot - Time domain response
plt.subplot(3, 1, 1)
plt.plot(time*1000, vin, 'b-', label='Vin')
plt.plot(time*1000, vout, 'r-', label='Vout')
plt.axhline(y=threshold, color='g', linestyle='--', label='Threshold (2.5V)')
plt.legend()
plt.title('Schmitt Trigger Time Domain Response')
plt.xlabel('Time [ms]')
plt.ylabel('Voltage [V]')
plt.grid(True)

# Second subplot - Input/Output transfer curve (hysteresis)
plt.subplot(3, 1, 2)
plt.plot(vin, vout, 'g-', label='Transfer Curve')
plt.axhline(y=threshold, color='k', linestyle='--', label='Threshold (2.5V)')
plt.legend()
plt.title('Hysteresis Curve')
plt.xlabel('Vin [V]')
plt.ylabel('Vout [V]')
plt.grid(True)

# Third subplot - Separate rising and falling edge responses
plt.subplot(3, 1, 3)
plt.plot(vin_rising, vout_rising, 'b-', label='Rising Edge')
plt.plot(vin_falling, vout_falling, 'r-', label='Falling Edge')
plt.axhline(y=threshold, color='k', linestyle='--', label='Threshold (2.5V)')
plt.legend()
plt.title('Rising vs Falling Edge Response')
plt.xlabel('Vin [V]')
plt.ylabel('Vout [V]')
plt.grid(True)

plt.tight_layout()
plt.savefig("sample_design/p28/p28_waveform.png")

# ===========================================
# Perform quantitative analysis after viewing waveforms
# ===========================================

print("\nStarting trigger point analysis...")

try:
    # Find rising edge trigger point
    rising_cross_indices = np.where(np.diff(vout_rising > threshold) > 0)[0]
    if len(rising_cross_indices) > 0:
        rising_index = rising_cross_indices[0]
        # Use linear interpolation for more precise trigger point
        v1 = vout_rising[rising_index]
        v2 = vout_rising[rising_index + 1]
        i1 = vin_rising[rising_index]
        i2 = vin_rising[rising_index + 1]
        
        # Linear interpolation to calculate exact trigger voltage
        if v2 != v1:  # Avoid division by zero
            t = (threshold - v1) / (v2 - v1)
            trigger_vin_rising = i1 + t * (i2 - i1)
        else:
            trigger_vin_rising = i1
    else:
        print("Warning: No threshold crossing detected for rising edge")
        trigger_vin_rising = None

    # Find falling edge trigger point
    falling_cross_indices = np.where(np.diff(vout_falling < threshold) > 0)[0]
    if len(falling_cross_indices) > 0:
        falling_index = falling_cross_indices[0]
        # Use linear interpolation for more precise trigger point
        v1 = vout_falling[falling_index]
        v2 = vout_falling[falling_index + 1]
        i1 = vin_falling[falling_index]
        i2 = vin_falling[falling_index + 1]
        
        # Linear interpolation to calculate exact trigger voltage
        if v2 != v1:  # Avoid division by zero
            t = (threshold - v1) / (v2 - v1)
            trigger_vin_falling = i1 + t * (i2 - i1)
        else:
            trigger_vin_falling = i1
    else:
        print("Warning: No threshold crossing detected for falling edge")
        trigger_vin_falling = None
        
    # Output detection results
    if trigger_vin_rising is not None and trigger_vin_falling is not None:
        hysteresis_width = abs(trigger_vin_rising - trigger_vin_falling)
        print(f"Rising edge trigger point: {trigger_vin_rising:.5f}V")
        print(f"Falling edge trigger point: {trigger_vin_falling:.5f}V")
        print(f"Hysteresis width: {hysteresis_width:.5f}V")
        
        # Check if Schmitt trigger is working properly
        if hysteresis_width <= 0.01:
            print("The circuit does not function correctly. Trigger points are too close.")
            print(f"Trigger points: {trigger_vin_rising:.5f}V and {trigger_vin_falling:.5f}V are not sufficiently different.")
            print("Please ensure proper positive feedback connection, where Rf should connect to the non-inverting input of the op-amp.")
            sys.exit(2)
        elif max(vout) - min(vout) < 2.5:
            print("The circuit does not function correctly. The output voltage does not vary more than Vdd/2.")
            sys.exit(2)
        else:
            print("The circuit functions correctly with different trigger points.")
        # Plot final graph with detected trigger points
        plt.figure(figsize=(12, 12))
        
        # Time domain response - with trigger points marked
        plt.subplot(3, 1, 1)
        plt.plot(time*1000, vin, 'b-', label='Vin')
        plt.plot(time*1000, vout, 'r-', label='Vout')
        plt.axhline(y=threshold, color='g', linestyle='--', label='Threshold (2.5V)')
        # Mark rising and falling edge trigger points (need to find closest time point)
        rising_time_idx = np.argmin(np.abs(vin_rising - trigger_vin_rising))
        falling_time_idx = np.argmin(np.abs(vin_falling - trigger_vin_falling))
        plt.plot(time[rising_indices[rising_time_idx]]*1000, threshold, 'go', markersize=8, label='Rising Trigger')
        plt.plot(time[falling_indices[falling_time_idx]]*1000, threshold, 'mo', markersize=8, label='Falling Trigger')
        plt.legend()
        plt.title('Schmitt Trigger Response with Trigger Points')
        plt.xlabel('Time [ms]')
        plt.ylabel('Voltage [V]')
        plt.grid(True)
        
        # Hysteresis curve - with trigger points marked
        plt.subplot(3, 1, 2)
        plt.plot(vin, vout, 'g-', label='Transfer Curve')
        plt.plot(trigger_vin_rising, threshold, 'bo', markersize=8, 
                 label=f'Rising Trigger: {trigger_vin_rising:.3f}V')
        plt.plot(trigger_vin_falling, threshold, 'ro', markersize=8, 
                 label=f'Falling Trigger: {trigger_vin_falling:.3f}V')
        plt.axhline(y=threshold, color='k', linestyle='--')
        plt.legend()
        plt.title(f'Hysteresis Curve (Width: {hysteresis_width:.3f}V)')
        plt.xlabel('Vin [V]')
        plt.ylabel('Vout [V]')
        plt.grid(True)
        
        # Separate rising and falling responses
        plt.subplot(3, 1, 3)
        plt.plot(vin_rising, vout_rising, 'b-', label='Rising Edge')
        plt.plot(vin_falling, vout_falling, 'r-', label='Falling Edge')
        plt.plot(trigger_vin_rising, threshold, 'bo', markersize=8)
        plt.plot(trigger_vin_falling, threshold, 'ro', markersize=8)
        plt.axhline(y=threshold, color='k', linestyle='--', label='Threshold')
        plt.legend()
        plt.title('Rising vs Falling Response with Trigger Points')
        plt.xlabel('Vin [V]')
        plt.ylabel('Vout [V]')
        plt.grid(True)
        
        plt.tight_layout()
        plt.savefig("sample_design/p28/p28_waveform.png")
    else:
        print("Analysis could not be completed as one or more trigger points were not detected.")
        sys.exit(2)

except Exception as e:
    print(f"Error analyzing trigger points: {e}")
    sys.exit(2)
    # import traceback
    # traceback.print_exc()

print("Simulation and analysis completed successfully!")
sys.exit(0)