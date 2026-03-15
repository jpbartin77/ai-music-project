import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_agent():
    print("🤖 Agent starting...")
    
    # 1. Define the connection to your server
    server_params = StdioServerParameters(
        command="python", # The command to launch the server
        args=["server.py"], # The file to run
        env=os.environ.copy() # Pass current environment (venv)
    )

    # 2. Connect to the server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the handshake
            await session.initialize()
            
            # 3. Ask: "What tools do you have?"
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"🔎 Discovered Tools: {tool_names}")
            
            if "play_progression" in tool_names:
                print("\n🎹 Requesting a Jazz Turnaround (Dm7 - G7 - Cmaj7)...")
                
                # 4. Use the Tool
                result = await session.call_tool(
                    "play_progression", 
                    arguments={"chord_list": ["Dm7", "G7", "Cmaj7"]}
                )
                
                # 5. Print the Result
                print(f"✅ AI Response: {result.content[0].text}")
            else:
                print("❌ Error: Could not find the play_progression tool.")

if __name__ == "__main__":
    asyncio.run(run_agent())