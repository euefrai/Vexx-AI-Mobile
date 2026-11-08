"""Bind an OS-selected loopback port; never adopt or terminate an existing process."""
import argparse
import socket
import webbrowser
import os
import secrets

import uvicorn
from .app import create_app
from . import __version__


def main():
    parser = argparse.ArgumentParser(description='Vexx PC local')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--start-hidden', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--data-dir')
    parser.add_argument('--root', action='append', help='Diretório para indexar (repetível)')
    args = parser.parse_args()
    app = create_app(args.data_dir, args.root)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(('127.0.0.1', args.port))
    sock.listen(128)
    port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}/'
    app.state.instance_id = secrets.token_hex(16)
    app.state.runtime = {'url':url, 'pid':os.getpid(), 'version':__version__, 'instance_id':app.state.instance_id}
    app.state.updater.no_browser = args.no_browser
    print('Vexx PC:', url, flush=True)
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False, use_colors=False))
    app.state.request_exit = lambda: setattr(server, 'should_exit', True)
    if not args.no_browser and os.name == 'nt':
        from .desktop import run
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        mutex = kernel.CreateMutexW(None, False, 'VexxPC.Desktop')
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        already_running = ctypes.get_last_error() == 183
        try:
            if not already_running:
                run(server, sock, url, app, hidden=args.start_hidden)
            elif not args.start_hidden:
                try:
                    import json, httpx
                    record = json.loads((app.state.directory / 'runtime.json').read_text('utf-8'))
                    with httpx.Client(base_url=record['url'], timeout=3, trust_env=False, follow_redirects=False) as client:
                        if client.get('/health').json().get('instance_id') == record.get('instance_id'):
                            client.get('/')
                            token = client.get('/api/bootstrap').json()['token']
                            client.post('/api/action', headers={'X-Vexx-Token': token}, json={'action': 'show_window'})
                except Exception:
                    pass
        finally:
            kernel.CloseHandle(mutex)
            sock.close()
    else:
        if not args.no_browser:
            import threading
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        server.run(sockets=[sock])


if __name__ == '__main__':
    main()
