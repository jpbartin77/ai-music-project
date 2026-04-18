# Splunk Edge Hub — MQTT Config Notes (April 18, 2026)

## What this file is

`plan/edge_hub_mqtt_config.json` is the configuration we imported into the Splunk Edge Hub MQTT sensor to tell it how to interpret incoming MQTT messages from `practice_session.py`. This note explains what the JSON structure means and why each part is written the way it is.

---

## Top-level structure

```json
{
  "externalBrokerEnabled": true,
  "topicRules": [ ... ],
  "lastUpdated": "..."
}
```

- **`externalBrokerEnabled`** — tells Edge Hub to listen to an external MQTT broker rather than its built-in one. Our Python script connects to Edge Hub's broker at port 1883; Edge Hub acts as the broker itself, so this flag just enables that mode.
- **`topicRules`** — one entry per MQTT topic. We have two: `piano/notes` and `piano/sessions`.
- **`lastUpdated`** — set automatically by Edge Hub on export; ignored on import.

---

## Topic rule structure

Each entry in `topicRules` looks like this:

```json
{
  "topicName": "piano/notes",
  "sensorId": "a1b2c3d4-0001-0001-0001-piano0000001",
  "sensorType": "piano_note",
  "description": "...",
  "metricRules": [ ... ],
  "dimensionRules": [ ... ],
  "timestamp": { "seconds": "timestamp_epoch", "nanos": "0" }
}
```

| Field | Purpose |
|-------|---------|
| `topicName` | The MQTT topic to subscribe to. Must match exactly what the Python publisher sends. |
| `sensorId` | A UUID that uniquely identifies this sensor in Edge Hub. We generated these manually in a consistent format. |
| `sensorType` | A freeform string label for the sensor category. Appears in Edge Hub UI and Splunk metadata. |
| `description` | Human-readable label. |
| `metricRules` | Extracts **numeric** fields from the JSON payload — these become time-series data points in Splunk. |
| `dimensionRules` | Extracts **string** fields — these become indexed tags/dimensions you can filter by in Splunk. |
| `timestamp` | Tells Edge Hub which field to use as the event timestamp rather than arrival time. |

---

## Metrics vs. Dimensions

This distinction matters for how data lands in Splunk:

- **Metrics** are numeric values that can be aggregated, graphed, and alerted on (e.g. velocity, BPM, standard deviation). Each metric becomes its own data point with a value and a unit.
- **Dimensions** are string labels that act as filters (e.g. which hand, which scale, which session). They're attached to metric data points so you can slice the data (e.g. "show me right-hand BPM only").

---

## Metric rule structure

```json
{
  "metricId": "a1b2c3d4-0001-0002-0001-piano0000001",
  "metricName": "velocity",
  "unit": "count",
  "value": "velocity"
}
```

| Field | Purpose |
|-------|---------|
| `metricId` | Unique identifier for this metric within the sensor. |
| `metricName` | Name used in Splunk for this metric. |
| `unit` | Unit label (e.g. `count`, `ms`, `bpm`, `pct`). Informational — Edge Hub does not convert units. |
| `value` | A **JSONata expression** evaluated against the incoming MQTT payload to extract the value. |

### JSONata expressions used

JSONata is a query/transformation language for JSON. Edge Hub evaluates the `value` field as a JSONata expression against each incoming message payload.

| Expression | What it does |
|------------|-------------|
| `velocity` | Returns the top-level `velocity` field directly. |
| `midi` | Returns the top-level `midi` field. |
| `finger ? finger : -1` | Returns `finger` if it exists and is non-null, otherwise `-1`. This handles the case where a note event has no finger assignment yet (early in scale detection). |
| `time_ms` | Returns the top-level `time_ms` field. |
| `metrics.right.speed_bpm` | Navigates a nested path: `metrics` object → `right` object → `speed_bpm` field. |
| `metrics.right.evenness_stddev_ms` | Same pattern for evenness standard deviation. |
| `metrics.right.evenness_cv_pct` | Coefficient of variation (std dev / mean, as a percentage). |
| `$count(notes.right)` | Built-in JSONata function. Counts the number of elements in the `notes.right` array. |
| `$string(segment_index)` | Converts the integer `segment_index` to a string (required because it's used as a dimension, not a metric). |

---

## Dimension rule structure

```json
{
  "dimensionId": "a1b2c3d4-0001-0003-0001-piano0000001",
  "dimensionKey": "note",
  "dimensionValue": "name"
}
```

| Field | Purpose |
|-------|---------|
| `dimensionId` | Unique identifier for this dimension. |
| `dimensionKey` | The label this dimension will have in Splunk (e.g. the field name you'll filter on). |
| `dimensionValue` | JSONata expression evaluated against the payload — almost always just a field name. |

---

## Timestamp field

```json
"timestamp": {
  "seconds": "timestamp_epoch",
  "nanos": "0"
}
```

By default, Edge Hub uses the time the message arrived as the event timestamp. We override this with `timestamp_epoch` — a Unix timestamp (integer seconds) that we add to every MQTT payload in `mqtt_publisher.py`. This ensures Splunk records when the note/segment actually happened, not when it was received.

`nanos` is set to `"0"` (a literal string, not integer) — we don't have sub-second precision in the epoch field.

---

## Topic 1 — `piano/notes`

**Purpose:** Real-time per-keypress events. One message per NOTE_ON.

**Metrics captured:**

| Metric | Source field | Unit | Why |
|--------|-------------|------|-----|
| `velocity` | `velocity` | count | How hard the key was struck (0–127). Useful for dynamics analysis. |
| `midi_number` | `midi` | count | The MIDI pitch number. Lets you identify notes in numeric queries. |
| `finger` | `finger ? finger : -1` | count | Which finger played the note. `-1` means unassigned (shouldn't happen in valid segments). |
| `time_ms` | `time_ms` | ms | Time since session start in milliseconds. Useful for inter-onset interval analysis in Splunk. |

**Dimensions captured:** `note` (e.g. "C4"), `hand` ("left"/"right"), `scale` (e.g. "c_major"), `session_id`

---

## Topic 2 — `piano/sessions`

**Purpose:** Per-segment summary. One message per completed scale pass (after the 2-second silence gap closes a segment).

**Metrics captured:**

| Metric | Source | Unit | Why |
|--------|--------|------|-----|
| `right_speed_bpm` | `metrics.right.speed_bpm` | bpm | Right hand tempo — derived from mean inter-onset interval |
| `right_evenness_stddev_ms` | `metrics.right.evenness_stddev_ms` | ms | Timing consistency — lower is more even |
| `right_evenness_cv_pct` | `metrics.right.evenness_cv_pct` | pct | Coefficient of variation — normalised evenness (comparable across tempos) |
| `left_speed_bpm` | `metrics.left.speed_bpm` | bpm | Same for left hand |
| `left_evenness_stddev_ms` | `metrics.left.evenness_stddev_ms` | ms | Same for left hand |
| `left_evenness_cv_pct` | `metrics.left.evenness_cv_pct` | pct | Same for left hand |
| `note_count_right` | `$count(notes.right)` | count | Number of notes played by right hand (should be 15 for a full 2-octave scale) |
| `note_count_left` | `$count(notes.left)` | count | Same for left hand |

**Dimensions captured:** `scale`, `scale_display` (human-readable, e.g. "C Major"), `session_id`, `segment_index` (as string)

---

## ID naming convention

We generated UUIDs manually using a consistent pattern to make them readable at a glance:

```
a1b2c3d4 - TTTT - SSSS - DDDD - pianoNNNNNNN
```

- `TTTT` = topic number (`0001` = piano/notes, `0002` = piano/sessions)
- `SSSS` = rule type (`0001` = sensor, `0002` = metric, `0003` = dimension)
- `DDDD` = sequence within that type
- `pianoNNNNNNN` = sequence suffix

This is purely cosmetic — Edge Hub treats them as opaque UUIDs.

---

## Import/export notes

- The file is imported via the Edge Hub UI: **Sensors → MQTT → Import Config**.
- Edge Hub showed a generic "Error" dialog on import but the config was accepted. Verified by immediately exporting — the exported JSON matched our file exactly (only field ordering and `lastUpdated` changed; the em dash in `description` was encoded as `\u2014`).
- If you need to re-import: delete the existing MQTT sensor first, then import. Edge Hub does not merge or update in place.
- The working config is stored at `plan/edge_hub_mqtt_config.json`. The `plan/config.json` file is the Edge Hub export (equivalent, different ordering).
