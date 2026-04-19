# Architecture Pivot — April 19, 2026

## Summary

This note documents the design discussion that produced v2 of the implementation plan. We significantly simplified the architecture by removing Google Cloud Run as a middleware layer and clarified the natural role of Cisco Workflows.

---

## What We Started With (v1 Architecture)

The original plan (archived at `plan/implementation_plan_v1_archived_2026-04-18.md`) used:

- **Cloud Run** as the cloud middleware: received Splunk webhooks on `/trigger`, called Cisco Workflows, and served the `/coach` endpoint
- **Google Cloud** as the cloud hosting platform for the Flask app
- **Gemini** (referenced in the plan) to generate the Cloud Run infrastructure boilerplate
- **ngrok** was mentioned as a future option for exposing local Splunk to Cloud Run

The v1 plan ran into a hard blocker: Cloud Run cannot reach Splunk at its dCloud private IP (`198.18.135.50`). Cloud Run is on GCP's public network and has no route to dCloud lab IPs. The `/coach` endpoint would time out trying to query Splunk.

---

## Key Insight: The Workstation Is Not Going Away

The piano's USB MIDI output goes to the workstation. `practice_session.py` runs on the workstation. Until MIDI is liberated — via Bluetooth MIDI or a phone app that captures and transmits notes — the workstation is a critical, unavoidable component in the pipeline.

**Conclusion:** If the workstation must run anyway, there is no benefit to hosting `/coach` in the cloud. The coach agent uses MCP tools to query Splunk, and if Splunk is also local (dCloud), all of that is local-to-local. Moving `/coach` to Cloud Run just adds a network hop and a connectivity problem.

The right model: run everything on the workstation, expose only what needs to be internet-accessible via ngrok.

---

## Options We Considered

### ngrok vs. Cloudflare Tunnel
Both would expose the local Splunk endpoint to the internet. Cloudflare Tunnel was rejected — competitively awkward at a Cisco conference presentation. ngrok is the preferred choice (competitively neutral, well-known developer tool).

**Decision:** ngrok for any local services that need public exposure.

### How Cisco Workflows fits

Initially it felt like Workflows was being forced in — the pipeline worked end-to-end without it. The question was: what does Workflows actually add?

The natural fit emerged when we added the Webex bot feature:

- Webex bots receive messages via webhooks
- That webhook receiver needs a public cloud endpoint
- Workflows **is** a cloud webhook receiver by design
- Registering Workflows as the Webex bot's webhook handler is a genuine fit — not a workaround

This gives Workflows two natural roles:
1. Receive session-end POSTs from `practice_session.py` → call `/coach` → send Webex card
2. Receive Webex bot messages → route to `/coach` as freeform queries → send Webex card reply

Workflows becomes the cloud meeting point for inbound events. `/coach` on the workstation is the compute layer. This is the right separation.

### Cloud Run
Not deleted, just parked. If MIDI eventually moves off the workstation (Bluetooth / phone app), Cloud Run becomes the right home for `/coach` again and the ngrok tunnels go away. The code is already written.

### Direct trigger from `practice_session.py` vs. Splunk alert
The v1 plan used a Splunk alert to fire the coaching trigger. This is elegant but adds complexity: Splunk must be configured to send a webhook, the payload format must be parsed by Workflows, and it adds a dependency on Splunk's alerting engine.

Since `practice_session.py` already runs on the workstation and knows the `session_id` the moment a session ends, it can POST directly to the Workflows webhook. Simpler, more reliable, and easier to demo. Splunk still receives all the data for historical analysis — it just isn't the trigger.

---

## New Features Added

### Freeform Webex bot queries
Instead of rigid bot commands, the raw Webex message text is passed to `/coach` as a natural language query. Claude interprets the query and decides which MCP tools to call. This is a stronger demo moment than a command parser — it shows genuine agentic reasoning.

Example queries:
- "How am I doing with my A scale?"
- "What's going on with my thumb crossover when ascending?" *(technically: thumb tucks under after finger 3 when ascending — a known weak point in scale practice)*
- "Which scale has improved the most?"

### Chart/graph generation
Where appropriate, `/coach` can return a chart (speed trend, evenness curve, per-finger heatmap) alongside the coaching text. Included in the Adaptive Card as an image. This shows well in a recorded demo. Implementation approach TBD (local matplotlib PNG vs. GCS-hosted URL).

---

## What Still Needs to Be Decided

1. **Cloud Splunk** — the blocking dependency. Options: Splunk Cloud trial, Splunk Free on a GCP VM. Must decide before building anything else.
2. **ngrok tier** — free (URL changes on restart) vs. paid (fixed subdomain). Fixed subdomain required for a stable Workflows webhook URL. Decide when setting up ngrok.
3. **Chart delivery method** — local PNG attached via bot API, or a URL in the Adaptive Card.

---

## April 30 Deadline

A prototype must be working well enough to record by April 30 (draft presentation due). It does not need to be perfect, but the main components must be demonstrable on video. Live demos will not be used in the presentation — recorded scenarios only, which allows the presentation to focus on storytelling rather than live risk management.

Priority order for the remaining build:
1. Cloud Splunk instance
2. HEC publisher (bypass Node-RED)
3. ngrok + `/coach` local service with auth
4. Workflows session trigger flow
5. Webex bot + Workflows freeform query flow
6. Chart generation (if time allows)
7. Pre-record demo sessions

---

## What This Looks Like as a Presentation Story

> "I started with a full cloud architecture — Cloud Run, Google Cloud, the whole thing. Then I realized I was solving the wrong problem. The piano is on my desk. The workstation isn't going away. So I simplified: run the intelligence locally, use ngrok to expose just what needs to be internet-accessible, and use Cisco Workflows as the natural cloud entry point for both Splunk alerts and Webex bot interactions. Less infrastructure, cleaner story, same capabilities."

This pivot is itself a good talking point — it demonstrates thinking about fit-for-purpose architecture rather than defaulting to "put everything in the cloud."
