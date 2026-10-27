"""Capture inner and outer real provider calls; raw public captures stay local."""
import json,pathlib,sys,time,threading,os,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['JULIA_ENV_FILE']=str(pathlib.Path(tempfile.gettempdir())/'v5910-none.env')
import search_providers as sp,query_intelligence as qi
import probe_source_quality_v5998 as probe
rows=[];lock=threading.Lock();original=sp.buscar
output=pathlib.Path(sys.argv[sys.argv.index('--output')+1])
version=sys.argv[sys.argv.index('--artifact-version')+1] if '--artifact-version' in sys.argv else 'v5910'
raw=ROOT/'qa-artifacts'/version/'raw';raw.mkdir(parents=True,exist_ok=True)
def observed(name,query,*args,**kwargs):
 row={'provider':name,'query':query,'candidates':[]};start=time.monotonic()
 try:
  result=original(name,query,*args,**kwargs)
  row['candidates']=[{k:r.get(k) for k in ['titulo','url','trecho','origem','tipo']} for r in result]
  return result
 except Exception as exc:row['error']=getattr(exc,'codigo',type(exc).__name__);raise
 finally:
  row['seconds']=round(time.monotonic()-start,3)
  with lock:rows.append(row)
sp.buscar=observed
try:probe.main()
finally:
 (raw/(output.stem+'-inner.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 print('inner_calls',len(rows))
