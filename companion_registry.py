"""Device credentials live in the existing auth SQLite, never in public bundles."""
import hashlib
import re
import time
import secrets
import sqlite3

import julia_auth


def handle(db, req):
    db.execute('''CREATE TABLE IF NOT EXISTS companion_devices (
        owner TEXT PRIMARY KEY, device_id TEXT NOT NULL, token_hash TEXT NOT NULL,
        name TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS companion_identities (
        owner TEXT PRIMARY KEY, nick TEXT NOT NULL UNIQUE, pin_hash TEXT NOT NULL,
        generation TEXT NOT NULL, failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0)''')
    action = req.get('action')
    if action == 'authenticate_identity':
        nick = str(req.get('nick', '')).strip().lower()
        row = db.execute('SELECT owner,pin_hash,generation,failures,locked_until FROM companion_identities WHERE nick=?', (nick,)).fetchone()
        dummy = 'scrypt$16384$8$1$' + '00'*16 + '$' + '00'*32
        valid = julia_auth.confere_senha(str(req.get('pin', '')), row[1] if row else dummy)
        if not row or row[4] > time.time():
            return {'type':'companion_registry', 'denied':True}
        if not valid:
            failures = row[3]+1
            with db:
                db.execute('UPDATE companion_identities SET failures=?,locked_until=? WHERE owner=?',
                           (failures, time.time()+900 if failures >= 5 else 0, row[0]))
            return {'type':'companion_registry', 'denied':True}
        user = julia_auth.buscar_uid(db, row[0])
        if not user or julia_auth.status_efetivo(db, row[0]) != 'ativo':
            return {'type':'companion_registry', 'denied':True}
        with db:
            db.execute('UPDATE companion_identities SET failures=0,locked_until=0 WHERE owner=?', (row[0],))
        return {'type':'companion_registry', 'owner':row[0], 'generation':row[2]}
    owner = str(req.get('owner', ''))
    user = julia_auth.buscar_uid(db, owner)
    if owner != 'local' and (not user or julia_auth.status_efetivo(db, owner) != 'ativo'):
        return {'type': 'companion_registry', 'error': 'Conta indisponível', 'allowed': False}
    if action == 'identity_get':
        row = db.execute('SELECT nick FROM companion_identities WHERE owner=?', (owner,)).fetchone()
        return {'type':'companion_registry', 'configured':bool(row), 'nick':row[0] if row else ''}
    if action in ('identity_set', 'identity_delete'):
        if action == 'identity_set':
            nick, pin = str(req.get('nick', '')).strip().lower(), str(req.get('pin', ''))
            if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{2,29}', nick) or not re.fullmatch(r'[0-9]{6,12}', pin):
                return {'type':'companion_registry', 'invalid':True}
            digest = julia_auth.hash_senha(pin)
        try:
            with db:
                if action == 'identity_delete':
                    db.execute('DELETE FROM companion_identities WHERE owner=?', (owner,))
                else:
                    db.execute('INSERT INTO companion_identities VALUES (?,?,?,?,0,0) ON CONFLICT(owner) DO UPDATE SET nick=excluded.nick,pin_hash=excluded.pin_hash,generation=excluded.generation,failures=0,locked_until=0',
                               (owner, nick, digest, secrets.token_hex(16)))
                db.execute('UPDATE companion_devices SET revoked=1 WHERE owner=?', (owner,))
        except sqlite3.IntegrityError:
            return {'type':'companion_registry', 'conflict':True}
        return {'type':'companion_registry', 'ok':True}
    if action == 'enroll':
        device, digest = req.get('device_id', ''), req.get('token_hash', '')
        if not re.fullmatch(r'[a-f0-9]{32}', device) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            return {'type': 'companion_registry', 'error': 'Credencial inválida'}
        with db:
            if 'generation' in req:
                identity = db.execute('SELECT generation FROM companion_identities WHERE owner=?', (owner,)).fetchone()
                if not identity or identity[0] != req['generation']:
                    return {'type':'companion_registry', 'denied':True}
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
