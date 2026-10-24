"""PC-side admin contracts. Aggregate diagnostics contain no conversation text."""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import julia_auth as auth

TYPES = {'admin_identity', 'admin_verify_password', 'admin_console_overview', 'admin_console_audit'}


def identity(db, owner, sid, require_session=False):
    user = auth.buscar_uid(db, owner)
    row = db.execute('SELECT aprovado FROM users WHERE uid=?', (owner,)).fetchone()
    if not user or user['role'] != 'admin' or user['status'] != 'ativo' or not row or not row[0]:
        raise auth.AuthErro('Permissão de administrador necessária', 'permissao')
    known_session = db.execute('SELECT 1 FROM user_sessions WHERE sid=?',(sid,)).fetchone() if sid else None
    if owner != 'local' or known_session or require_session:
        session = auth.sessao_valida(db, sid)
        if not session or session['uid'] != owner:
            raise auth.AuthErro('Sessão inválida', 'permissao')
    revision = db.execute("SELECT COALESCE(MAX(id),0) FROM audit_log WHERE "
            "(alvo IN (?,?) AND acao IN ('papel_alterado','bloqueado','desbloqueado',"
            "'sessoes_revogadas','admin_migration_promoted','admin_migration_reverted')) "
            "OR (ator=? AND acao='senha_trocada')", (owner,user['username'],owner)).fetchone()[0]
    return {'uid':owner, 'role':'admin', 'status':'ativo', 'approved':True, 'revision':revision}


def handle(db, request, agent=None):
    owner = request.get('owner','')
    kind = request.get('type')
    user = identity(db, owner, request.get('sid',''), request.get('require_session',False))
    if kind == 'admin_identity':
        return {'type':'admin_identity','identity':user}
    if kind == 'admin_verify_password':
        # The legacy Argon2 credential is checked only by the relay.
        if owner == 'local':
            ok = request.get('legacy_verified') is True
        else:
            username = auth.buscar_uid(db, owner)['username']
            try:
                verified = auth.login_conta(db, username, request.get('password',''), request.get('cliente',''))
                ok = verified['uid'] == owner
            except auth.AuthErro:
                auth.auditar(db,owner,'admin_reauth_failed')
                raise
        auth.auditar(db,owner,'admin_reauth_ok' if ok else 'admin_reauth_failed')
        if not ok:
            raise auth.AuthErro('Credenciais inválidas','credenciais')
        if owner == 'local':
            sid=request.get('sid','')
            if not isinstance(sid,str) or not 8 <= len(sid) <= 128:
                raise auth.AuthErro('Sessão inválida','permissao')
            with db:
                db.execute('INSERT OR IGNORE INTO user_sessions(sid,uid,created_at,expira_em) VALUES (?,?,?,?)',
                    (sid,owner,auth.agora_iso(),(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()))
        return {'type':'admin_verified','identity':identity(db,owner,request.get('sid',''))}
    if kind == 'admin_console_audit':
        rows=db.execute('SELECT ts,ator,acao,alvo FROM audit_log ORDER BY id DESC LIMIT 100').fetchall()
        return {'type':kind,'events':[dict(zip(('ts','actor','action','target'),r)) for r in rows]}
    if kind != 'admin_console_overview':
        raise auth.AuthErro('Operação não permitida','permissao')
    counts=db.execute("SELECT count(*),sum(role='admin'),sum(status='ativo' AND aprovado=1) FROM users").fetchone()
    jobs=dict(db.execute('SELECT status,count(*) FROM research_jobs GROUP BY status').fetchall())
    outcomes=dict(db.execute("SELECT COALESCE(json_extract(usados,'$.research_outcome.state'),'unknown'),count(*) "
                             'FROM research_jobs WHERE json_valid(usados) GROUP BY 1').fetchall())
    # Select JSON flags only: no objective, message, excerpt, URL, or owner data.
    total,read=db.execute("SELECT count(*),sum(CASE WHEN json_valid(original) THEN "
              "json_extract(original,'$.texto_lido')=1 ELSE 0 END) FROM evidence").fetchone()
    runtime=getattr(agent,'VEXX_RUNTIME',None)
    process={'pid':os.getpid(),'role':runtime.role if runtime else None,
             'state':runtime.state if runtime else 'unmanaged',
             'uptime_s':round(time.time()-runtime.started) if runtime else None,
             'cpu_percent':None,'ram_mb':None,'connected':True}
    try:
        import psutil
        proc=psutil.Process();process['ram_mb']=round(proc.memory_info().rss/1048576,1)
        # Avoid presenting a first unsampled cpu_percent() value as a real 0.
        process['cpu_time_s']=round(sum(proc.cpu_times()[:2]),2)
    except ImportError:
        pass
    try:
        import search_providers
        providers={name:{k:data.get(k) for k in ('chamadas','ok','vazio','erros')}
                   for name,data in search_providers.metricas().items()}
    except (ImportError,AttributeError):
        providers={}
    model=agent.ai_config().get('model') if agent else None
    return {'type':kind,'accounts':dict(zip(('total','admins','active'),[n or 0 for n in counts])),
            'agent':process,'backend':getattr(agent,'VEXX_BACKEND_REVISION',None),
            'relay':urlsplit(os.getenv('JULIA_RELAY_URL','')).hostname,
            'research':{'statuses':jobs,'outcomes':outcomes,'sources':total,'read_sources':read or 0,
                        'read_rate':round((read or 0)/total,4) if total else None},
            'providers':providers,'model':{'configured':model,'inference':'not_checked','availability':None}}
