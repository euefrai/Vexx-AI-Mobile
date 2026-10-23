"""Opt-in, bounded live evaluation. Isolated SQLite, no real chats or paid model.

Run with --live --output <new-directory>. Each case runs in a subprocess;
network hangs cannot consume the next case's time budget. Not a UI test.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = [
    ('price', 'shopping', 'Qual o preço do Samsung Galaxy A56 256 GB no Brasil agora?'),
    ('followup', 'followup', 'Veja outro modelo parecido com aquele e me dê o preço.'),
    ('comparison', 'research', 'Compare Galaxy A56 256 GB e Galaxy A36 256 GB: bateria, proteção e atualizações.'),
    ('news', 'research', 'Últimas notícias sobre inteligência artificial no Brasil nas últimas 24 horas.'),
    ('science', 'research', 'Quais estudos científicos com placebo avaliam creatina e força em adultos?'),
    ('divergence', 'research', 'FDA e EFSA divergem sobre limites de cafeína para adultos e gestantes? Compare condições e evidências.'),
]


def load_cases(path=None):
    cases = json.loads(Path(path).read_text(encoding='utf-8'))['cases'] if path else CASES
    if not isinstance(cases, list) or not 1 <= len(cases) <= 40:
        raise ValueError('evaluation requires 1..40 cases')
    normalized, ids = [], set()
    for row in cases:
        ident, route, question = row
        if not re.fullmatch(r'[a-z0-9_-]{1,60}', ident) or ident in ids:
            raise ValueError('case IDs must be unique safe basenames')
        if route not in ('shopping','followup','research','live_data') or not isinstance(question, str) or not 1 <= len(question) <= 1000:
            raise ValueError('invalid evaluation case')
        normalized.append((ident, route, question)); ids.add(ident)
    return normalized


def run_case(case, workspace):
    import pc_agent
    import research_agents as ra
    import shopping
    import conversation_followups
    import research_quality_lab as lab
    from research_synthesis import normalized
    import research
    import search_providers
    for blocked in os.environ.get('VEXX_EVAL_BLOCKED_PROVIDERS', '').split(','):
        if blocked in search_providers.PROVEDORES:
            research._circuito_falha(blocked)

    ident, route, question = case
    db = pc_agent.open_db(workspace / 'evaluation.sqlite3')
    owner, conv = 'live-evaluation-only', 'price-followup'
    started = time.monotonic()
    result = {'id': ident, 'route': route, 'question': question,
              'claim_support_human_review': None, 'ui_tested': False}
    import query_intelligence
    result['request'] = query_intelligence.analyze(question)
    try:
        if route == 'live_data':
            import live_data
            result.update(answer=live_data.respond(question, {}), model_calls_requested=0)
        elif route == 'shopping':
            data = shopping.pesquisar(db, owner, question, conv, usar_cache=False, teto_paginas=3)
            text = shopping.resumo_texto(data)
            (workspace / 'price-answer.txt').write_text(text, encoding='utf-8')
            result.update(answer=text, result=data)
        elif route == 'followup':
            prior = workspace / 'price-answer.txt'
            if not prior.exists():
                result.update(state='blocked', reason='previous_price_case_incomplete', answer='')
            else:
                previous = prior.read_text(encoding='utf-8')
                text = conversation_followups.product_reply(db, owner, conv, question, previous)
                result.update(state='answered' if text else 'unresolved', answer=text or '',
                              previous_answer=previous)
        else:
            job = ra.criar_job(db, owner, question, manual='rapida')
            calls = []
            cfg = pc_agent.ai_config()
            # Never silently switch to a paid model to make the benchmark pass.
            writer = pc_agent._research_writer(cfg, threading.Event()) if cfg['model'].endswith(':free') and not os.environ.get('VEXX_EVAL_MODEL_BLOCKED') else None
            def measured_writer(messages, timeout):
                calls.append({'timeout_s': round(timeout, 2)})
                return writer(messages, timeout)
            summary = ra.executar(db, job['id'], owner, ra.provedores_reais(orquestrado=True),
                                  sintetizar_fn=measured_writer if writer else None)
            evidence = ra.listar_evidencias(db, owner, job['id'])
            events = ra.eventos_desde(db, owner, job['id'])
            sources = {e['id']: e for e in evidence}
            synthesis = summary.get('sintese') or {}
            displayed = []
            for label, url in re.findall(r'\[(E\d+)\]\((https?://[^\s)]+)\)', synthesis.get('texto', '')):
                source = next((e for e in evidence if e['url'] == url), None)
                displayed.append({'label': label, 'url': url, 'source_exists': source is not None,
                                  'source_retrieved': bool(source) and ra._evidencia_lida(source),
                                  'claim_supported': None})
            provenance = synthesis.get('provenance') or []
            # Reuse lab metrics only for mechanical stages; support is NOT auto-graded.
            mechanical = [{'citation_exists': p.get('evidence_id') in sources,
                           'source_retrieved': ra._evidencia_lida(sources.get(p.get('evidence_id'), {})),
                           'passage_found': bool(p.get('quote')) and normalized(p['quote']) in normalized(sources.get(p.get('evidence_id'), {}).get('trecho', '')),
                           'claim_supported': False} for p in provenance]
            metrics = lab.citation_stage_metrics(mechanical)
            metrics['stages'].pop('claim_supported')
            result.update(answer=synthesis.get('texto', ''), summary=summary, evidence=evidence,
                          read_sources=sum(ra._evidencia_lida(e) for e in evidence),
                          model=cfg['model'] if writer else None, model_calls_requested=len(calls),
                          citation_mechanics=metrics,
                          displayed_citation_links=displayed,
                          search_events=[e for e in events if e['tipo'] in ('search_completed', 'source_opened', 'source_irrelevant')])
            import research_view
            import jdui
            view = research_view.build_view(summary, evidence)
            valid, _, errors = jdui.validar_mensagem(view)
            result['jdui_valid'] = valid
            result['jdui_errors'] = errors[:3]
            result['jdui'] = view
        result['provider_metrics'] = search_providers.metricas()
        result['elapsed_s'] = round(time.monotonic() - started, 3)
        return result
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--cases', default='', help='Comma-separated IDs; no retries')
    parser.add_argument('--child', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    cases = load_cases(args.dataset)
    if args.cases:
        selected = args.cases.split(',')
        if set(selected) - {c[0] for c in cases}:
            parser.error('unknown case ID')
        cases = [c for c in cases if c[0] in selected]
    if args.child:
        workspace = Path(os.environ['VEXX_LIVE_EVALUATION_WORKSPACE']).resolve()
        if not workspace.name.startswith('vexx-live-evaluation-'):
            parser.error('evaluation requires its isolated temporary workspace')
        case = next(c for c in cases if c[0] == args.child)
        result = run_case(case, workspace)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0

    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'vexx-live-research-evaluation/v1',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'live component pipelines; temporary SQLite; not authenticated UI',
              'case_timeout_s': 65, 'cases': []}
    with tempfile.TemporaryDirectory(prefix='vexx-live-evaluation-') as folder:
        env = dict(os.environ, VEXX_LIVE_EVALUATION_WORKSPACE=folder, PYTHONIOENCODING='utf-8')
        env['JULIA_SQLITE_PATH'] = str(Path(folder) / 'evaluation.sqlite3')
        env['VISUAL_CROSSING_USAGE_PATH'] = str(Path(folder) / 'weather-usage.sqlite3')
        blocked_providers = set(os.environ.get('VEXX_EVAL_BLOCKED_PROVIDERS', '').split(',')) - {''}
        for ident, route, question in cases:
            output = args.output / f'{ident}.json'
            started = time.monotonic()
            with (args.output / f'{ident}.log').open('w', encoding='utf-8') as log:
                try:
                    command = [sys.executable, __file__, '--live', '--child', ident,
                               '--output', str(output.resolve())]
                    if args.dataset:
                        command += ['--dataset', str(args.dataset.resolve())]
                    env['VEXX_EVAL_BLOCKED_PROVIDERS'] = ','.join(sorted(blocked_providers))
                    proc = subprocess.run(command, cwd=ROOT, env=env,
                                          stdout=log, stderr=log, timeout=65)
                    if proc.returncode == 0:
                        data = json.loads(output.read_text(encoding='utf-8'))
                        blocked_providers.update(name for name, metrics in data.get('provider_metrics', {}).items()
                                                 if any(metrics.get('erros', {}).get(code) for code in ('bloqueado','rate_limited')))
                        model_code = data.get('summary', {}).get('sintese', {}).get('fallback_provider_code')
                        if model_code in ('auth','quota','rate_limit','modelo-nao-encontrado','circuito_aberto','indisponivel'):
                            env['VEXX_EVAL_MODEL_BLOCKED'] = model_code
                    else:
                        data = {'id': ident, 'state': 'error', 'exit_code': proc.returncode}
                except subprocess.TimeoutExpired:
                    data = {'id': ident, 'state': 'timeout', 'elapsed_s': round(time.monotonic() - started, 3)}
            report['cases'].append(data)
            (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(ident, data.get('state', 'completed'), data.get('elapsed_s'), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
