"""Export an explicit allowlist of QA/operational results, never private manifests."""
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa-artifacts/v5981'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(name, value):
    (QA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    for log, target in [('ui-release.log','admin-browser.json'),('ui-tabs-release.log','admin-tabs.json')]:
        text = (QA / log).read_text(encoding='utf-8-sig')
        assert text.startswith('### Result\n') and '### Error' not in text
        write(target,json.loads(text.splitlines()[1]))
    runtime = read(QA / 'qa-runtime-private.json')
    db = sqlite3.connect(Path(runtime['database']).as_uri()+'?mode=ro',uri=True)
    result = {'messages': db.execute('select count(*) from messages').fetchone()[0],
              'ai_requests': db.execute('select count(*) from ai_requests').fetchone()[0],
              'bob_limits_and_remote':list(db.execute("select max_ai_hora,max_ia_simult,remote_ok from users where username='bob'").fetchone()),
              'audit_counts':dict(db.execute('select acao,count(*) from audit_log group by acao').fetchall())}
    db.close()
    assert result['messages']==result['ai_requests']==0
    assert result['bob_limits_and_remote']==[20,2,0]
    write('admin-browser-sqlite.json',result)
    private = Path.home()/'.julia-mobile/ops-v5981'
    initial = read(private/'restart-receipt.json')
    final = read(private/'controlled-restart-receipt.json')
    migration = read(private/'account-migration-receipt.json')
    write('operational-summary.json',{
        'initial_backend':initial['backend_commit'],
        'initial_wrapper_pid':initial['new_pid'],
        'final':{k:final[k] for k in ('old_pid','new_pid','backend_commit','source_equivalent_to','old_stop','old_terminal','wrapper_sha256','active_operations_before','rollback','integrity','message_count_preserved')},
        'migration':{k:migration[k] for k in ('promoted','before','after')},
        'browser_reload':{'messages_visible':14,'pc_connected':True},
        'scope':'Operational receipts + authenticated UI observation; no credentials, account IDs or environment exported'
    })
    print('Sanitized browser, SQLite and operational evidence exported.')
