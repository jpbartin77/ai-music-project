# To do when connecting to a new dCloud session

## Route to Add when using the dCloud FP Workplace Lab

```powershell
route add 198.18.0.0 mask 255.255.0.0 100.127.43.1
```

Add `-p` to make persistent across reboots.

**Note:** The gateway IP (`100.127.43.1`) appears to be dynamic and may change between lab rotations. If connectivity to 198.18.x.x fails, verify the correct gateway by checking the AnyConnect adapter address or the dCloud lab details page.

**IMPORTANT NOTE**: The subnet changes with each new lab.  Not sure how to determine what subnet is assigned except to connect via DHCP and observe the address.  It always seems to match the pattern 100.127.0.1/24.  

## Update HEC Token in and API Cred in 1Password

### HEC Token

The token was intentionally redacted. To retrieve it from dCloud Splunk:

1. Open Splunk Web: http://198.18.135.50:8000 in your browser (while on dCloud)
2. Go to **Settings** → **Data Inputs** → **HTTP Event Collector**
3. Find the token named "Edge Hub Default" — click it to view or copy the token value
4. Add it to 1Password as a new item named splunk_hec_token with the token in the credential field

That's the 1Password item name I used as the placeholder in .env.tpl. Once it's there, op run will inject it as SPLUNK_HEC_TOKEN at runtime.

### API Key
To refresh:

1. In Splunk Web at `http://198.18.135.50:8000`, go to **Settings → Tokens** (under "USERS AND AUTHENTICATION")
2. Either find the existing API token and copy its value, or click **New Token** to generate one (audience: any descriptive string, no expiration if you want it to last the rotation)
3. Update the `dcloud splunk api token` entry in 1Password with the new token value