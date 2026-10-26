"""Build compact release evidence from existing local runs; never runs a benchmark."""
import collections
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = Path(__file__).resolve().parent


def read(name):
    return json.loads((QA / name).read_text(encoding='utf-8-sig'))


def write(name, data):
    (QA / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def cli(name):
    text = (QA / (name + '.log')).read_text(encoding='utf-8-sig')
    return json.JSONDecoder().raw_decode(text.split('### Result\n', 1)[1])[0]


def coverage(data):
    return [{'id': r.get('id'), 'description': r.get('description'), 'state': r.get('state')}
            for r in (data or {}).get('requirements', [])]


def trace_summary(rows):
    return {
        'events': dict(collections.Counter(r.get('event', r['state']) for r in rows)),
        'reasons': dict(collections.Counter(r['reason_code'] for r in rows if r.get('reason_code'))),
        'charged': sum(bool(r.get('slot_charged')) for r in rows),
        'read_source_refs': len({r['source_ref'] for r in rows if r.get('source_ref') and r.get('read')}),
        'legacy_support_bindings_not_verified': any('requirement_support' not in r for r in rows),
    }


def main():
    replay = []
    trace_examples = {}
    for label, before, after in [
        ('api-extracted', 'replay-dev-api-text-before-verified.json', 'replay-dev-api-text-after-verified.json'),
        ('company-extracted', 'replay-dev-company-text-before-verified.json', 'replay-dev-company-text-after-verified.json'),
        *[(n + '-html', f'replay-dev-{n}-html-before.json', f'replay-dev-{n}-html-after.json')
          for n in ('api', 'company', 'history')],
        ('seeded-api-html', 'replay-seeded-html-before.json', 'replay-seeded-html-after.json'),
    ]:
        a, b = read(before), read(after)
        assert a['frozen_input_sha256'] == b['frozen_input_sha256']
        pair = {'case': label, 'frozen_input_sha256': b['frozen_input_sha256'],
                'same_input': True, 'extraction_executed': b.get('extraction_executed', False)}
        for key, value in [('before', a), ('after', b)]:
            pair[key] = {k: value.get(k) for k in (
                'source_head', 'read_calls', 'slots', 'distinct_urls', 'evidence_count',
                'sqlite_bytes', 'document_cache_chars', 'elapsed_s', 'process_rss_sample_bytes')}
            pair[key]['coverage'] = coverage(value.get('coverage'))
            pair[key]['trace'] = trace_summary(value.get('trace', []))
            refs = {q for e in value.get('evidence', []) for q in (e.get('provenance') or {}).get('query_ids', [])}
            pair[key]['unresolved_query_refs'] = sorted(refs - value.get('query_registry', {}).keys())
            pair[key]['queries'] = value.get('queries', [])
        replay.append(pair)
        if label == 'api-html':
            trace_examples[label] = {'scope': b['scope'], 'query_registry': b['query_registry'], 'events': b['trace']}
    write('replay-summary.json', {'scope': 'FIXED_INPUT_OPERATIONAL_COMPARISON_NOT_LIVE_RECALL', 'pairs': replay})
    write('trace-example.json', trace_examples)
    live = []
    for file in sorted(QA.glob('live-eff-*.json')):
        value = read(file.name)
        live.append({k: value.get(k) for k in ('case', 'dataset_sha256', 'source_revision', 'source_sha256',
                    'provider_calls', 'budget_used', 'read_evidence_count', 'evidence_count', 'status', 'outcome')}
                    | {'trace': trace_summary(value['trace'])})
    write('external-summary.json', {'scope': 'MODEL_AUTHORED_LIVE_NOT_HUMAN_GOLD_NO_PAIRED_NETWORK_BASELINE', 'cases': live})
    e2e = []
    for case in 'ABCDEF':
        value = read('e2e-' + case + '.json')
        row = {k: value.get(k) for k in ('name', 'query', 'seconds', 'http_status', 'content_type', 'job',
              'job_state', 'outcome', 'synthesis_llm', 'chat_result_id', 'synthesis_budget',
              'stage_timings', 'assistant_messages', 'reload_preserved', 'source_card_count', 'links', 'page_errors')}
        row['coverage'] = coverage(value.get('answer_coverage'))
        e2e.append(row)
    write('e2e-summary.json', {'scope': 'AUTHENTICATED_REAL_AGENT_TEMPORARY_SQLITE', 'cases': e2e})
    ui = {'visual': cli('browser-visual-stable'), 'sources': cli('browser-sources'),
          'gallery_interaction': cli('gallery-interaction-verified')}
    ui['sources'].pop('source_text', None)
    for name in ('browser-gallery', 'browser-cancel'):
        value = cli(name)
        value['public_answer_sha256'] = hashlib.sha256(value.pop('public_answer', '').encode()).hexdigest()
        value['source_card_count'] = len(value.pop('source_cards', []))
        ui[name] = value
    write('ui-summary.json', ui)
    checks = {}
    for name in ('full-suite-final-verified.log', 'trace-completion-focused.log', 'baseline-search.log',
                 'baseline-shopping.log', 'baseline-experience.log', 'reproduction-before.log',
                 'retention-reproduction.log', 'full-suite.log'):
        text = (QA / name).read_text(encoding='utf-8-sig')
        checks[name] = {'sha256': hashlib.sha256((QA / name).read_bytes()).hexdigest(),
                        'summary': re.findall(r'\d+ passed[^\n]*|\d+ failed[^\n]*|resultado: [^\n]*', text)[-1:]}
    write('validation-summary.json', {'checks': checks, 'baselines': {'search': '34/34', 'shopping': '59/59', 'experience': '16/16'}})
    # Raw pages, runtime metadata and source passages are deliberately not copied.
    manifest = []
    for path in sorted(QA.rglob('*')):
        if not path.is_file() or path.name in ('qa-runtime-private.json', 'qa-stop', 'manifest.json'):
            continue
        if path.suffix not in ('.json', '.log', '.png', '.csv'):
            continue
        manifest.append({'path': path.relative_to(QA).as_posix(), 'bytes': path.stat().st_size,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'raw_local_only': 'raw' in path.parts})
    write('manifest.json', {'scope': 'LOCAL_EVIDENCE_HASHES_NOT_ALL_FILES_ARE_COMMITTED', 'files': manifest})
    print(json.dumps({'replay_pairs': len(replay), 'live_cases': len(live), 'authenticated_cases': len(e2e),
                      'checks': checks['full-suite-final-verified.log']['summary']}))


if __name__ == '__main__':
    main()
