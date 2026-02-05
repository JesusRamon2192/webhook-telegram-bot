import os
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, request, jsonify
from pyngrok import ngrok, conf

# --------------------------------------------------
# Configuración base
# --------------------------------------------------

PORT = 5000
BASE_DIR = Path(__file__).resolve().parent
WEBHOOKS_DIR = BASE_DIR / "received_webhooks"

# --------------------------------------------------
# Variables de entorno
# --------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

if NGROK_AUTHTOKEN:
    conf.get_default().auth_token = NGROK_AUTHTOKEN

# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --------------------------------------------------
# Flask
# --------------------------------------------------

app = Flask(__name__)

# --------------------------------------------------
# Utilidades
# --------------------------------------------------

def setup_directories():
    WEBHOOKS_DIR.mkdir(parents=True, exist_ok=True)


def start_ngrok():
    public_url = ngrok.connect(PORT).public_url
    logger.info("Ngrok activo → %s/webhook", public_url)


def json_tail(data, max_lines=30):
    text = json.dumps(data, indent=2, ensure_ascii=False)
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def send_telegram_message(text):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[:4096]
    }
    r = requests.post(
        f"{TELEGRAM_API_URL}/sendMessage",
        json=payload,
        timeout=10
    )
    r.raise_for_status()


def send_telegram_file(file_path: Path):
    with file_path.open("rb") as f:
        r = requests.post(
            f"{TELEGRAM_API_URL}/sendDocument",
            data={"chat_id": TELEGRAM_CHAT_ID},
            files={"document": f},
            timeout=20
        )
        r.raise_for_status()

# --------------------------------------------------
# Webhook
# --------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook_listener():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"status": "error", "message": "JSON inválido"}), 400

    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S-%f")
    file_name = f"{timestamp}.json"
    file_path = WEBHOOKS_DIR / file_name

    try:
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Webhook guardado: %s", file_name)

        tail = json_tail(data)

        message = (
            "Webhook recibido\n\n"
            f"UTC: {timestamp}\n"
            f"Archivo: {file_name}\n\n"
            "Últimas líneas:\n"
            f"{tail}"
        )

        try:
            send_telegram_message(message)
            send_telegram_file(file_path)
            logger.info("Enviado a Telegram correctamente")
        except Exception as tg_err:
            logger.error("Error enviando a Telegram: %s", tg_err)

        return jsonify({
            "status": "success",
            "file_saved": file_name
        }), 200

    except Exception as e:
        logger.exception("Error procesando webhook")
        return jsonify({"status": "error", "message": str(e)}), 500

# --------------------------------------------------
# Main
# --------------------------------------------------

if __name__ == "__main__":
    setup_directories()
    start_ngrok()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
