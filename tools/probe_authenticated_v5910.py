"""Actual authenticated QA HTTP endpoint, never direct DB insertion."""
import argparse,http.cookiejar,json,time,urllib.request
from pathlib import Path
from urllib.parse import urlparse


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--qa',type=Path,required=True)
    p.add_argument('--query',required=True);p.add_argument('--label',required=True)
    args=p.parse_args();private=json.loads((args.qa/'qa-runtime-private.json').read_text())
    url=private['url']
    if urlparse(url).hostname!='127.0.0.1' or not Path(private['database']).parent.name.startswith('v5981-admin-qa-'):
        raise SystemExit('Disposable loopback QA required')
    output=args.qa/(args.label+'.json')
    if output.exists():raise SystemExit('Refusing duplicate real inference')
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf=''
    def api(path,data=None):
        req=urllib.request.Request(url+path,data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        with client.open(req,timeout=25) as r:return json.load(r)
    csrf=api('/api/login',{'username':'alice','password':'qa-password-long-5981'})['csrf']
    started=time.monotonic()
    job=api('/api/research/start',{'objetivo':args.query,'conv':args.label,'modo':'profunda'})
    final={};seen=set();events=[]
    while time.monotonic()-started<210:
        result=api('/api/research/status?job_id='+job['job_id'])
        final=result['resumo']
        for ev in result.get('eventos',[]):
            key=ev.get('seq')
            if key not in seen:seen.add(key);events.append(ev)
        if final.get('status') in ('concluida','falhou','cancelada','interrompida'):break
        time.sleep(1)
    out={'scope':'ACTUAL_AUTHENTICATED_QA_ENDPOINT','job':job,'summary':final,'events':events,
         'elapsed_s':round(time.monotonic()-started,3)}
    output.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'job':job,'status':final.get('status'),'elapsed_s':out['elapsed_s']}))

if __name__=='__main__':main()
