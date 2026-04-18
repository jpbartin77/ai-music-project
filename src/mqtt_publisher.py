"""
mqtt_publisher.py — Publishes piano practice data to an MQTT broker.

Two topic streams:
  piano/notes    — one message per NOTE_ON (real-time)
  piano/sessions — one message per completed segment (summary + metrics)

Configuration via environment variables (see notes/mqtt_setup.md):
  MQTT_HOST   default: 100.127.43.4
  MQTT_PORT   default: 1883
  MQTT_USER   default: (none)
  MQTT_PASS   default: (none)
"""

import json
import os
import time
import paho.mqtt.client as mqtt


DEFAULTS = {
    'host': '100.127.43.4',
    'port': 1883,
    'topic_notes':    'piano/notes',
    'topic_sessions': 'piano/sessions',
}


class MQTTPublisher:
    """
    Thin wrapper around paho-mqtt. Publish failures are logged but never
    crash the recording session.
    """

    def __init__(self):
        self.host  = os.environ.get('MQTT_HOST', DEFAULTS['host'])
        self.port  = int(os.environ.get('MQTT_PORT', DEFAULTS['port']))
        self.user  = os.environ.get('MQTT_USER', '')
        self.pw    = os.environ.get('MQTT_PASS', '')
        self.connected = False

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if self.user:
            self._client.username_pw_set(self.user, self.pw)

        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect(self.host, self.port, keepalive=60)
            self._client.loop_start()
        except Exception as e:
            print(f"  [MQTT] Could not connect to {self.host}:{self.port} — {e}")
            print(f"  [MQTT] Session will continue; data will not be published.")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.connected = True
            print(f"  [MQTT] Connected to {self.host}:{self.port}")
        else:
            print(f"  [MQTT] Connection refused — reason code {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False

    def publish_note(self, event, hand, scale_name, session_id):
        """Publish a single note event to piano/notes."""
        if not self.connected:
            return
        payload = {
            'session_id':      session_id,
            'scale':           scale_name,
            'hand':            hand,
            'midi':            event['midi'],
            'name':            event['name'],
            'velocity':        event['velocity'],
            'finger':          event.get('finger'),
            'time_ms':         event['time_ms'],
            'timestamp_epoch': int(time.time()),
        }
        self._publish(DEFAULTS['topic_notes'], payload)

    def publish_segment(self, doc, session_id):
        """Publish a completed segment summary to piano/sessions."""
        if not self.connected:
            return
        payload = {**doc, 'session_id': session_id, 'timestamp_epoch': int(time.time())}
        self._publish(DEFAULTS['topic_sessions'], payload)

    def _publish(self, topic, payload):
        try:
            self._client.publish(topic, json.dumps(payload), qos=1)
        except Exception as e:
            print(f"  [MQTT] Publish failed: {e}")

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
