# MQTT Setup — Splunk Edge Hub Connection

## Broker details
| Setting | Value |
|---------|-------|
| Host    | 100.127.43.4 (Splunk Edge Hub) |
| Port    | 1883 (standard MQTT, unencrypted) |
| Topics  | `piano/notes`, `piano/sessions` |

> **Note:** The Edge Hub is not currently reachable — home network needs
> reconfiguring before this will work. The session script will warn and
> continue recording/saving locally if MQTT is unavailable.

---

## Environment variables

The publisher reads four environment variables. Set them in your terminal
before running `practice_session.py`, or add them to a `.env` file.

| Variable   | Default       | Purpose |
|------------|---------------|---------|
| `MQTT_HOST`| `100.127.43.4`| Broker IP or hostname |
| `MQTT_PORT`| `1883`        | Broker port |
| `MQTT_USER`| *(empty)*     | Username (if broker requires auth) |
| `MQTT_PASS`| *(empty)*     | Password (if broker requires auth) |

### Windows — set for current session only
```cmd
set MQTT_HOST=100.127.43.4
set MQTT_PORT=1883
python src/practice_session.py
```

### Windows — set permanently (user level)
```cmd
setx MQTT_HOST 100.127.43.4
setx MQTT_PORT 1883
```
Then open a new terminal for the values to take effect.

### PowerShell
```powershell
$env:MQTT_HOST = "100.127.43.4"
$env:MQTT_PORT = "1883"
python src/practice_session.py
```

---

## Splunk Edge Hub — MQTT input configuration

Once the network is reachable, configure the Edge Hub to accept MQTT:

1. Open the Edge Hub admin UI
2. Add a new **MQTT** data input
3. Set the **topic filter** to `piano/#` (captures both `piano/notes` and `piano/sessions`)
4. Set **sourcetype** mapping:
   - Topic `piano/notes`    → sourcetype `piano:note`
   - Topic `piano/sessions` → sourcetype `piano:session`
5. Forward to your Splunk index (suggest: `piano_practice`)

---

## Testing the connection

Quick test from the terminal (requires `mosquitto_pub` installed):
```cmd
mosquitto_pub -h 100.127.43.4 -t piano/test -m "hello"
```

Or with Python:
```python
from src.mqtt_publisher import MQTTPublisher
pub = MQTTPublisher()
pub.publish_note(
    {'midi': 60, 'name': 'C4', 'velocity': 80, 'finger': 1, 'time_ms': 0.0},
    hand='right', scale_name='c_major', session_id='test'
)
pub.disconnect()
```
