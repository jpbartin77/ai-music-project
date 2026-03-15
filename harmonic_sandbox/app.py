import streamlit as st
import asyncio
import os
import time
import nest_asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, GenerationConfig
from visualizer import create_piano_roll

# --- 1. PATCH ASYNC LOOP ---
nest_asyncio.apply()

# --- 2. CONFIG & AUTH ---
user_home = os.path.expanduser("~")
adc_path = os.path.join(user_home, ".config", "gcloud", "application_default_credentials.json")
if os.path.exists(adc_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = adc_path

PROJECT_ID = "excellent-badge-484603-h7"
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)

# --- 3. PAGE SETUP (Must be early) ---
st.set_page_config(page_title="Harmonic Sandbox", page_icon="🎹")

# --- 4. TOOL DEFINITION ---
play_progression_func = FunctionDeclaration(
    name="play_progression",
    description="Generates a MIDI file.",
    parameters={
        "type": "object",
        "properties": {
            "chord_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of chord symbols (e.g. ['Cm7', 'F7'])."
            }
        },
        "required": ["chord_list"]
    }
)
music_tool = Tool(function_declarations=[play_progression_func])

# --- 5. CORE LOGIC (The Composer) ---
async def process_request(user_prompt, is_blind_mode):
    # Clean up old file
    if os.path.exists("generated_progression.mid"):
        try: os.remove("generated_progression.mid")
        except: pass

    # THE COMPOSER PROMPT
    full_prompt = f"""
    ROLE: You are an expert Jazz Composer and Music Theorist.
    
    USER REQUEST: "{user_prompt}"
    
    INSTRUCTIONS:
    1. ANALYZE the user's request. If they describe a mood (e.g., "sad", "jazzy") but do not list chords, YOU MUST INVENT THE CHORDS.
    2. CALL THE TOOL `play_progression` immediately with your chords.
    3. AFTER the tool call, provide a "Harmonic Analysis":
       - Roman Numerals.
       - One theory concept.
       - One famous song.
       
    DO NOT ASK THE USER FOR CHORDS. YOU ARE THE COMPOSER.
    """

    # Force correct python path
    server_params = StdioServerParameters(
        command=sys.executable, args=["server.py"], env=os.environ.copy()
    )

    result_payload = {"type": "text", "content": ""}

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                model = GenerativeModel("gemini-2.0-flash-001", tools=[music_tool])
                chat = model.start_chat()
                response = chat.send_message(full_prompt)
                
                # Check for Tool
                if response.candidates and response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    if part.function_call and part.function_call.name == "play_progression":
                        # CALL TOOL
                        chords = list(part.function_call.args["chord_list"])
                        await session.call_tool("play_progression", arguments={"chord_list": chords})
                        
                        # GET ANALYSIS TEXT
                        analysis = ""
                        if len(response.candidates[0].content.parts) > 1:
                            analysis = response.candidates[0].content.parts[1].text
                        else:
                            fup = chat.send_message("Provide the Harmonic Analysis now.")
                            analysis = fup.text
                        
                        # PACKAGE RESULT
                        result_payload = {
                            "type": "music",
                            "chords": chords,
                            "analysis": analysis,
                            "mid_path": "generated_progression.mid"
                        }
                    else:
                        result_payload = {"type": "text", "content": response.text}

    except Exception as e:
        result_payload = {"type": "text", "content": f"Error: {e}"}

    return result_payload

# --- 6. UI LAYOUT ---
st.title("🎹 Harmonic Sandbox")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar
with st.sidebar:
    st.header("🎛️ Controls")
    blind_mode_on = st.toggle("🕵️ Blind Test Mode")

# --- 7. DISPLAY HISTORY ---
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        with st.chat_message("assistant"):
            if msg.get("type") == "music":
                # Render Music Block
                st.success(f"Generated: {msg['chords']}")
                
                if os.path.exists(msg['mid_path']):
                    with open(msg['mid_path'], "rb") as f:
                        st.download_button("🎵 Download MIDI", f, "progression.mid", "audio/midi", key=f"dl_{msg['id']}")
                
                # Analysis Logic
                if msg.get("blind_mode", False):
                    if st.button("👁️ Reveal Analysis", key=f"rev_{msg['id']}"):
                        st.markdown(msg["analysis"])
                        st.image("piano_roll.png", width="stretch")
                    else:
                        st.info("🙈 Analysis Hidden (Blind Mode)")
                else:
                     with st.expander("🎼 Harmonic Analysis", expanded=True):
                        st.markdown(msg["analysis"])
                     st.image("piano_roll.png", width="stretch")

            else:
                st.write(msg["content"])

# --- 8. HANDLE INPUT ---
if prompt := st.chat_input("Play a jazz chord progression..."):
    # Add User Message & Rerun
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

# --- 9. HANDLE PROCESSING ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with st.chat_message("assistant"):
        with st.spinner("Composing..."):
            last_prompt = st.session_state.messages[-1]["content"]
            response_data = asyncio.run(process_request(last_prompt, blind_mode_on))
            
            # SAVE TO HISTORY
            msg_id = int(time.time())
            if response_data["type"] == "music":
                create_piano_roll(response_data["mid_path"], "piano_roll.png")
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "type": "music",
                    "id": msg_id,
                    "chords": response_data["chords"],
                    "analysis": response_data["analysis"],
                    "mid_path": response_data["mid_path"],
                    "blind_mode": blind_mode_on
                })
            else:
                st.session_state.messages.append({
                    "role": "assistant",
                    "type": "text",
                    "content": response_data["content"]
                })
            
            st.rerun()