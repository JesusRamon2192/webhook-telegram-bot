# Webhook Listener

Este proyecto implementa un servidor simple en Flask (`webhook.py`) diseñado para recibir webhooks (peticiones HTTP POST), guardarlos en archivos locales y enviar notificaciones a Telegram.

## Estructura y Docker

El proyecto está contenerizado usando **Docker**.

- **Dockerfile**: Define la imagen base (`python:3.11-slim`), instala las dependencias y prepara el entorno.
- **docker-compose.yml**: Orquesta el servicio. Define un volumen (`webhookPayloads`) que mapea una carpeta del host (`/home/pi/nextcloud-data/jesus/files/webhookPayloads`) al directorio `/app/received_webhooks` dentro del contenedor. Esto asegura que los archivos JSON recibidos persistan en el disco del servidor host incluso si el contenedor se reinicia.

## Funcionamiento del Código (`webhook.py`)

El script `webhook.py` levanta un servidor HTTP en el puerto 5000 y escucha peticiones POST en la ruta `/webhook`.

### Manejo de Archivos JSON

Cuando se recibe una petición POST con un cuerpo JSON, el código realiza lo siguiente:

1.  **Recepción y Validación**: Intenta parsear el cuerpo de la petición como JSON (`request.get_json()`). Si no es un JSON válido, devuelve un error.
2.  **Generación de Nombre**: Crea un nombre de archivo único basado en la fecha y hora actual UTC (ej. `2023-10-27_10-00-00-123456.json`).
3.  **Guardado (IMPORTANTE)**: Guarda el contenido del JSON en un archivo dentro del directorio `received_webhooks`.
    *   **¿Modifica el contenido?**: **NO.** El código **no filtra, parsea para extraer campos específicos, ni modifica** la estructura de los datos recibidos.
    *   **Formato**: Lo único que hace es **re-formatear** el JSON para que sea legible (pretty-print) con una indentación de 2 espacios (`json.dump(..., indent=2)`). Aparte de este cambio estético (espacios y saltos de línea), **la información y la estructura se mantienen idénticas** a lo que se envió en la petición original. Todo el contenido recibido se vuelca al archivo.
4.  **Notificación**: Lee las últimas líneas del JSON formateado y envía una notificación a Telegram al bot @webhook2192_bot junto con el archivo completo.
