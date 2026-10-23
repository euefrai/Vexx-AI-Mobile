"""One opt-in discovery + real SSE attempt, no retry or paid model switch."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import pc_agent
    import providers
    import hermes_bridge as bridge
    import research
    import research_synthesis as rs
    from assistant_identity import system_with_identity
    cfg = pc_agent.ai_config()
    result = {'model':cfg['model'], 'state':'BLOCKED', 'stream_inference_executed':False,
              'deep_research_approved':False, 'ui_tested':False}
    started = time.monotonic()
    chunks = []
    try:
        if not cfg['model'].endswith(':free'):
            result['reason'] = 'configured_model_not_explicitly_free'
        else:
            prov, model = providers.dividir(cfg['model'])
            if prov == 'hermes':
                try:
                    models = bridge.listar_modelos(cfg['proxy'], timeout=6)
                    result['discovered_model_count'] = len(models)
                    result['configured_model_discovered'] = any(
                        (m.get('id') if isinstance(m,dict) else m) == model for m in models)
                except Exception as exc:
                    result['discovery_error_code'] = rs.safe_provider_code(exc)
            source = research._recuperar_um({'url':'https://docs.python.org/3/library/asyncio-task.html',
                                             'titulo':'Python asyncio tasks'}, None, 6, 'TaskGroup cancellation')
            excerpt = source['trecho_usado'][:160]
            result['source_url'] = source['final']
            result['source_read'] = bool(source.get('lida'))
            messages = [{'role':'system','content':system_with_identity('Repita literalmente o trecho público fornecido, sem acrescentar fatos, e termine com [S1].')},
                        {'role':'user','content':excerpt}]
            def delta(seq, value):
                chunks.append((seq, value))
            if prov == 'hermes':
                response = bridge.chat_stream(cfg['proxy'], model, messages, delta, timeout=12, max_tokens=160)
            else:
                response = providers.chat_stream(prov, model, messages, delta, timeout=12, max_tokens=160)
            answer = response.get('texto', '')
            result.update(state='PARTIAL', stream_inference_executed=bool(chunks or answer),
                          chunks=len(chunks), sequence_ordered=[c[0] for c in chunks] == sorted(c[0] for c in chunks),
                          cited_literal_present=rs.normalized(excerpt) in rs.normalized(answer) and '[S1]' in answer,
                          answer=answer[:2000])
    except Exception as exc:
        result.update(reason=rs.safe_provider_code(exc), error_type=type(exc).__name__,
                      chunks=len(chunks), stream_inference_executed=bool(chunks))
    result['elapsed_s'] = round(time.monotonic()-started,3)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'answer'},ensure_ascii=False))


if __name__ == '__main__':
    main()
