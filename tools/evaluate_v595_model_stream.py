"""One opt-in discovery + real SSE attempt, no retry or paid model switch."""
import argparse
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-tokens', type=int, default=160, choices=(160,1800))
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
    transport = {}
    wire = bytearray()
    original_open = urllib.request.urlopen
    def observed_open(*values, **kwargs):
        response = original_open(*values, **kwargs)
        transport.update(http_status=getattr(response,'status',None),
                         content_type=response.headers.get('Content-Type','').split(';')[0])
        class Observed:
            def __enter__(self): response.__enter__(); return self
            def __exit__(self,*args): return response.__exit__(*args)
            def __getattr__(self,key): return getattr(response,key)
            def read1(self,size):
                data=response.read1(size)
                wire.extend(data[:max(0,65536-len(wire))])
                return data
        return Observed()
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
                with patch('urllib.request.urlopen', observed_open):
                    response = bridge.chat_stream(cfg['proxy'], model, messages, delta, timeout=25, max_tokens=args.max_tokens)
            else:
                response = providers.chat_stream(prov, model, messages, delta, timeout=25, max_tokens=args.max_tokens)
            answer = response.get('texto', '')
            result.update(state='PARTIAL', stream_inference_executed=bool(chunks or answer),
                          chunks=len(chunks), sequence_ordered=[c[0] for c in chunks] == sorted(c[0] for c in chunks),
                          cited_literal_present=rs.normalized(excerpt) in rs.normalized(answer) and '[S1]' in answer,
                          answer=answer[:2000])
    except Exception as exc:
        result.update(reason=rs.safe_provider_code(exc), error_type=type(exc).__name__,
                      chunks=len(chunks), stream_inference_executed=bool(chunks))
    # Preserve protocol observations, never raw provider bodies/headers or credentials.
    events=[]
    for line in wire.decode('utf-8',errors='replace').splitlines():
        if line.startswith('data:'):
            try: events.append(json.loads(line[5:].strip()))
            except ValueError: pass
    transport.update(captured_bytes=len(wire), json_sse_events=len(events),
        capture_limit_bytes=65536, captured_prefix_only=len(wire)==65536,
        upstream_error_events=sum(isinstance(e,dict) and bool(e.get('error')) for e in events),
        nonempty_content_events=sum(bool(((e.get('choices') or [{}])[0].get('delta') or {}).get('content')) for e in events if isinstance(e,dict)))
    choices=[c for e in events if isinstance(e,dict) for c in (e.get('choices') or []) if isinstance(c,dict)]
    transport['delta_fields'] = sorted({k for c in choices for k in (c.get('delta') or {}) if k in ('content','role','reasoning','reasoning_content','tool_calls')})
    transport['reasoning_events'] = sum(bool((c.get('delta') or {}).get('reasoning_content') or (c.get('delta') or {}).get('reasoning')) for c in choices)
    transport['finish_reasons'] = sorted({c['finish_reason'] for c in choices if c.get('finish_reason') in ('stop','length','tool_calls','content_filter')})
    result['max_tokens']=args.max_tokens
    result['transport']=transport
    result['elapsed_s'] = round(time.monotonic()-started,3)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'answer'},ensure_ascii=False))


if __name__ == '__main__':
    main()
