#!/bin/bash
# cloudshell_setup.sh — run this in GCP Cloud Shell to deploy piano-coach to Cloud Run.
#
# Steps performed:
#   1. Set project and enable required APIs
#   2. Create secrets in Google Secret Manager
#   3. Deploy to Cloud Run with secrets mounted
#   4. Print the service URL
#
# Usage:
#   git clone https://github.com/jpbartin77/ai-music-project.git
#   cd ai-music-project
#   bash cloudshell_setup.sh

set -e

PROJECT_ID="excellent-badge-484603-h7"
REGION="us-central1"
SERVICE_NAME="piano-coach"

# Non-secret config (matches .env.tpl)
SPLUNK_URL="https://198.18.135.50:8089"
SPLUNK_INDEX="edge_hub_mqtt"
WEBEX_ROOM_ID="Y2lzY29zcGFyazovL3VzL1JPT00vODFhZjMzZDAtM2I4OC0xMWYxLWI0M2MtM2YzODEyYjMyMTcz"

echo "=== Piano Coach — Cloud Run Deploy ==="
echo "Project : $PROJECT_ID"
echo "Region  : $REGION"
echo "Service : $SERVICE_NAME"
echo ""

# ── 1. Project + APIs ──────────────────────────────────────────────────────────
echo "[1/4] Setting project and enabling APIs..."
gcloud config set project "$PROJECT_ID"
gcloud services enable \
    run.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com

# ── 2. Secrets ─────────────────────────────────────────────────────────────────
echo ""
echo "[2/4] Creating secrets in Secret Manager..."
echo "      You will be prompted for each value. Paste from 1Password."
echo ""

create_or_update_secret() {
    local name=$1
    local prompt=$2
    echo -n "$prompt: "
    read -rs value
    echo ""
    if gcloud secrets describe "$name" --project="$PROJECT_ID" &>/dev/null; then
        echo "      '$name' exists — adding new version."
        echo -n "$value" | gcloud secrets versions add "$name" --data-file=-
    else
        echo "      Creating '$name'..."
        echo -n "$value" | gcloud secrets create "$name" \
            --data-file=- \
            --replication-policy=automatic
    fi
}

create_or_update_secret "ANTHROPIC_API_KEY" "Anthropic API key"
create_or_update_secret "SPLUNK_TOKEN"      "Splunk REST API token"
create_or_update_secret "WEBEX_BOT_TOKEN"   "Webex bot token"

# ── 3. Grant Cloud Run SA access to secrets ────────────────────────────────────
echo ""
echo "[3/4] Granting Cloud Run service account access to secrets..."

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in ANTHROPIC_API_KEY SPLUNK_TOKEN WEBEX_BOT_TOKEN; do
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:${SA}" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet
done

# ── 4. Deploy ──────────────────────────────────────────────────────────────────
echo ""
echo "[4/4] Deploying to Cloud Run (this builds from source — takes ~2 min)..."

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-secrets "ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,SPLUNK_TOKEN=SPLUNK_TOKEN:latest,WEBEX_BOT_TOKEN=WEBEX_BOT_TOKEN:latest" \
    --set-env-vars "SPLUNK_URL=${SPLUNK_URL},SPLUNK_INDEX=${SPLUNK_INDEX},WEBEX_ROOM_ID=${WEBEX_ROOM_ID}" \
    --timeout 300 \
    --memory 512Mi \
    --max-instances 3

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "=== Deploy complete ==="
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)")
echo "Service URL : $SERVICE_URL"
echo ""
echo "Test it:"
echo "  curl -s -X POST ${SERVICE_URL}/coach -H 'Content-Type: application/json' -d '{}' | jq ."
echo ""
echo "Webhook URL for Splunk alert:"
echo "  ${SERVICE_URL}/coach"
echo ""
echo "Save this URL — you'll need it when configuring the Splunk alert."
