import logging
import sys
import os
import asyncio
import base64
from aiohttp import web

# Aggiungi path corrente per import moduli
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.hls_proxy import HLSProxy
from services.ffmpeg_manager import FFmpegManager
from config import PORT, DVR_ENABLED, RECORDINGS_DIR, MAX_RECORDING_DURATION, RECORDINGS_RETENTION_DAYS

# Only import DVR components if enabled
if DVR_ENABLED:
    from services.recording_manager import RecordingManager
    from routes.recordings import setup_recording_routes

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

# --- Logica di Avvio ---
def create_app():
    """Crea e configura l'applicazione aiohttp."""

    ffmpeg_manager = FFmpegManager()
    proxy = HLSProxy(ffmpeg_manager=ffmpeg_manager)

    app = web.Application()
    app['ffmpeg_manager'] = ffmpeg_manager
    app.ffmpeg_manager = ffmpeg_manager

    # --- Middleware per autenticazione Basic via variabile d'ambiente ---
    PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")
    if not PROXY_PASSWORD:
        raise Exception("Devi impostare la variabile d'ambiente PROXY_PASSWORD!")

    @web.middleware
    async def auth_middleware(request, handler):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Basic "):
            return web.Response(
                status=401,
                headers={"WWW-Authenticate": 'Basic realm="Proxy"'},
                text="Autenticazione richiesta"
            )
        encoded = auth.split(" ")[1]
        try:
            decoded = base64.b64decode(encoded).decode()
        except Exception:
            return web.Response(status=400, text="Header Authorization non valido")
        if decoded != f"user:{PROXY_PASSWORD}":
            return web.Response(status=403, text="Password errata")
        return await handler(request)

    app.middlewares.append(auth_middleware)

    # --- Recording Manager se DVR abilitato ---
    if DVR_ENABLED:
        recording_manager = RecordingManager(
            recordings_dir=RECORDINGS_DIR,
            max_duration=MAX_RECORDING_DURATION,
            retention_days=RECORDINGS_RETENTION_DAYS
        )
        app['recording_manager'] = recording_manager

    # --- Registrazione route del proxy ---
    app.router.add_get('/', proxy.handle_root)
    app.router.add_get('/favicon.ico', proxy.handle_favicon)
    
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    if not os.path.exists(static_path):
        os.makedirs(static_path)
    app.router.add_static('/static', static_path)

    app.router.add_get('/builder', proxy.handle_builder)
    app.router.add_get('/info', proxy.handle_info_page)
    app.router.add_get('/api/info', proxy.handle_api_info)
    app.router.add_get('/key', proxy.handle_key_request)
    app.router.add_get('/proxy/manifest.m3u8', proxy.handle_proxy_request)
    app.router.add_get('/proxy/hls/manifest.m3u8', proxy.handle_proxy_request)
    app.router.add_get('/proxy/mpd/manifest.m3u8', proxy.handle_proxy_request)
    app.router.add_get('/proxy/stream', proxy.handle_proxy_request)
    app.router.add_get('/extractor', proxy.handle_extractor_request)
    app.router.add_get('/extractor/video', proxy.handle_extractor_request)
    app.router.add_get('/proxy/hls/segment.ts', proxy.handle_proxy_request)
    app.router.add_get('/proxy/hls/segment.m4s', proxy.handle_proxy_request)
    app.router.add_get('/proxy/hls/segment.mp4', proxy.handle_proxy_request)
    app.router.add_get('/playlist', proxy.handle_playlist_request)
    app.router.add_get('/segment/{segment}', proxy.handle_ts_segment)
    app.router.add_get('/decrypt/segment.mp4', proxy.handle_decrypt_segment)
    app.router.add_get('/decrypt/segment.ts', proxy.handle_decrypt_segment)
    app.router.add_get('/license', proxy.handle_license_request)
    app.router.add_post('/license', proxy.handle_license_request)
    app.router.add_post('/generate_urls', proxy.handle_generate_urls)
    app.router.add_get('/ffmpeg_stream/{stream_id}/{filename}', proxy.handle_proxy_request)
    app.router.add_get('/proxy/ip', proxy.handle_proxy_ip)

    # --- Setup DVR routes se abilitato ---
    if DVR_ENABLED:
        setup_recording_routes(app, recording_manager)

    # --- CORS generico ---
    app.router.add_route('OPTIONS', '/{tail:.*}', proxy.handle_options)

    # --- Cleanup / startup / shutdown ---
    async def cleanup_handler(app):
        await proxy.cleanup()
    app.on_cleanup.append(cleanup_handler)

    async def on_startup(app):
        asyncio.create_task(ffmpeg_manager.cleanup_loop())
        if DVR_ENABLED:
            asyncio.create_task(recording_manager.cleanup_loop())
    app.on_startup.append(on_startup)

    async def on_shutdown(app):
        if DVR_ENABLED:
            await recording_manager.shutdown()
    app.on_shutdown.append(on_shutdown)

    return app

# Crea l'istanza dell'app
app = create_app()

def main():
    if sys.platform == 'win32':
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)

    print("🚀 Starting HLS Proxy Server...")
    print(f"📡 Server available at: http://localhost:{PORT}")
    print(f"📡 Or: http://server-ip:{PORT}")
    print("🔗 Endpoints principali: /, /builder, /info, /proxy/manifest.m3u8, /playlist, ecc.")
    
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    main()
