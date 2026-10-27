"""Read-only process/path verification; run with the local psutil Python."""
import json,tempfile
from pathlib import Path
import psutil
P=Path(__file__).resolve().parents[1]/'qa-artifacts/v5910'
out={'production_operations':False,'sessions':{}}
for label in ('C','live'):
    runtime=json.loads((P/'raw'/label/'runtime.json').read_text())
    folder=Path(runtime['database']).resolve().parent
    assert folder.name.startswith('v5981-admin-qa-') and folder.is_relative_to(Path(tempfile.gettempdir()).resolve())
    matching=[]
    for process in psutil.process_iter(['pid','cmdline']):
        try:
            if any(str(folder) in arg for arg in (process.info['cmdline'] or [])):matching.append(process.pid)
        except (psutil.AccessDenied,psutil.NoSuchProcess):continue
    log=(P/('qa-start.log' if label=='C' else 'qa-live.log')).read_text(encoding='utf-8',errors='replace')
    out['sessions'][label]={'temporary_database_removed':not Path(runtime['database']).exists(),
      'temporary_runtime_removed':not Path(runtime['runtime']).exists(),'qa_processes_matching_private_folder':len(matching),
      'disposable_child_wait_timeout':'TimeoutExpired' in log,
      'limit':'C required disposal of its own QA launcher after tailer drain failure; no production agent was terminated.' if label=='C' else 'Real live QA drained without child wait timeout; not a repeat of failed model synthesis.'}
out['live_before_stop']={k:v for k,v in json.loads((P/'raw/runtime-before-stop.json').read_text()).items() if k in ('role','state','active_operations')}
(P/'qa-shutdown.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out))
assert all(v['temporary_database_removed'] and v['temporary_runtime_removed'] and not v['qa_processes_matching_private_folder'] for v in out['sessions'].values())
