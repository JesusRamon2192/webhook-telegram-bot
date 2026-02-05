"""
Módulo para capturar webhooks utilizando Flask y exponiéndolo vía NGROK.
Los payloads recibidos se guardan en archivos JSON locales.
"""
import os
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from pyngrok import ngrok, conf

# --- Configuración y Constantes ---
PORT = 5000
# Uso de pathlib para manejo moderno de rutas
BASE_DIR = Path(__file__).resolve().parent
WEBHOOKS_DIR = BASE_DIR / "received_webhooks"


token = os.getenv("NGROK_AUTHTOKEN")
if token:
    conf.get_default().auth_token = token

# Configuración del Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def setup_directories():
    """Crea el directorio de almacenamiento si no existe."""
    try:
        WEBHOOKS_DIR.mkdir(parents=True, exist_ok=True)
        # Lazy formatting (W1203) sin emojis
        logger.info("Directorio de webhooks verificado: %s", WEBHOOKS_DIR)
    except OSError as e:
        logger.error("Error critico creando directorio: %s", e)
        sys.exit(1)

def start_ngrok():
    """Inicia el túnel de ngrok y muestra la URL pública."""
    try:
        # Se conecta al puerto definido
        public_url = ngrok.connect(PORT).public_url
        logger.info("=" * 50)
        logger.info("Tunel ngrok iniciado correctamente.")
        # Concatenación segura dentro del logger sin emojis
        logger.info("URL Publica: %s/webhook", public_url)
        logger.info("=" * 50)
    except OSError as e:
        logger.error("Error al iniciar ngrok: %s", e)
        logger.warning("Consejo: Asegurate de tener tu authtoken configurado.")
        sys.exit(1)

@app.route('/webhook', methods=['POST'])
def webhook_listener():
    """
    Endpoint para recibir webhooks.
    Valida el JSON, genera un timestamp y guarda el archivo.
    """
    # 1. Obtención segura del JSON
    data = request.get_json(silent=True)

    if not data:
        logger.warning("Se recibio una peticion sin JSON valido o vacia.")
        return jsonify({"status": "error", "message": "Payload JSON invalido o faltante."}), 400

    # 2. Generación de nombre de archivo
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')
    file_name = f"{timestamp}.json"
    file_path = WEBHOOKS_DIR / file_name

    logger.info("Webhook recibido. Guardando en: %s", file_name)

    # 3. Guardado del archivo
    try:
        # Pathlib permite escribir texto directamente
        with file_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        logger.info("Guardado exitosamente.")
        return jsonify({"status": "success", "file_saved": str(file_name)}), 200

    except OSError as e:
        # Lazy formatting para la excepción
        logger.error("Error de E/S al guardar archivo: %s", e)
        return jsonify({"status": "error", "message": "Fallo interno al guardar datos."}), 500

# --- Bloque Principal ---
if __name__ == '__main__':
    # Inicializamos directorios y ngrok solo si se ejecuta el script directamente
    setup_directories()
    start_ngrok()

    # Desactivamos el reloader de Flask para evitar duplicidad de túneles
    app.run(port=PORT, use_reloader=False)

