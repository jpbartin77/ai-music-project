# Set MQTT environment variables for the current PowerShell session only.
# Run with: . .\tools\set_mqtt_env.ps1  (note the leading dot — required to affect the current session)
#
# Broker: Ubuntu host in dCloud lab — the primary MQTT broker for this environment.
# Node-RED on this host forwards all MQTT traffic to Splunk HEC.
# Splunk Edge Hub (100.127.43.4) is an optional add-on and not required for data ingestion.

$env:MQTT_HOST = "198.18.133.101"
$env:MQTT_PORT = "1883"

Write-Host "MQTT environment variables set for this session:"
Write-Host "  MQTT_HOST = $env:MQTT_HOST  (Ubuntu broker — forwards to Splunk via Node-RED)"
Write-Host "  MQTT_PORT = $env:MQTT_PORT"
