I need to convert my PySpice circuit netlist into a parameterized form for automated optimization. Please transform the following original circuit description into a parameter-based implementation with appropriate search ranges.

## Input:
Please convert the circuit code I'll provide below. For reference, here's an example of what an original circuit might look like:

```python
circuit = Circuit('Two-Stage CMOS Op-Amp')
circuit.V('dd', 'vdd', circuit.gnd, 1.2)  # Using 1.2V supply for 45nm technology
circuit.V('in', 'Vin', circuit.gnd, 0.6)  # Typical mid-range voltage for 1.2V supply
circuit.M('1', 'out', 'in', circuit.gnd, circuit.gnd, model='nmos', w=10e-6, l=45e-9)  # 45nm technology
circuit.R('load', 'out', 'vdd', 5@u_kΩ)
circuit.C('comp', 'out', 'Vin', 2@u_pF)
```

Here is my actual circuit code:

```python
[CODE]
```

## Required Output:
1. A circuit creation function that uses a `params` dictionary
2. A parameter search range dictionary (for Optuna or similar optimization tools)
3. Reasonable parameter constraints with tailored search ranges:
   - Transistor width (W) should be within 1-500× the corresponding length (L)
   - All voltage sources (except vdd and input voltages Vin/Vinp/Vinn) within 0.8-1.2× their original values, not exceeding 1.2V
   - Resistors within 0.5-2× their original values
   - Critical compensation capacitors within 0.5-5× their original values
   - Other capacitors within 0.8-1.5× their original values

## Specific Requirements:
- The circuit creation function MUST be named `create_circuit` - this name is required for compatibility with the optimization framework
- Keep vdd as a fixed value (1.2V), do not include it in the parameter search
- Keep input voltages (Vin, Vinp, Vinn) as fixed values, as they will be swept during DC analysis to find suitable operating points
- Convert all other fixed values (transistor dimensions, other voltages, resistors, capacitors) to parameterized form
- Since only the W/L ratio affects circuit behavior, please keep L constant (typically 45nm for this technology) and only include W in the optimization parameters
- Define appropriate search ranges for each parameter according to the constraints above
- All voltage sources must always be less than or equal to 1.2V
- Bias point shifts should be kept conservative to maintain circuit operation in the intended region
- Consider the MOSFET threshold voltage (Vth = 0.22V) when setting bias voltage ranges
- Output format should include:
  1. Parameterized circuit creation function named `create_circuit`
  2. Annotated optimization parameter search ranges
  3. Brief description of the physical meaning of each parameter
- Keep the import statement "from model import nmos_params, pmos_params" exactly as written in the parameterized circuit function. This module will be available in the execution environment.
- **IMPORTANT**: Make sure the initial_params dictionary contains EXACTLY the original values from my circuit code WITHOUT any modifications. These exact values must be preserved as the starting point for optimization.
- **IMPORTANT**: Ensure that all initial parameter values are within their respective search ranges.
- **IMPORTANT**: Keep load capacitors (C_load) as fixed values using the original values from the circuit code. DO NOT include load capacitors in the parameter search.

## Example Output Format:
```python
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from model import nmos_params, pmos_params

def create_circuit(params):
    circuit = Circuit('Two-Stage CMOS Op-Amp')

    circuit.model('nmos_model', 'nmos', **nmos_params)
    circuit.model('pmos_model', 'pmos', **pmos_params)

    # Power supply (fixed, not parameterized)
    circuit.V('dd', 'vdd', circuit.gnd, 1.2)  # 1.2V for 45nm technology
    
    # Input voltage source (fixed, not parameterized)
    circuit.V('in', 'Vin', circuit.gnd, 0.6)  # Mid-range for 1.2V supply
    
    # NMOS transistor
    circuit.M('1', 'out', 'in', circuit.gnd, circuit.gnd, 
              model='nmos', 
              w=params['w_M1'],
              l=45e-9)  # Length fixed by 45nm process
    
    # Load resistor - convert parameter to ngspice unit
    circuit.R('load', 'out', 'vdd', f"{params['r_load']}k")
    
    # Compensation capacitor - convert parameter to ngspice unit
    circuit.C('comp', 'out', 'Vin', f"{params['c_comp']}p")
        
    return circuit

# Optimization parameter search ranges
# Parameter range definition (without trial)
param_ranges_definition = {
    # Transistor dimensions
    'w_M1': {'min': 45e-9, 'max': 22.5e-6, 'log': True},  # Width range: 1-500× length
    
    # Passive components
    'r_load': {'min': 2.5, 'max': 10, 'log': True},     # Load resistor: 0.5-2× original (kΩ)
    'c_comp': {'min': 1.0, 'max': 10, 'log': True},     # Compensation cap: 0.5-5× original (pF)
}

# Initial parameter values (EXACT original circuit values)
initial_params = {
    'w_M1': 10e-6,   # Original width value
    'r_load': 5,      # Original resistance (kΩ)
    'c_comp': 2,      # Original capacitance (pF)
}
```

Please follow these requirements to convert my circuit netlist into a parameterized form suitable for automated optimization. Pay special attention to keeping voltage ranges conservative to avoid drifting too far from the intended operating point. For all voltage sources (except vdd and input voltages Vin/Vinp/Vinn which should remain fixed), use a consistent range of 0.8-1.2× the original value (but never exceeding 1.2V, which is the supply voltage for this 45nm technology with Vth = 0.22V). The function MUST be named `create_circuit` as this is required for compatibility with the optimization framework. Load capacitors should remain fixed at their original values and should NOT be included in the parameter search.