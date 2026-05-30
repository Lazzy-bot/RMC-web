import requests
import os
from flask import Blueprint, jsonify, request

slack_bp = Blueprint("slack", __name__, url_prefix="/api")

# Map site key -> env variable name that stores Slack webhook URL
SLACK_WEBHOOK_ENV_KEYS = {
    "ABDNC": "SLACK_WEBHOOK_ABDNC",
    "AMDR": "SLACK_WEBHOOK_AMDR",
    "ANVL": "SLACK_WEBHOOK_ANVL",
    "ATQB": "SLACK_WEBHOOK_ATQB",
    "AVG": "SLACK_WEBHOOK_AVG",
    "DEFAULT": "SLACK_WEBHOOK_DEFAULT",
}


def _get_webhook(site_key: str) -> str:
    env_key = SLACK_WEBHOOK_ENV_KEYS.get(site_key, SLACK_WEBHOOK_ENV_KEYS["DEFAULT"])
    webhook = os.getenv(env_key) or os.getenv(SLACK_WEBHOOK_ENV_KEYS["DEFAULT"], "")
    return webhook.strip()


@slack_bp.post("/send-slack")
def send_slack():
    body    = request.json or {}
    text    = body.get("text", "").strip()
    site    = body.get("site", "").upper().strip()

    if not text:
        return jsonify({"error": "Khong co noi dung de gui"}), 400

    # Map ten day du -> site key neu can
    from config import SITE_KEY_MAP
    # Thu exact match truoc, roi uppercase, roi fallback DEFAULT
    site_key = (SITE_KEY_MAP.get(site)
                or SITE_KEY_MAP.get(site.upper())
                or site.upper())
    webhook = _get_webhook(site_key)
    print(f"[SLACK] site='{site}' -> key='{site_key}' -> {'MATCHED' if site_key in SLACK_WEBHOOK_ENV_KEYS else 'DEFAULT'}", flush=True)

    if not webhook:
        return jsonify({"error": "Slack webhook chua duoc cau hinh"}), 500

    try:
        r = requests.post(webhook, json={"text": text}, timeout=10)
        if r.status_code == 200:
            return jsonify({"ok": True})
        else:
            return jsonify({"error": f"Slack tra loi: {r.status_code} {r.text}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500