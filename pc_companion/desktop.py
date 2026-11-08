"""Native Windows window around the authenticated loopback UI, with no Python bridge."""
import json
import os
import threading
import time
from pathlib import Path


def run(server, sock, url, app, *, hidden=False):
    import webview
    import ctypes
    if os.name == 'nt':
        import pystray
        from PIL import Image
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Vexx.PC')
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.settings['ALLOW_DOWNLOADS'] = False
    window = webview.create_window('Vexx PC', url, width=1280, height=850,
        min_size=(390, 600), hidden=hidden, background_color='#0e1117', text_select=True)
    app.state.show_window = window.show
    app.state.pick_folder = lambda: window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(Path.home()))

    app.state.exiting=False

    def closed():
        server.should_exit = True
    window.events.closed += closed

    def on_closing(*_):
        if not app.state.exiting:
            window.hide()
            return False
    closing_event = getattr(window.events, 'closing', None)
    if closing_event is not None:
        window.events.closing += on_closing
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

    icon = None
    try:
        record = json.loads((Path(__file__).resolve().parents[1] / 'installation.json').read_text('utf-8'))
        candidate = Path(record['install_root']) / 'VexxPC.ico'
        if candidate.is_file():
            icon = str(candidate)
    except (OSError, ValueError, KeyError):
        pass
    tray = None
    show_on_start = False
    if os.name == 'nt':
        try:
            tray_image = Image.open(icon).convert('RGBA').resize((64, 64)) if icon else Image.new('RGBA', (64, 64), (35, 190, 150, 255))
        except (OSError, ValueError):
            tray_image = Image.new('RGBA', (64, 64), (35, 190, 150, 255))

        def quit_from_tray(_icon,_item):
            app.state.exiting = True
            server.should_exit = True

        tray = pystray.Icon('Vexx PC', tray_image, 'Vexx PC', pystray.Menu(
            pystray.MenuItem('Abrir Vexx PC', lambda _icon, _item: window.show(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Encerrar Vexx PC', quit_from_tray)))
        tray_ready = threading.Event()
        def start_tray(icon):
            icon.visible=True
            tray_ready.set()
        def run_tray():
            try:tray.run(setup=start_tray)
            except Exception:
                tray_ready.set()
        tray_thread = threading.Thread(target=run_tray, name='vexx-system-tray', daemon=True)
        tray_thread.start()
        show_on_start = hidden and not tray_ready.wait(4)
        if hidden and not tray.visible:
            show_on_start = True
    def after_gui_start():
        threading.Thread(target=watch_server, name='vexx-window-close', daemon=True).start()
        if show_on_start:window.show()
    try:
        webview.start(after_gui_start, gui='edgechromium', private_mode=True, icon=icon)
    finally:
        app.state.exiting=True
        server.should_exit = True
        if tray:
            try:
                tray.stop()
            except Exception:
                pass
        thread.join(timeout=10)
