"""Controlled before/after pipeline experiment, isolated SQLite, no network/model.

The same readers/documents run against --root V597 or V598. This is FIXTURE,
never evidence of external retrieval success or scientific correctness.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import time


def run(root):
    sys.path.insert(0, str(root))
    import pc_agent
    import research_agents as ra
    question='Compare estudos de baterias de estado sólido: métodos, resultados e limitações'
    calls=[];reads=[];snapshots=[]
    class Provider:
        nome='controlled-documents'
        def buscar(self, query, limite=6):
            calls.append(query)
            targeted=any(term in query for term in ('methods sample','experimental conditions','limitations study'))
            kind='method' if targeted else 'result'
            return [{'titulo':'Estudo de baterias de estado sólido '+kind+' '+str(i),
                     'doi':f'10.1234/{kind}-{i}',
                     'url':f'https://fixture.example/{kind}-{i}',
                     'trecho':'Baterias de estado sólido, métodos, resultados e limitações.'} for i in (1,2)]
    def recover(url):
        reads.append(url)
        study=int(url[-1])
        sections=[{'titulo':'Results','texto':f'Baterias de estado sólido, estudo {study}: measured capacity was {100+study} mAh/g.'}]
        if '/method-' in url:
            sections += [{'titulo':'Methods','texto':f'Baterias de estado sólido, estudo {study}: {50+study} cells were tested at {25+study} C.'},
                         {'titulo':'Limitations','texto':f'Baterias de estado sólido, estudo {study}: observations are limited to laboratory cells.'}]
        return {'titulo':'Estudo de baterias de estado sólido','final':url,
                'texto':'Baterias de estado sólido métodos resultados limitações. DOI 10.1234/'+url.rsplit('/',1)[-1]+' '+
                        ' '.join(s['texto'] for s in sections),
                'content_scope':'document_text','texto_lido':True,'secoes':sections}
    with tempfile.TemporaryDirectory(prefix='v598-autonomy-fixture-') as temp:
        db=pc_agent.open_db(Path(temp)/'research.sqlite')
        job=ra.criar_job(db,'qa-fixture',question,manual='profunda')
        job['orcamento'].update(subs=1,buscas=6,paginas=8,replans=1,timeout_s=25)
        ra.salvar_job(db,job)
        start=time.monotonic()
        evaluate=ra._avaliar_rodada
        def observed(*args,**kwargs):
            value=evaluate(*args,**kwargs)
            snapshots.append(copy.deepcopy(args[1]['usados'].get('research_gaps',[])))
            return value
        ra._avaliar_rodada=observed
        try:
            result=ra.executar(db,job['id'],job['owner'],[Provider()],recover)
        finally:
            ra._avaliar_rodada=evaluate
        stored=ra.carregar_job(db,job['owner'],job['id'])
        ev=ra.listar_evidencias(db,job['owner'],job['id'])
        view=__import__('research_view').build_view(result,ev)
        out={'scope':'FIXTURE; same controlled corpus/readers; not external/inference/auth UI',
             'question':question,'status':result['status'],'queries':calls,'read_urls':reads,
             'duplicate_reads':len(reads)-len(set(reads)),'read_sources':sum(bool(e.get('texto_lido')) for e in ev),
             'gaps':stored['usados'].get('research_gaps',[]),
             'initial_gaps':snapshots[0] if snapshots else [], 'plan':result.get('etapas',[]),
             'events':ra.eventos_desde(db,job['owner'],job['id']),
             'replans':stored['usados'].get('replans',0),
             'controller_decisions':stored['usados'].get('controller_decisions',[]),
             'outcome':stored['usados'].get('research_outcome'),
             'synthesis':result.get('sintese'), 'jdui':view,
             'elapsed_s':round(time.monotonic()-start,3)}
        db.close()
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    data=run(args.root.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:data[k] for k in ('read_sources','replans','duplicate_reads','elapsed_s')}))
