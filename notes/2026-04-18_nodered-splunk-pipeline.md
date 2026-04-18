# Node-RED → Splunk Pipeline Configuration (April 18, 2026)

## Summary

Piano practice data published via MQTT from `practice_session.py` is now flowing into Splunk
via the Ubuntu MQTT broker and Node-RED. This note documents the final working configuration.

---

## Architecture

```
practice_session.py / send_test_scale.py
  → MQTT publish (piano/notes, piano/sessions)
    → Ubuntu MQTT broker (198.18.133.101:1883)
      → Node-RED (198.18.133.101:1880)
        → HTTP POST to Splunk HEC (198.18.135.50:8088)
          → Splunk index: edge_hub_mqtt
```

The Splunk Edge Hub (100.127.43.4) was investigated but not used — its internal topic routing
between processed sensor data and the datastreamer clients was not functional in this lab
environment. The Ubuntu broker + Node-RED path is the primary data pipeline for all devices
in this demo lab.

---

## What was already in place

The LocalMQTT tab in Node-RED had a pre-existing flow:

```
LOCAL# (All topics) → DeDup → topic (switch) → merakimv / meraki/v1/mt / meraki/v1/mr / otherwise
```

The `topic` switch node routes messages based on `msg.topic` content. The three Meraki
branches each lead to further processing and ultimately to Splunk. The `otherwise` branch
was unconnected.

---

## Change made — adding piano to the topic switch

A fourth rule was added to the existing `topic` switch node in LocalMQTT:

| Rule | Condition | Value | Output |
|------|-----------|-------|--------|
| 1 | contains | `merakimv` | → 1 |
| 2 | contains | `meraki/v1/mt` | → 2 |
| 3 | contains | `meraki/v1/mr` | → 3 |
| **4** | **contains** | **`piano`** | **→ 4** |
| 5 | otherwise | | → 5 |

![Topic switch node with piano branch](nodered-topic-switch-piano.png)

---

## Piano MQTT tab — new flow

Output 4 from the topic switch feeds into a new flow built in the **Piano MQTT** tab:

```
[link in] → Format For HTTP (function) → HTTP To Splunk (http request) → debug http post (debug)
```

![Piano MQTT flow](nodered-piano-mqtt-flow.png)

### Format For HTTP — function node code

```javascript
msg.headers = {
    "Authorization": "Splunk <HEC_TOKEN>",
    "Content-Type": "application/json"
};
msg.payload = JSON.stringify({
    index: "edge_hub_mqtt",
    source: msg.topic,
    event: msg.payload
});
return msg;
```

### HTTP To Splunk — http request node config

| Field | Value |
|-------|-------|
| Method | POST |
| URL | `http://198.18.135.50:8088/services/collector/event` |
| Return | UTF-8 string |

No additional auth needed — the `Authorization` header is set in the function node.

---

## Splunk — verifying data

Search query used to confirm data is landing:

```spl
index=edge_hub_mqtt source="piano/notes"
| table _time, hand, name, finger, midi, velocity, scale, session_id
```

For session summaries:

```spl
index=edge_hub_mqtt source="piano/sessions"
| table _time, scale_display, segment_index, session_id
```

Result — 30 events for a single test scale run (15 RH + 15 LH notes), all fields present and
correctly parsed:

![Splunk search results showing piano/notes events](splunk-piano-notes-results.png)

Fields visible in Splunk per event: `finger`, `hand`, `midi`, `name`, `scale`, `session_id`,
`time_ms`, `timestamp_epoch`, `velocity`.

---

## HEC token reference

| Token name | Value | Default index | Allowed indexes |
|------------|-------|---------------|-----------------|
| Edge Hub Default | `<HEC_TOKEN>` | `edge_hub_data` | edge_hub_data, edge_hub_logs, edge_hub_modbus, edge_hub_mqtt, edge_hub_opcua |

The `edge_hub_mqtt` index is where all MQTT-sourced data lands (both Meraki and piano).

---

## What's next

With data in Splunk, the next steps are:

1. Write SPL queries for practice analysis (speed trends, evenness, per-finger breakdown)
2. Build Splunk dashboards for the demo
3. Build Claude MCP server for AI coaching analysis
4. Configure Cisco Workflows to trigger on session events
5. Output layer — Webex bot and/or web dashboard
6. Pre-record practice sessions for presentation demo data
