# 1Password secret references — never contains real values.
# Usage: op run --env-file=.env.tpl -- python src/coach_agent.py
#
# Requires: op CLI signed in (op signin)
# All items are in the "Private" vault.

ANTHROPIC_API_KEY=op://Private/claude_api_key_vscode/credential
SPLUNK_TOKEN=op://Private/dcloud splunk api token/credential
SPLUNK_HEC_TOKEN=op://Private/splunk_hec_token/credential
WEBEX_BOT_TOKEN=op://Private/43s5ntukc25q7zonpo4wvtjnh4/credential
WEBEX_ROOM_ID=Y2lzY29zcGFyazovL3VzL1JPT00vODFhZjMzZDAtM2I4OC0xMWYxLWI0M2MtM2YzODEyYjMyMTcz

# Non-secret config — safe to hardcode here
SPLUNK_URL=https://198.18.135.50:8089
SPLUNK_HEC_URL=http://198.18.135.50:8088/services/collector/event
SPLUNK_INDEX=edge_hub_mqtt
PUBLISHER_TYPE=hec
AUTO_COACH=true
SUMMARY_MODE=false
MQTT_HOST=198.18.133.101
MQTT_PORT=1883
