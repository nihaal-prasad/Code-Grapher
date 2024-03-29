import r2pipe
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import argparse
import os
import concurrent.futures

# Setup the argument parser
parser = argparse.ArgumentParser(description="Analyzes specified lines of code by executing the code using the given input values, recording the output, and displaying the input and output in a graph.", usage='%(prog)s [options] filename start stop input output range')
parser.add_argument("filename", help="The name of the executable you would like to analyze.")
parser.add_argument("start", help="The first breakpoint will be set at this location. At the breakpoint, the input register or memory location will be changed to the next value in the range.")
parser.add_argument("stop", help="The second breakpoint will be set at this location. At the breakpoint, the output will be recorded.")
parser.add_argument("input", help="The register or memory location that contains the input value that should be bruteforced. Will be displayed on the x-axis. Example: \"eax\". If using a memory location, please specify the location using m[location]. Example: \"m[rbp-0x8]\".")
parser.add_argument("output", help="The register or memory location that contains the output values that should be checked after the code is executed. Will be displayed on the y-axis. Example: \"eax\". If using a memory location, please specify the location using m[location]. Example: \"m[rbp-0x8]\".")
parser.add_argument("range", help="The range of values that should be used for the input during the bruteforce process. Should be in the form \"[lower,upper]\" or \"[lower,upper,step]\". For example: [0,101,5] will use 0, 5, 10, ..., 95, 100 as the x values in the graph. These must be in base 10 (hexadecimal or binary will not work).")

# Add optional arguments
parser.add_argument("-t", "--threads", nargs='?', dest="threads", default="5", help="The number of threads that will be used during execution. Default value is 5.")
parser.add_argument("-in", "--standard-input", nargs='?', dest='input_file', default='', help="Uses the \'dor stdin=[INPUT_FILE]\' command in radare2 to make the executable read standard input from a given file instead of having the user type it in.")
parser.add_argument("-il", "--input-length", nargs='?', dest='input_length', default='1', help="The amount of bytes placed at the input memory location. Default value is 1, but this will be automatically adjusted if it is too small. Is only used if the input is a memory location and not a register.")
parser.add_argument("-ol", "--output-length", nargs='?', dest='output_length', default='1', help="The amount of bytes read at the output memory location. Must be equal to either 1, 2, 4, or 8. Default value is 1. Is only used if the output is a memory location and not a register.")
parser.add_argument("-e", "--execute", nargs='?', dest='commands', type=str, default='', help="Executes the given r2 commands in radare2 right after the debugger hits the first breakpoint, but before the input value is set. Example: -e \"dr ebx = 7\" will always set ebx equal to 7 at the first breakpoint. Multiple commands can be separated by a semicolon.")
parser.add_argument("-hx", "--x-axis-hex", dest='x_is_hex', action='store_const', const=True, default=False, help="Displays the x-axis in hexadecimal instead of denary.")
parser.add_argument("-hy", "--y-axis-hex", dest='y_is_hex', action='store_const', const=True, default=False, help="Displays the y-axis in hexadecimal instead of denary.")
parser.add_argument("-j", "--jump", dest='jump', action='store_const', const=True, default=False, help="Instead of running all of the code that comes before the breakpoint, if this option is set, rip/eip will immidiately be set to the start value as soon as the program opens. This will essentially jump over any code that comes before the first breakpoint, and it will make the program only execute the code between the starting and stopping breakpoints.")

# Parse all of the arguments
args = parser.parse_args()
filename = args.filename
start = args.start
stop = args.stop
bruteforce = args.input
bruteforceIsMem = False
if(bruteforce.startswith("m[") and bruteforce[-1]==']'):
    bruteforceIsMem = True
    bruteforce = bruteforce[2:-1]
output = args.output
outputIsMem = False
if(output.startswith("m[") and output[-1]==']'):
    outputIsMem = True
    output = output[2:-1]
valueRange = args.range.split(",")
lower_bound = int(valueRange[0].split("[")[1])
upper_bound = valueRange[1]
if("]" in upper_bound):
    upper_bound = int(upper_bound[:-1])
else:
    upper_bound = int(upper_bound)
step = 1
if(len(valueRange) == 3):
    step = int(valueRange[2][:-1])
threads = int(args.threads)
input_file = args.input_file
input_length = args.input_length
output_length = args.output_length
commands = args.commands
x_is_hex = args.x_is_hex
y_is_hex = args.y_is_hex
jump = args.jump

# List of tuples that contain the input and its corresponding output. These points will eventually be plotted onto the graph.
points = []

def execute(value):
    """ Executes some code using the given input and returns the output. """
    # Load the binary in radare2
    r = r2pipe.open(filename, flags=['d', 'A'])

    # If the standard input option is set, then set use the dor command to set stdin to the given file
    if(input_file != ''):
        r.cmd('dor stdin=' + input_file)

    # Reopen the program and set a breakpoint at the stopping point
    r.cmd('doo;db ' + stop)
    if(jump): # If jump is set to true, then we will set rip to be the starting memory location
        r.cmd('dr rip = ' + start) # One of these will work (based on whether its 32-bit or 64-bit), the other will not
        r.cmd('dr eip = ' + start) # Since r2 will just ignore the command that doesn't work, it's okay if we just execute both of these
    else: # Else, just set a breakpoint at that instruction and continue
        r.cmd('db ' + start + ";dc")

    # Execute any r2 commands that the user wants to have executed
    r.cmd(commands)

    # Set the register/memory location that we are bruteforcing to the value that we want it
    if(bruteforceIsMem):
        hex_value = hex(value)[2:] # Convert the value to hex and delete the "0x" part of it
        r.cmd('w0 ' + input_length + " @" + bruteforce) # Clears out the memory at the location
        r.cmd('wB 0x' + hex_value + " @" + bruteforce) # Overwrites the memory location with the value that we are bruteforcing it with
    else:
        r.cmd('dr ' + bruteforce + ' = ' + str(value)) # If it's a register, then we just need to use the "dr" command.

    # Continue execution
    r.cmd('dc')

    # Read the value of the register/memory location that needs to be checked and record it
    result = 0
    if(outputIsMem):
        result = int(r.cmd('pv' + output_length + ' @' + output), 16)
    else:
        result = int(r.cmd('dr ' + output).strip(), 16)

    # Add the point to the list of points
    points.append((value, result))

# Use a ThreadPoolExecutor to call execute() using range(lower_bound, upper_bound, step) in a given number of threads
with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
    executor.map(execute, range(lower_bound, upper_bound, step))

# Print out the points in sorted order
print("Points:")
print(sorted(points, key=lambda x: x[0]))

# Convert the list of points into two tuples. The first tuple will contain the x values (inputs) and the second tuple will contain the y values (results). 
# This is done to convert the points into a format that matplotlib accepts
xy = zip(*points)

# Plot the graph
plt.scatter(*xy)
plt.title('Bruteforcing ' + bruteforce + ' @' + start)
plt.xlabel(bruteforce + '\'s starting values @' + start)
plt.ylabel(output + '\'s ending values @' + stop)

# Display the results in hex if necessary
axes = plt.gca()

if(x_is_hex): # Displays x-axis in hex if necessary
    xlabels = map(lambda t: '0x%08X' % int(t), axes.get_xticks())
    axes.set_xticklabels(xlabels)
if(y_is_hex): # Displays y-axis in hex if necessary
    ylabels = map(lambda t: '0x%08X' % int(t), axes.get_yticks())
    axes.set_yticklabels(ylabels)

# Show the results
plt.show()
