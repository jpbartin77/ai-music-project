# AI Music Project

> **Status (2026-09-04): reference only.** This project served two April 2026 presentations and is no longer under active development. The code, notes, and architecture are kept as a working reference for the piano-as-sensor-network pattern (MIDI → Splunk HEC → MCP → Claude coach → Webex card). dCloud addresses and tokens referenced here are stale.

A personal learning project unifying three areas:
- Piano and MIDI capture
- Music theory
- AI/ML model training

## Project Goals
- Capture live MIDI from a digital piano via USB
- Analyze musical patterns using Python
- Train AI models on personal playing data
- Build a live call-and-response system using Claude via MCP
- Route AI-generated notes through Reaper to Pianoteq/VSL

## Tech Stack
- Python 3.13 + venv
- mido, python-rtmidi, pretty_midi, numpy, matplotlib, jupyter
- Reaper + reapy bridge
- Anthropic Claude API (MCP)

## Status
Environment setup complete. Beginning Phase 1 — MIDI capture.
```