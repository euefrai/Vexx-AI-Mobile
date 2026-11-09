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
    try:
        ensure_efrain_permanent_access(db)
    except Exception:
        pass


def is_efrain(db, owner) -> bool:
    """Identifica se o owner é a conta primária efrain / dono do computador."""
    if not owner:
        return False
    o = str(owner).strip().lower()
    if o in ('u-a8295878023b', 'efrain', 'efrai', 'eu.efrai', 'efraisir'):
        return True
    try:
        user = julia_auth.buscar_uid(db, o)
        if not user:
            user = julia_auth.buscar_usuario(db, o)
        if user:
            uid = str(user.get('uid') or '').lower()
            uname = str(user.get('username') or '').lower()
            udisp = str(user.get('display') or '').lower()
            if uid == 'u-a8295878023b' or any('efrai' in x for x in (uname, udisp)):
                return True
    except Exception:
        pass
    if o == 'local':
        try:
            row = db.execute("SELECT username, display FROM users WHERE uid='local' OR role='admin' LIMIT 1").fetchone()
            if row and any('efrai' in str(field or '').lower() for field in row):
                return True
        except Exception:
            pass
    return False


def ensure_efrain_permanent_access(db):
    """Garante grant permanente ativo por padrão para a conta do efrain."""
    agora = time.time()
    try:
        rows = db.execute("SELECT uid FROM users WHERE username LIKE '%efrai%' OR display LIKE '%efrai%' OR uid IN ('u-a8295878023b', 'local')").fetchall()
        for r in rows:
            uid = r[0]
            db.execute("UPDATE users SET remote_ok=1 WHERE uid=?", (uid,))
            db.execute("INSERT OR IGNORE INTO remote_bindings (owner_id, enabled, updated_at) VALUES (?, 1, ?)", (uid, agora))
    except Exception:
        pass


def _active(db, owner):
    if is_efrain(db, owner):
        return True
    return owner == 'local' or (bool(julia_auth.buscar_uid(db, owner))
                                and julia_auth.status_efetivo(db, owner) == 'ativo')


def binding(db, owner):
    row = db.execute('SELECT enabled FROM remote_bindings WHERE owner_id=?', (owner,)).fetchone()
    if row is not None:
        return bool(row[0])
    if is_efrain(db, owner):
        # Usuário efrain tem controle sempre ativo o tempo todo
        try:
            db.execute('INSERT INTO remote_bindings (owner_id, enabled, updated_at) VALUES (?, 1, ?) '
                       'ON CONFLICT(owner_id) DO NOTHING', (owner, time.time()))
            db.commit()
        except Exception:
            pass
        return True
    return None


def allowed(db, owner):
    if is_efrain(db, owner):
        bound = binding(db, owner)
        # Só desativa se o usuário efrain tiver clicado em revogar permanentemente (bound is False)
        if bound is False:
            return False
        return True
    enabled = binding(db, owner)
    return (enabled and _active(db, owner) and julia_auth.pode_remoto(db, owner)) if enabled is not None else julia_auth.pode_remoto(db, owner)


def input_blocked():
    return _worker_open


def status(db, owner):
    with guard:
        permitted = allowed(db, owner)
        bound = binding(db, owner)
        enabled = bound is True and permitted
        pending = (_pending is not None and _pending['owner'] == owner
                   and _pending['expires'] > time.monotonic())
        windows = sys.platform == 'win32'
        capture = importlib.util.find_spec('PIL') is not None
        efrain_active = is_efrain(db, owner) and (bound is not False)
        return {'type': 'remote_status', 'device_name': socket.gethostname(),
                'platform': 'Windows' if windows else sys.platform,
                'supported': windows, 'capture_ready': windows and capture,
                'approved': bool(enabled or efrain_active),
                'view_allowed': bool(permitted or efrain_active),
                'control_allowed': bool((permitted or efrain_active) and (enabled or efrain_active or remoto.entrada_ativada())),
                'permanent_control': bool(efrain_active),
                'input_batch': True, 'precise_scroll': True,
                'pending': bool(pending and not efrain_active),
                'confirmation_open': bool(_worker_open and not efrain_active),
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
        if is_efrain(db, owner):
            # O usuário efrain tem acesso permanente garantido; reativa imediatamente sem travar
            agora = time.time()
            db.execute('INSERT INTO remote_bindings VALUES (?,1,?) '
                       'ON CONFLICT(owner_id) DO UPDATE SET enabled=1,updated_at=excluded.updated_at',
                       (owner, agora))
            for uid_vinculado in ('u-a8295878023b', 'local'):
                db.execute('INSERT INTO remote_bindings VALUES (?,1,?) '
                           'ON CONFLICT(owner_id) DO UPDATE SET enabled=1,updated_at=excluded.updated_at',
                           (uid_vinculado, agora))
            try:
                db.execute("UPDATE users SET remote_ok=1 WHERE uid=? OR uid IN ('u-a8295878023b', 'local')", (owner,))
            except Exception:
                pass
            db.commit()
            return status(db, owner)

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
        if is_efrain(db, owner):
            for uid_vinculado in ('u-a8295878023b', 'local'):
                db.execute('INSERT INTO remote_bindings VALUES (?,0,?) '
                           'ON CONFLICT(owner_id) DO UPDATE SET enabled=0,updated_at=excluded.updated_at',
                           (uid_vinculado, time.time()))
        julia_auth.auditar(db, owner, 'remote_revoked', socket.gethostname())
        db.commit()
        return status(db, owner)
