from mcp.server.fastmcp import FastMCP
from chord_engine import generate_progression
import os

# 1. Initialize the Server
# This name is what the AI sees as the "Toolbox" name
mcp = FastMCP("Harmonic Sandbox")

# 2. Define the Tool
# The @mcp.tool() decorator tells the AI: "You can use this function!"
@mcp.tool()
def play_progression(chord_list: list[str]) -> str:
    """
    Generates a MIDI file from a list of chord symbols.
    Useful for creating backing tracks, testing chord progressions, or ear training.
    
    Args:
        chord_list: A list of chord symbols (e.g. ['Cm7', 'F7', 'Bbmaj7'])
    """
    # Define a static output name for the demo
    filename = "generated_progression.mid"
    
    # Call your original engine
    success = generate_progression(chord_list, filename)
    
    if success:
        # We return text to the AI so it knows what happened
        return f"SUCCESS: Created {filename}. Tell the user to download it and listen!"
    else:
        return "ERROR: Could not generate the file. Check the chord symbols."

# 3. Run the Server
if __name__ == "__main__":
    mcp.run()