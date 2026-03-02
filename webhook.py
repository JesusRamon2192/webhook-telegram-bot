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
USERS_FILE = BASE_DIR / "replied_users.json"

# --------------------------------------------------
# Variables de entorno
# --------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Opcional: ID inicial si el archivo está vacío
INITIAL_ADMIN_ID = os.getenv("TELEGRAM_CHAT_ID")
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Falta TELEGRAM_BOT_TOKEN")

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
    if not USERS_FILE.exists():
        with USERS_FILE.open("w") as f:
            json.dump({}, f)

def get_users_dict():
    """Devuelve el dict de usuarios: {'id': True/Metadata, ...}"""
    try:
        if not USERS_FILE.exists():
            return {}
        with USERS_FILE.open("r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_user(chat_id, first_name="Usuario"):
    users = get_users_dict()
    str_id = str(chat_id)
    
    # Si ya existe, no hacemos nada (o actualizamos metadata si quisieramos)
    if str_id in users:
        return False
    
    # Agregamos nuevo usuario
    users[str_id] = {"name": first_name, "date": datetime.now().isoformat()}
    with USERS_FILE.open("w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
    return True

def start_ngrok():
    public_url = ngrok.connect(PORT).public_url
    logger.info("Ngrok activo → %s/webhook", public_url)

    # Registrar Webhook en Telegram para recibir mensajes
    webhook_url = f"{public_url}/telegram_webhook"
    try:
        r = requests.post(
            f"{TELEGRAM_API_URL}/setWebhook",
            json={"url": webhook_url},
            timeout=10
        )
        r.raise_for_status()
        logger.info("Webhook de Telegram registrado: %s", webhook_url)
    except Exception as e:
        logger.error("Error registrando webhook de Telegram: %s", e)


def json_head(data, max_lines=30):
    text = json.dumps(data, indent=2, ensure_ascii=False)
    lines = text.splitlines()
    return "\n".join(lines[:max_lines])


def send_telegram_message(text, chat_id=None):
    """
    Si chat_id se especifica, envía solo a ese ID.
    Si no, envía a TODOS los usuarios en replied_users.json.
    """
    if chat_id:
        targets = [str(chat_id)]
    else:
        users = get_users_dict()
        targets = list(users.keys())
        # Fallback a env var si no hay nadie en el archivo
        if not targets and INITIAL_ADMIN_ID:
            targets = [INITIAL_ADMIN_ID]

    if not targets:
        logger.warning("No hay destinatarios para enviar el mensaje.")
        return

    for target_id in targets:
        payload = {
            "chat_id": target_id,
            "text": text[:4096]
        }
        try:
            r = requests.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json=payload,
                timeout=10
            )
            r.raise_for_status()
        except Exception as e:
            logger.error("Error enviando mensaje a %s: %s", target_id, e)


def send_telegram_file(file_path: Path, chat_id=None):
    if chat_id:
        targets = [str(chat_id)]
    else:
        users = get_users_dict()
        targets = list(users.keys())
        if not targets and INITIAL_ADMIN_ID:
            targets = [INITIAL_ADMIN_ID]

    if not targets:
        return

    try:
        file_content = file_path.read_bytes()
    except Exception as e:
        logger.error("No se pudo leer archivo: %s", e)
        return

    for target_id in targets:
        try:
            r = requests.post(
                f"{TELEGRAM_API_URL}/sendDocument",
                data={"chat_id": target_id},
                files={"document": (file_path.name, file_content)},
                timeout=20
            )
            r.raise_for_status()
        except Exception as e:
            logger.error("Error enviando archivo a %s: %s", target_id, e)

# --------------------------------------------------
# Webhook Listener & Telegram Command Handler
# --------------------------------------------------

@app.route("/telegram_webhook", methods=["POST"])
def telegram_listener():
    data = request.get_json(silent=True)
    if not data: 
        return "OK", 200

    # Log de debug
    logger.info("Telegram msg: %s", json.dumps(data))

    if "message" in data:
        msg = data["message"]
        chat_id = msg.get("chat", {}).get("id")
        user_first_name = msg.get("from", {}).get("first_name", "Usuario")
        
        if not chat_id:
            return "OK", 200

        # AUTO-SUBSCRIBE
        is_new = save_user(chat_id, user_first_name)
        
        if is_new:
            welcome_text = (
                f"👋 ¡Hola {user_first_name}!\n"
                "✅ Te he guardado en mi lista de destinatarios.\n"
                "Recibirás todos los webhooks que lleguen a partir de ahora."
            )
            send_telegram_message(welcome_text, chat_id)
        else:
            # Opcional: confirmar que sigue vivo sin spammear
            # send_telegram_message("🤖 Sigo aquí, y sigues suscrito.", chat_id)
            pass

    return "OK", 200

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

        head = json_head(data)
        message = (
            "Webhook recibido\n\n"
            f"UTC: {timestamp}\n"
            f"Archivo: {file_name}\n\n"
            "Primeras líneas:\n"
            f"{head}"
        )

        send_telegram_message(message)
        send_telegram_file(file_path)
        logger.info("Enviado a Telegram correctamente")

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
