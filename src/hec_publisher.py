"""
hec_publisher.py — Posts piano practice events directly to Splunk HEC.

Replaces the Node-RED → MQTT → HEC chain with a direct HTTP POST from the
workstation to Splunk, eliminating the lab setup dependency.

Configuration via environment variables:
  SPLUNK_HEC_URL    default: http://198.18.135.50:8088/services/collector/event
  SPLUNK_HEC_TOKEN  required — Splunk HEC token
  SPLUNK_INDEX      default: edge_hub_mqtt
"""

import json
import os
import time
import urllib.request
import urllib.error


DEFAULTS = {
    'hec_url':   'http://198.18.135.50:8088/services/collector/event',
    'index':     'edge_hub_mqtt',
    'topic_notes':    'piano/notes',
    'topic_sessions': 'piano/sessions',
}


class HECPublisher:
    """
    Direct Splunk HEC publisher. Same interface as MQTTPublisher so
    practice_session.py can swap between them via PUBLISHER_TYPE env var.
    Publish failures are logged but never crash the recording session.
    """

    def __init__(self):
        self.hec_url = os.environ.get('SPLUNK_HEC_URL', DEFAULTS['hec_url'])
        self.token   = os.environ.get('SPLUNK_HEC_TOKEN', '')
        self.index   = os.environ.get('SPLUNK_INDEX', DEFAULTS['index'])

        if not self.token:
            print("  [HEC] Warning: SPLUNK_HEC_TOKEN not set — events will not be published.")
        else:
            print(f"  [HEC] Publisher ready -> {self.hec_url} (index={self.index})")

    def publish_note(self, event, hand, scale_name, session_id):
        """Post a single note event to Splunk HEC (source=piano/notes)."""
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
        self._post(payload, DEFAULTS['topic_notes'])

    def publish_segment(self, doc, session_id):
        """Post a completed segment summary to Splunk HEC (source=piano/sessions)."""
        payload = {**doc, 'session_id': session_id, 'timestamp_epoch': int(time.time())}
        self._post(payload, DEFAULTS['topic_sessions'])

    def _post(self, payload, source):
        if not self.token:
            return
        body = json.dumps({
            'event': payload,
            'index': self.index,
            'source': source,
        }).encode('utf-8')
        req = urllib.request.Request(
            self.hec_url,
            data=body,
            headers={
                'Authorization': f'Splunk {self.token}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    print(f"  [HEC] Unexpected status {resp.status}")
        except urllib.error.URLError as e:
            print(f"  [HEC] Publish failed: {e.reason}")
        except Exception as e:
            print(f"  [HEC] Publish failed: {e}")

    def disconnect(self):
        pass  # no persistent connection to close
