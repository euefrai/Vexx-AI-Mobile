"""Explicit owner-authorized account snapshot migration; never called at startup."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import admin_migration
from agent_runtime import private_directory


def run(pid,apply=False,owner_authorized=False):
    env=psutil.Process(pid).environ()
    path=Path(env['JULIA_SQLITE_PATH']).resolve()
    assert path==(Path.home()/'.julia-mobile/memory.sqlite3').resolve()
    private=private_directory(Path.home()/'.julia-mobile/ops-v5981')
    db=sqlite3.connect(path,timeout=5)
    assert db.execute('pragma quick_check').fetchone()[0]=='ok'
    # Legacy login aliases may differ; ownership is the stable local UID.
    owner=db.execute("select role,status,aprovado from users where uid='local'").fetchone()
    assert owner==('admin','ativo',1)
    collision=db.execute('select uid from users where username=?',(env['JULIA_USERNAME'].lower(),)).fetchone()
    assert not collision or collision[0]=='local','Legacy login alias collides with a different owner'
    snapshot=admin_migration.plan(db)
    (private/'account-dry-run.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
    if not apply:
        db.close();return {'dry_run':True,'planned_promotions':snapshot['promotions']}
    assert owner_authorized,'Explicit owner authorization is required'
    backup=private/f'pre-account-migration-{int(time.time())}.sqlite3'
    dest=sqlite3.connect(backup);db.backup(dest)
    assert dest.execute('pragma quick_check').fetchone()[0]=='ok';dest.close()
    protected='select uid,username,display,hash,status,aprovado,remote_ok,max_ai_hora,max_ia_simult from users order by uid'
    before=db.execute(protected).fetchall()
    sessions=db.execute('select * from user_sessions order by sid').fetchall()
    roles_before=dict(db.execute('select role,count(*) from users group by role'))
    result=admin_migration.apply(db,snapshot)
    assert db.execute(protected).fetchall()==before
    assert db.execute('select * from user_sessions order by sid').fetchall()==sessions
    assert db.execute('pragma quick_check').fetchone()[0]=='ok'
    assert admin_migration.apply(db,snapshot)['promoted']==0
    roles_after=dict(db.execute('select role,count(*) from users group by role'))
    receipt={'promoted':result['promoted'],'before':roles_before,'after':roles_after,'snapshot':snapshot,
             'result':result,'backup':str(backup),'integrity':'ok','protected_fields_and_sessions_unchanged':True,
             'idempotence_verified':True,'owner_authorization':'direct V5981 owner request; canonical local UID and no alias collision'}
    (private/'account-migration-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    db.close()
    return {k:receipt[k] for k in ('promoted','before','after','integrity','protected_fields_and_sessions_unchanged','idempotence_verified')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--apply',action='store_true');p.add_argument('--owner-authorized',action='store_true')
    a=p.parse_args();print(json.dumps(run(a.pid,a.apply,a.owner_authorized)))
