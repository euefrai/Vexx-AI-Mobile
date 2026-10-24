"""Explicit, one-time migration of the reviewed existing human account snapshot."""
import json
import re
from datetime import datetime, timezone

import julia_auth as auth

KEY = 'migration_v5981_existing_human_admins'
NON_HUMAN = re.compile(r'(?:^|[._ -])(qa|test|teste|fixture|service|svc|bot|automation)(?:$|[._ -]|\d)',re.I)


def plan(db, cutoff=None):
    cutoff = cutoff or datetime.now(timezone.utc).isoformat()
    trusted={'local','registro','bootstrap-local','studio-local','aberto','convite'}
    trusted.update(r[0] for r in db.execute("SELECT uid FROM users WHERE role='admin' AND status='ativo' AND aprovado=1"))
    result=[]
    for uid,username,display,role,status,approved,password,created in db.execute(
            'SELECT uid,username,display,role,status,aprovado,hash,created_at FROM users'):
        origin = db.execute("SELECT ator FROM audit_log WHERE alvo=? AND acao IN "
                            "('usuario_criado','cadastro_aprovado','proprietario_vinculado')",(username,)).fetchall()
        reason = ('already_admin' if role=='admin' else
                  'inactive_or_unapproved' if status!='ativo' or not approved else
                  'future_account' if created>cutoff else
                  'fixture_or_service' if NON_HUMAN.search(username) or NON_HUMAN.search(display) else
                  'unverified_identity' if not password or not any(r[0] in trusted or r[0].startswith('convite:') for r in origin) else
                  'eligible')
        result.append({'uid':uid,'previous_role':role,'reason':reason})
    return {'migration':KEY,'cutoff':cutoff,'accounts':result,
            'promotions':sum(r['reason']=='eligible' for r in result)}


def apply(db, snapshot, actor='local'):
    if snapshot.get('migration') != KEY:
        raise ValueError('Manifesto de migração inválido')
    db.execute('BEGIN IMMEDIATE')
    try:
        previous=db.execute('SELECT v FROM app_config WHERE k=?',(KEY,)).fetchone()
        if previous:
            db.rollback()
            return {'already_applied':True,'promoted':0,'receipt':json.loads(previous[0])}
        operator=db.execute("SELECT role,status,aprovado FROM users WHERE uid=?",(actor,)).fetchone()
        if operator != ('admin','ativo',1):
            raise ValueError('Proprietário administrador ativo necessário')
        fresh=plan(db,snapshot['cutoff'])
        # Any new account or permission change since review requires a new plan.
        if fresh != snapshot:
            raise ValueError('Contas mudaram desde o dry-run; refaça a revisão')
        changed=[]
        for item in snapshot['accounts']:
            if item['reason']!='eligible':
                continue
            db.execute("UPDATE users SET role='admin' WHERE uid=? AND role='user'",(item['uid'],))
            db.execute('INSERT INTO audit_log(ts,ator,acao,alvo,detalhe) VALUES (?,?,?,?,?)',
                (auth.agora_iso(),actor,'admin_migration_promoted',item['uid'],'v5981; previous_role=user'))
            changed.append(item['uid'])
        receipt={'cutoff':snapshot['cutoff'],'changed':changed,'actor':actor,'created_at':auth.agora_iso()}
        db.execute('INSERT INTO app_config(k,v) VALUES (?,?)',(KEY,json.dumps(receipt)))
        db.commit()
        return {'already_applied':False,'promoted':len(changed),'receipt':receipt}
    except BaseException:
        db.rollback()
        raise


def reverse(db, actor='local'):
    """Revert only migration-owned changes; keep the receipt to exclude future users."""
    db.execute('BEGIN IMMEDIATE')
    try:
        operator=db.execute("SELECT role,status,aprovado FROM users WHERE uid=?",(actor,)).fetchone()
        if operator != ('admin','ativo',1):
            raise ValueError('Administrador ativo necessário')
        row=db.execute('SELECT v FROM app_config WHERE k=?',(KEY,)).fetchone()
        receipt=json.loads(row[0]) if row else {'changed':[]}
        changed=[]
        for uid in receipt['changed']:
            if uid==actor:
                raise ValueError('Não é permitido rebaixar o operador')
            later=db.execute("SELECT 1 FROM audit_log WHERE alvo=? AND ts>? AND acao IN "
                    "('papel_alterado','admin_migration_reverted')",(uid,receipt['created_at'])).fetchone()
            # Manual role updates use username as target too.
            username=db.execute('SELECT username FROM users WHERE uid=?',(uid,)).fetchone()
            if username and db.execute("SELECT 1 FROM audit_log WHERE alvo=? AND ts>? AND acao='papel_alterado'",
                                      (username[0],receipt['created_at'])).fetchone():
                later=True
            if later:
                continue
            others=db.execute("SELECT count(*) FROM users WHERE role='admin' AND status='ativo' AND aprovado=1 AND uid!=?",(uid,)).fetchone()[0]
            if not others:
                raise ValueError('Último administrador protegido')
            db.execute("UPDATE users SET role='user' WHERE uid=? AND role='admin'",(uid,))
            db.execute('INSERT INTO audit_log(ts,ator,acao,alvo,detalhe) VALUES (?,?,?,?,?)',
                    (auth.agora_iso(),actor,'admin_migration_reverted',uid,'v5981; role=user'))
            changed.append(uid)
        db.commit()
        return changed
    except BaseException:
        db.rollback()
        raise
