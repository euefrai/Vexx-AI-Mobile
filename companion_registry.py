"""Device credentials live in the existing auth SQLite, never in public bundles."""
import hashlib
import re
import time

import julia_auth


def handle(db, req):
    db.execute('''CREATE TABLE IF NOT EXISTS companion_devices (
        owner TEXT PRIMARY KEY, device_id TEXT NOT NULL, token_hash TEXT NOT NULL,
        name TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)''')
    owner = str(req.get('owner', ''))
    user = julia_auth.buscar_uid(db, owner)
    if owner != 'local' and (not user or julia_auth.status_efetivo(db, owner) != 'ativo'):
        return {'type': 'companion_registry', 'error': 'Conta indisponível', 'allowed': False}
    action = req.get('action')
    if action == 'enroll':
        device, digest = req.get('device_id', ''), req.get('token_hash', '')
        if not re.fullmatch(r'[a-f0-9]{32}', device) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            return {'type': 'companion_registry', 'error': 'Credencial inválida'}
        with db:
            db.execute('INSERT OR REPLACE INTO companion_devices VALUES (?,?,?,?,0,?)',
                       (owner, device, digest, str(req.get('name', 'PC'))[:80], time.time()))
    elif action == 'revoke':
        with db:
            db.execute('UPDATE companion_devices SET revoked=1 WHERE owner=?', (owner,))
    row = db.execute('SELECT device_id,token_hash,name,revoked FROM companion_devices WHERE owner=?', (owner,)).fetchone()
    result = {'type': 'companion_registry', 'linked': bool(row), 'active': bool(row and not row[3])}
    if row:
        result.update(device_id=row[0], name=row[2])
    if action == 'validate':
        import hmac
        result['allowed'] = bool(row and not row[3] and row[0] == req.get('device_id') and
                                 hmac.compare_digest(row[1], hashlib.sha256(str(req.get('token', '')).encode()).hexdigest()))
    return result
