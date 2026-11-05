"""Native Windows window around the authenticated loopback UI, with no Python bridge."""
import json
import threading
import time
from pathlib import Path


def run(server, sock, url, app, *, hidden=False):
    import webview
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Vexx.PC')
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.settings['ALLOW_DOWNLOADS'] = False
    window = webview.create_window('Vexx PC', url, width=1280, height=850,
        min_size=(390, 600), hidden=hidden, background_color='#0e1117', text_select=True)
    app.state.show_window = window.show
    app.state.pick_folder = lambda: window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(Path.home()))

    def closed():
        server.should_exit = True
    window.events.closed += closed
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), name='vexx-local-server', daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    if not server.started:
        raise RuntimeError('Não foi possível iniciar o Vexx PC.')

    def watch_server():
        thread.join()
        try:
            window.destroy()
        except Exception:
            pass

    def after_gui_start():
        threading.Thread(target=watch_server, name='vexx-window-close', daemon=True).start()
    icon = None
    try:
        record = json.loads((Path(__file__).resolve().parents[1] / 'installation.json').read_text('utf-8'))
        candidate = Path(record['install_root']) / 'VexxPC.ico'
        if candidate.is_file():
            icon = str(candidate)
    except (OSError, ValueError, KeyError):
        pass
    try:
        webview.start(after_gui_start, gui='edgechromium', private_mode=True, icon=icon)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
