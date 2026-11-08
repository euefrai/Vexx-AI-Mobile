"""Bounded default-model discovery and safe, actionable inference diagnostics."""
import re
import html
import threading
import time

import hermes_bridge

_CACHE = {}
_LOCK = threading.Lock()


def effective_models(cfg, models, timeout=2):
    models = list(models)
    if (not cfg.get('model_implicit') or not models
            or models[0] != hermes_bridge.DEFAULT_MODEL):
        return models
    base = cfg.get('proxy') or hermes_bridge.DEFAULT_PROXY_URL
    import providers
    resolved = providers.cached_default(base, models[0])
    if resolved != models[0]:
        return list(dict.fromkeys([resolved] + models[1:]))
    with _LOCK:
        cached = _CACHE.get(base)
        if cached and cached[0] > time.monotonic():
            selected = cached[1]
        else:
            selected = models[0]
            try:
                catalog = hermes_bridge.listar_modelos(base, timeout=max(.1, min(2, timeout)))
                ids = [m for m in catalog if isinstance(m, str)
                       and re.fullmatch(r'[A-Za-z0-9_~.][A-Za-z0-9_~.:/-]{0,119}', m)
                       and providers.supports_chat(m, getattr(catalog,'metadata',{}).get(m))]
                if selected not in ids:
                    selected = next((m for m in ids if m.endswith(':free')), selected)
            except hermes_bridge.BridgeErro:
                pass  # Keep the configured path; generation reports its real error.
            _CACHE[base] = (time.monotonic()+60, selected)
    return list(dict.fromkeys([selected]+models[1:]))


def with_failure_notice(text, code):
    if not text:
        return text
    notices = {
        'modelo-nao-encontrado': 'O modelo selecionado não está disponível. Atualize a lista e selecione outro modelo.',
        'modelo': 'O modelo selecionado não está disponível. Atualize a lista e selecione outro modelo.',
        'auth': 'O provedor recusou a autenticação. Confira a conexão ou a chave nas configurações.',
        'sem_chave': 'O provedor selecionado está sem chave configurada.',
        'rate_limit': 'O provedor atingiu o limite de requisições. Aguarde antes de tentar novamente.',
        'quota': 'A cota do provedor foi esgotada.',
        'timeout': 'O modelo não respondeu dentro do prazo.',
        'vazia': 'O modelo devolveu uma resposta vazia.',
        'indisponivel': 'Não foi possível conectar ao provedor do modelo.',
    }
    notice = notices.get(code, 'Não foi possível gerar a síntese por IA nesta tentativa.')
    return notice+' As fontes recuperadas foram preservadas abaixo.\n\n'+text


def grounded_reply(text, sources, query):
    """Check citation identity and attributed literal quotes, not factual truth."""
    read = [s for s in sources if s.get('status')=='aberta' and s.get('relevante',True)
            and str(s.get('texto_lido') or '').strip()]
    if not read:
        return text
    ids = {s.get('id') for s in read}
    prose = re.sub(r'```.*?```|`[^`]*`', '', text, flags=re.S)
    cited = set(re.findall(r'\[(S\d{1,3})\]', prose))
    def norm(value):
        return ' '.join(html.unescape(str(value)).casefold().split())
    body = '\n'.join(str(s.get('texto_lido') or '') for s in read)
    quotes = re.findall(r'["“]([^"”\n]{40,600})["”]\s*(?:—|–|--)\s*\w', text)
    uncited = any(len(p.strip()) >= 160 and not re.search(r'\[S\d{1,3}\]', p)
                  for p in re.split(r'\n\s*\n', prose))
    issue = ('missing_citations' if not cited or uncited else 'unknown_citations' if not cited <= ids else
             'unsupported_quote' if any(norm(q) not in norm(body) for q in quotes) else '')
    if not issue:
        return text
    import research
    digest = research.resumo_deterministico(sources, query)
    for source in sources:
        sid = str(source.get('id') or '')
        url = source.get('url','')
        if url and re.fullmatch(r'S\d{1,3}',sid):
            digest = digest.replace(']('+url+')', ']('+url+') ['+sid+']')
    return ('A redação do modelo não passou pela conferência de citações. '
            'Preservei os trechos e as fontes recuperadas.\n\n'+digest)
