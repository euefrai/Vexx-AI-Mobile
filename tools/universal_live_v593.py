"""Budgeted external probes, disposable SQLite, existing retrieval paths, no model."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from retrieval_recovery_v592 import run_case

CASES = [
 ('air','Pesquise voos de Salvador para São Paulo daqui a 30 dias, para um adulto.','research'),
 ('bus-feira','Pesquise passagens de ônibus de Salvador para Feira de Santana daqui a sete dias.','research'),
 ('bus-itabuna','Pesquise passagens de ônibus de Salvador para Itabuna daqui a sete dias.','research'),
 ('bus-return','Pesquise passagens de ônibus de Itabuna para Salvador daqui a sete dias.','research'),
 ('municipal','O que aconteceu em Ubatã, Bahia, nos últimos sete dias?','research'),
 ('capital','Últimas notícias de Salvador.','research'),
 ('regional','Quais acontecimentos importantes ocorreram em Feira de Santana recentemente?','research'),
 ('events','Quais eventos ocorrerão em Recife nas próximas duas semanas?','research'),
 ('currency','Quanto vale 100 dólares em reais agora?','currency'),
 ('science','Pesquise estudos científicos recentes sobre baterias de estado sólido.','research'),
 ('semiconductors','Pesquise estudos científicos sobre materiais semicondutores.','research'),
 ('transformer','Pesquise o artigo original da arquitetura Transformer com DOI e texto completo aberto.','research'),
 ('documentation','Compare a documentação oficial de FastAPI e Django.','research'),
 ('shopping','Pesquise uma geladeira frost free 400 litros até R$ 3500.','shopping'),
 ('tools','Pesquise uma furadeira Bosch 220 V até R$ 500.','shopping'),
 ('books','Pesquise o livro Dom Casmurro edição física até R$ 60.','shopping'),
]
BASELINE = {'air','bus-feira','municipal','capital','events','science'}


def main():
 p=argparse.ArgumentParser();p.add_argument('--case');p.add_argument('--baseline',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
 if args.case:
  import research, research_view, shopping, source_check
  collected=[];pdf_reads=[]
  normalize=research._fonte_de;download=source_check._baixar_bytes
  def observed_normalize(*a,**kw):
   s=normalize(*a,**kw);collected.append(s);return s
  def observed_pdf(url,*a,**kw):
   entry={'url':url};pdf_reads.append(entry);tick=time.monotonic()
   try:
    final,status,mime,body=download(url,*a,**kw);entry.update(final=final,status=status,mime=mime,bytes=len(body));return final,status,mime,body
   except Exception as exc:
    entry['error']=str(getattr(exc,'codigo',type(exc).__name__));raise
   finally:entry['ms']=round((time.monotonic()-tick)*1000,2)
  research._fonte_de=observed_normalize;source_check._baixar_bytes=observed_pdf
  r=run_case(next(c for c in CASES if c[0]==args.case));r['kind']='LIVE_RETRIEVAL';r['model_inference']=False
  r['source_contracts']=[{k:s.get(k) for k in ('url','titulo','relevante','status','content_scope','full_text_fetched','full_text_url','oa_attempt','vertical','publicado_em','doi','imagens')} for s in collected]
  r['pdf_reads']=pdf_reads
  r['contextual_jdui']=research_view.contextual_fence([s for s in collected if s.get('relevante')])
  r['product_states']=[{'url':p.get('url'),'state':shopping.precision_status(p),'pending':p.get('pendencias_do_pedido')} for p in r.get('products') or []]
  r['coverage']={'discovered':len(r.get('discovered') or []),'opened':r.get('opened_sources'),
                 'eligible':r.get('usable_sources'),
                 'page_read_eligible':sum(bool(s.get('relevante')) and s.get('status')=='aberta' and s.get('content_scope') not in ('abstract_only','metadata_only','feed_metadata') for s in collected),
                 'abstracts_retrieved':sum(s.get('content_scope')=='abstract_only' and bool(s.get('relevante')) for s in collected),
                 'discovered_unread_relevant':sum(s.get('status')!='aberta' and bool(s.get('relevante')) for s in collected)}
  print(json.dumps(r,ensure_ascii=False,default=str));return
 rows=[]
 for c in CASES:
  if args.baseline and c[0] not in BASELINE: continue
  start=time.monotonic()
  try:
   proc=subprocess.run([sys.executable,__file__,'--case',c[0]],capture_output=True,timeout=65,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
   row=json.loads(proc.stdout) if proc.returncode==0 else {'case':c[0],'query':c[1],'error':proc.stderr[-1600:]}
  except subprocess.TimeoutExpired: row={'case':c[0],'query':c[1],'error':'65s process ceiling'}
  row.setdefault('seconds',round(time.monotonic()-start,3));rows.append(row)
  if args.output:
   args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({k:row.get(k) for k in ('case','state','usable_sources','confirmed_offers','seconds','error')}),flush=True)


if __name__=='__main__':main()
