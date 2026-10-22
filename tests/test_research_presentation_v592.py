import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
import jdui
import research
import research_view


def test_optional_cache_size_failure_keeps_response_and_evidence():
    db = sqlite3.connect(':memory:')
    research.criar_tabelas(db)
    result = research.pesquisa_rapida(db, 'qa', 'química',
        buscar_fn=lambda q: [{'titulo':'Química', 'url':'https://example.com/chemistry', 'trecho':'química'}],
        recuperar_fn=lambda u: {'titulo':'Química', 'texto':'Química aplicada a baterias e materiais.',
                                'tabelas':[{'rows':[['x' * 70000]]}]})
    assert result['cache_status'] == 'skipped_size_limit'
    assert result['fontes'][0]['texto_lido']
    assert db.execute('SELECT COUNT(*) FROM research_cache').fetchone()[0] == 0


def test_sources_contract_matches_python_and_javascript():
    message = {'version':jdui.VERSION, 'blocks':[{'type':'ui','component':'sources','props':{
        'title':'Fontes', 'items':[{'titulo':'Estudo real', 'url':'https://example.com/paper',
            'status':'utilizada', 'escopo':'Somente resumo', 'tipo':'academico',
            'relacao':'Trecho ligado à afirmação', 'data':'2026-10-01', 'data_evento':'2026-09-20'}]}}]}
    valid, py, errors = jdui.validar_mensagem(message)
    assert valid, errors
    assert shutil.which('node'), 'Node is required for Python/JS contract parity'
    script = "global.window={}; global.location={href: 'https://app.example/'}; eval(require('fs').readFileSync('public/jdui.js','utf8')); console.log(JSON.stringify(window.JDUI.validateMessage(JSON.parse(process.argv[1])).msg));"
    process = subprocess.run(['node','-e',script,json.dumps(message)],cwd=Path(__file__).parents[1],capture_output=True,text=True,encoding='utf-8')
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == py


def test_final_view_contains_actual_synthesis_and_explicit_abstract_scope():
    summary = {'objetivo':'Baterias', 'status':'concluida', 'modo':'profunda',
        'sintese':{'texto':'Conclusão baseada no resumo recuperado.'},
        'achados':[{'afirmacao':'Lacuna', 'estado':'INSUFFICIENT_EVIDENCE'}]}
    evidence = [{'id':'ev1','titulo':'Estudo', 'url':'https://example.com/paper',
                 'content_scope':'abstract_only','texto_lido':False,'trecho':'Resumo efetivamente recuperado.'}]
    msg = research_view.build_view(summary, evidence)
    assert msg['blocks'][0]['content'] == summary['sintese']['texto']
    props = next(b['props'] for b in msg['blocks'] if b.get('component') == 'sources')
    assert 'texto completo não lido' in props['items'][0]['escopo']
    claims = next(b['props']['claims'] for b in msg['blocks'] if b.get('component') == 'evidence')
    assert claims[0]['state'] == 'INCONCLUSIVE'


def test_scientific_recency_does_not_request_unrelated_news():
    import search_orchestrator as orch
    query='Pesquise estudos científicos recentes sobre baterias de estado sólido.'
    info=orch.classificar(query)
    gaps=orch.detectar_lacunas(query,[{'titulo':'Solid-state batteries','tipo':'academico','url':'https://example.com/paper','year':2026}],info['classes'],info)
    assert 'sem fonte de notícia recente' not in gaps
