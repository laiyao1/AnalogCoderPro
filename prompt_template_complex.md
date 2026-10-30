You aim to design a topology for a given circuit described in the text. 
Please ensure your designed circuit topology works properly and achieves the design requirements. 

To make the task easier, you can directly use the opamp subcircuits by inserting:

```python
from opamp import *
# Declare the operational amplifier subcircuit
circuit.subcircuit(Opamp())
# Create a subcircuit instance
# Parameter order: first parameter is the instance name, second is the subcircuit name
# Third parameter is the non-inverting input
# Fourth parameter is the inverting input
# Fifth parameter is the output
circuit.X('1', 'Opamp', 'Vinp', 'Vinn', 'Vout')
```

The DC bias voltage for both input terminals (Vinn and Vinp) is 2.5V. For AC coupling/grounding purposes, these terminals should be referenced to the 2.5V power supply rather than ground.

Here is an example:

## Question 
Design an opamp circuit with 470 ohm resistive load.

Input node name: Vin.
Output node name: Vout.

## Answer

```python
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from opamp import *

circuit = Circuit('Operational Amplifier with Single Supply')

# Define the MOSFET models
circuit.model('nmos_model', 'nmos', level=1, kp=100e-6, vto=0.5)
circuit.model('pmos_model', 'pmos', level=1, kp=50e-6, vto=-0.5)

# Power supply
circuit.V('dd', 'Vdd', circuit.gnd, 5@u_V)

# Set reference voltage (2.5V) as virtual ground
circuit.V('ref', 'Vref', circuit.gnd, 2.5@u_V)  # Virtual ground at Vdd/2

# Set DC bias voltage for the input
circuit.V('in', 'Vin', circuit.gnd, 3@u_V)

# Declare the opamp subcircuit
circuit.subcircuit(Opamp())

# Create opamp instance (non-inverting configuration)
# Parameters: instance_name, subcircuit_name, non_inverting_input, inverting_input, output
circuit.X('op', 'Opamp', 'Vin', 'Vref', 'Vout')

# Add 470 ohm load resistor connected to Vref (virtual ground), NOT to actual ground
circuit.R('load', 'Vout', 'Vref', 470@u_Ω)  # Load connected to virtual ground

simulator = circuit.simulator()
```


As you have seen, the output of your designed topology should be in a complete Python code, describing the topology of integrated analog circuits according to the design plan. 

Please make sure your Python code is compatible with PySpice. 
Please give the runnable code without any placeholders.
Do not write other redundant codes after ```simulator = circuit.simulator()```.

There are some tips you should remember all the time:
1. For the MOSFET definition circuit.MOSFET(name, drain, gate, source, bulk, model, w=w1,l=l1), be careful about the parameter sequence. For example, ```circuit.MOSFET('1', 'Drain1', 'Vin', circuit.gnd, circuit.gnd, model='nmos_model', w=50e-6, l=1e-6)```.
2. You should connect the bulk of a MOSFET to its source.
3. Please use the MOSFET threshold voltage, when setting the bias voltage.
4. Avoid giving any AC voltage in the sources, just consider the operating points.
5. Make sure the input and output node names appear in the circuit.
6. Use nominal transistor sizing.
7. Assume the Vdd = 5.0 V. Do not need to add the power supply for subcircuits.

Please first give a detailed design plan and then write the code.

## Question

Design [TASK].

Input node name: [INPUT].

Output node name: [OUTPUT].


## Answer


