# Splunk SPL Cheat Sheet

## Piano Practice Queries

| Query | Purpose |
|-------|---------|
| `index=edge_hub_mqtt source="piano/notes" \| table _time, hand, name, finger, midi, velocity, scale, session_id` | View individual note events — one row per note played |
| `index=edge_hub_mqtt source="piano/sessions" \| table _time, scale_display, segment_index, session_id` | View session summaries — one row per completed scale run |
