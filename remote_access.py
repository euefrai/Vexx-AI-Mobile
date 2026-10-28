"""Account-bound desktop consent. The browser can request, never approve access.

Only a local Windows dialog can grant access. Input is locked while that dialog
exists, including for legacy remote grants, so it cannot approve itself remotely.
Approvals are stored only in this agent's SQLite database, never in the relay.
"""
import importlib.util
from contextlib import closing
import secrets
import socket
import sqlite3
import sys
import threading
import time
from collections import deque

import julia_auth
import remoto

guard = threading.RLock()
_pending = None
_worker_open = False
_attempts = deque()
CONSENT_SECONDS = 120


def create_tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS remote_bindings (
        owner_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL
    )""")


def _active(db, owner):
    return owner == 'local' or (bool(julia_auth.buscar_uid(db, owner))
                                and julia_auth.status_efetivo(db, owner) == 'ativo')


def binding(db, owner):
    row = db.execute('SELECT enabled FROM remote_bindings WHERE owner_id=?', (owner,)).fetchone()
    return None if row is None else bool(row[0])


def allowed(db, owner):
    enabled = binding(db, owner)
    return (enabled and _active(db, owner) and julia_auth.pode_remoto(db, owner)) if enabled is not None else julia_auth.pode_remoto(db, owner)


def input_blocked():
    return _worker_open


def status(db, owner):
    with guard:
        permitted = allowed(db, owner)
        enabled = binding(db, owner) is True and permitted
        pending = (_pending is not None and _pending['owner'] == owner
                   and _pending['expires'] > time.monotonic())
        windows = sys.platform == 'win32'
        capture = importlib.util.find_spec('PIL') is not None
        return {'type': 'remote_status', 'device_name': socket.gethostname(),
                'platform': 'Windows' if windows else sys.platform,
                'supported': windows, 'capture_ready': windows and capture,
                'approved': enabled, 'view_allowed': bool(permitted),
                'control_allowed': bool(permitted and (enabled or remoto.entrada_ativada())),
                'pending': pending, 'confirmation_open': _worker_open,
                'code': _pending['code'] if pending else ''}


def confirm_locally(username, code):
    """Fail closed on unsupported/headless desktops or a dismissed dialog."""
    if sys.platform != 'win32':
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    user32.MessageBoxW.restype = ctypes.c_int
    text = (f'Conta: {username}\nComputador: {socket.gethostname()}\nCódigo: {code}\n\n'
            'Permitir que aparelhos conectados a esta conta vejam a tela inteira '
            'e controlem o mouse e o teclado deste computador?\n\n'
            'Confirme somente se você solicitou o acesso e o código confere. '
            'A autorização fica salva até ser revogada em Meu PC. '
            'Esta solicitação expira em 2 minutos.')
    # MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_SETFOREGROUND | MB_TOPMOST
    return user32.MessageBoxW(None, text, 'Vexx AI — Permitir acesso ao PC',
                             0x4 | 0x30 | 0x100 | 0x10000 | 0x40000) == 6


def _confirm_worker(path, request, username):
    global _pending, _worker_open
    approved = False
    try:
        approved = confirm_locally(username, request['code'])
        with guard:
            if not approved or _pending is not request or request['expires'] <= time.monotonic():
                return
            with closing(sqlite3.connect(path, timeout=5)) as db, db:
                if not _active(db, request['owner']):
                    return
                db.execute('INSERT INTO remote_bindings VALUES (?,1,?) '
                           'ON CONFLICT(owner_id) DO UPDATE SET enabled=1,updated_at=excluded.updated_at',
                           (request['owner'], time.time()))
                # Preserve the existing administrator revocation gate as well.
                db.execute('UPDATE users SET remote_ok=1 WHERE uid=?', (request['owner'],))
                julia_auth.auditar(db, request['owner'], 'remote_local_approved', socket.gethostname())
    except Exception:
        # Consent failure must never enable input or crash the agent loop.
        return
    finally:
        with guard:
            if _pending is request:
                _pending = None
            _worker_open = False


def request_access(db, owner):
    global _pending, _worker_open
    with guard:
        state = status(db, owner)
        if not state['supported'] or not state['capture_ready']:
            return {'type': 'remote_error', 'codigo': 'dependencia',
                    'error': 'O agente precisa estar no Windows com Pillow instalado.'}
        if not _active(db, owner):
            return {'type': 'remote_error', 'codigo': 'sem_permissao', 'error': 'Conta indisponível.'}
        if state['approved'] or state['pending']:
            return state
        if _worker_open:
            return {'type': 'remote_error', 'codigo': 'ocupado',
                    'error': 'Feche a confirmação anterior no computador antes de tentar novamente.'}
        now = time.monotonic()
        while _attempts and now - _attempts[0] >= 600:
            _attempts.popleft()
        if len(_attempts) >= 3:
            return {'type': 'remote_error', 'codigo': 'ritmo',
                    'error': 'Muitas solicitações. Aguarde alguns minutos.'}
        path = db.execute('PRAGMA database_list').fetchone()[2]
        if not path:
            return {'type': 'remote_error', 'codigo': 'banco', 'error': 'Banco local indisponível.'}
        user = julia_auth.buscar_uid(db, owner)
        username = (user or {}).get('username') or 'Proprietário local'
        request = {'owner': owner, 'code': f'{secrets.randbelow(1000000):06d}',
                   'expires': now + CONSENT_SECONDS}
        _pending = request
        _worker_open = True
        _attempts.append(now)
        try:
            threading.Thread(target=_confirm_worker, args=(path, request, username),
                             name='vexx-local-consent', daemon=True).start()
        except RuntimeError:
            _pending = None
            _worker_open = False
            return {'type': 'remote_error', 'codigo': 'ocupado', 'error': 'Não foi possível abrir a confirmação.'}
        return status(db, owner)


def revoke(db, owner):
    global _pending
    with guard:
        # Cancel even an open dialog: its later "Yes" cannot restore a grant.
        if _pending is not None and _pending['owner'] == owner:
            _pending = None
        db.execute('INSERT INTO remote_bindings VALUES (?,0,?) '
                   'ON CONFLICT(owner_id) DO UPDATE SET enabled=0,updated_at=excluded.updated_at',
                   (owner, time.time()))
        julia_auth.auditar(db, owner, 'remote_revoked', socket.gethostname())
        db.commit()
        return status(db, owner)
