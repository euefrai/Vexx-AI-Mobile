"""Smart Search Orchestrator (V5.5) — busca multi-provedor com honestidade.

Responsabilidades (nada mais):
1. Classificar o assunto da consulta (geral, técnico, acadêmico, notícias,
   enciclopédia, dados, imagens, livros, saúde) e o idioma provável.
2. Escolher provedores por afinidade e disponibilidade real.
3. Gerar consultas alternativas determinísticas (sinônimos, termos
   relacionados, decomposição) — SEM alterar números, marcas, orçamento,
   condições ou entidades do pedido.
4. Buscar com orçamento (nº de consultas/provedores e tempo), alternando
   provedor quando um falha, é bloqueado, volta vazio ou devolve
   resultados que não correspondem ao pedido (índice geral com lixo).
5. Deduplicar por URL canônica e ranquear por correspondência real.
6. Detectar lacunas (o que o pedido exige e as fontes não cobrem) e
   sugerir/executar buscas complementares limitadas.
7. Diferenciar: sem_resultados ≠ bloqueado ≠ falha de rede ≠
   sem_correspondencia (resultado existe, mas não responde ao pedido).

Não contorna bloqueios; não usa fonte paga; não inventa resultado.
"""
import re
import time
import unicodedata
import urllib.parse

import search_providers as sp
import evidence_graph as eg  # V5.7: regra única de fonte desatualizada

# ── Classes de assunto ─────────────────────────────────────────────
RX_TECNICO = re.compile(
    r"\b(python|javascript|typescript|java|c\+\+|c#|rust|golang|sql|api|sdk|"
    r"docker|kubernetes|linux|windows|android|ios|react|node|django|fastapi|"
    r"erro|bug|exceção|exception|stack ?trace|compile|compilar|instalar|"
    r"configurar|regex|algoritmo|banco de dados|sqlite|postgres|mysql|git|"
    r"servidor|deploy|json|xml|csv|html|css|criptografia|hash|token|asyncio|transformer|transformers|attention)\b", re.I)
RX_ACADEMICO = re.compile(
    r"\b(artigo|artigos|paper|papers|estudo|estudos|pesquisa cientifica|tese|dissertacao|doi|"
    r"revisao sistematica|meta-?analise|pubmed|scopus|openalex|crossref|"
    r"referência bibliográfica|citação)\b", re.I)
RX_NOTICIA = re.compile(
    r"\b(notícia|noticia|últimas|ultimas|hoje|ontem|esta semana|nesta semana|"
    r"agora|recente|recentes|breaking|aconteceu|eleição|eleicao|governo|"
    r"economia|mercado|bolsa|inflação|inflacao|juros|cotação|cotacao)\b", re.I)
RX_SAUDE = re.compile(
    r"\b(saúde|saude|doença|doenca|sintoma|tratamento|remédio|remedio|"
    r"vacina|câncer|cancer|diabetes|pressão|pressao|médic|medic|clínic|clinic)\b", re.I)
RX_DADOS = re.compile(
    r"\b(estatística|estatistica|dados|indicador|taxa|índice|indice|pib|pib per|"
    r"população|populacao|censo|percentual|porcentagem|média|media|total de|"
    r"crescimento|desemprego|selic|ipca|dólar|dolar|câmbio|cambio)\b", re.I)
RX_IMAGEM = re.compile(
    r"\b(imagem|imagens|foto|fotos|figura|mapa|gráfico de imagem|ilustração|"
    r"ilustracao|logo|bandeira)\b", re.I)
RX_LIVRO = re.compile(r"\b(livro|livros|autor|obra|isbn|editora|biografia)\b", re.I)
RX_ENCICLOPEDIA = re.compile(
    r"\b(o que (é|e)|quem (foi|é|e)|definição|definicao|significado|"
    r"história de|historia de|biografia|origem|conceito)\b", re.I)
RX_PRODUTO = re.compile(
    r"\b(preço|preco|quanto custa|quanto custam|custa quanto|comprar|compr|"
    r"onde encontrar|oferta|promoção|promocao|mais barato|barato|loja|modelo|"
    r"marca|vale a pena|custo-?benefício)\b", re.I)
RX_COMPARACAO = re.compile(
    r"\b(compare|comparar|comparação|comparacao|versus|\bvs\b|diferença|diferenca|"
    r"melhor entre|qual melhor|prós e contras|pros e contras)\b", re.I)
RX_TEMPORAL = re.compile(
    r"\b(quando|em que ano|desde|até|ate|prazo|data|vigência|vigencia|"
    r"atualizado|cronologia|linha do tempo)\b", re.I)

# Sinônimos determinísticos (pt-BR) usados para gerar consultas
# alternativas. Nunca alteram números, nomes próprios ou restrições.
SINONIMOS = {
    "carro": ("automóvel",), "automóvel": ("carro",), "celular": ("smartphone",),
    "smartphone": ("celular",), "notebook": ("laptop",), "laptop": ("notebook",),
    "emprego": ("vaga",), "vaga": ("emprego",), "salário": ("remuneração",),
    "preço": ("valor",), "valor": ("preço",), "empresa": ("companhia",),
    "comprar": ("adquirir",), "doença": ("enfermidade",), "médico": ("clínico",),
    "estudo": ("pesquisa",), "pesquisa": ("estudo",), "lei": ("legislação",),
    "governo": ("poder público",), "escola": ("instituição de ensino",),
    "rápido": ("veloz",), "erro": ("falha",), "falha": ("erro",),
    "configurar": ("configuração",), "instalar": ("instalação",),
    "como fazer": ("tutorial",), "tutorial": ("passo a passo",),
    "diferença": ("comparação",), "comparação": ("diferença",),
    "significado": ("definição",), "definição": ("significado",),
}
# Expansões por classe (ajudam provedores de índice geral).
EXTRAO_CLASSE = {
    sp.CLASSE_TECNICA: ("documentação", "exemplo"),
    sp.CLASSE_ACADEMICA: ("estudo", "artigo"),
    sp.CLASSE_NOTICIA: ("",),
    sp.CLASSE_DADOS: ("dados oficiais",),
    sp.CLASSE_LIVRO: ("livro",),
}
# Tradução técnica determinística (ajuda Stack Exchange/HN/PubMed).
TECNICO_EN = {
    "memória": "memory", "desempenho": "performance", "erro": "error",
    "instalar": "install", "configurar": "configure", "arquivo": "file",
    "banco de dados": "database", "rede": "network", "servidor": "server",
    "segurança": "security", "criptografia": "encryption", "teste": "test",
    "exceção": "exception", "compilar": "compile", "executar": "run",
    "função": "function", "classe": "class", "biblioteca": "library",
    "permissão": "permission", "requisição": "request", "resposta": "response",
    "lento": "slow", "travando": "hanging", "vazamento": "leak",
}

_ESTOPO = {"para", "como", "mais", "sobre", "entre", "isso", "esse", "esta",
           "este", "qual", "quais", "onde", "quando", "porque", "pode", "ser",
           "são", "sao", "the", "and", "com", "dos", "das", "uma", "que",
           "não", "nao", "por", "favor", "quero", "preciso", "gostaria",
           "pesquise", "busque", "procure", "encontre", "veja", "me", "diga",
           # verbos/funcionais de pergunta: aparecem em qualquer página sobre a
           # palavra ("funciona", "faz") e por isso NÃO provam correspondência
           # temática (V5.7: "como funciona X" devolvia dicionários como "ok").
           "funciona", "funcionam", "funcionar", "funcionava", "funcionavam",
           "faz", "fazem", "fazer", "fez", "fizeram", "fica", "ficam", "ficar",
           "tem", "têm", "ter", "existe", "existem", "serve", "servem",
           "significa", "significam", "usar", "usa", "usam", "dá", "dar",
           "vai", "vão", "vao", "era", "eram", "foi", "foram", "seria",
           "será", "sera", "acontece", "aconteceu", "aconteceram"}
_GENERICOS = {"comprar", "oferta", "promo", "promoção", "promocao", "preço",
              "preco", "valor", "melhor", "barato", "brasil", "site", "site:"}
# Palavras que NÃO provam correspondência: aparecem em qualquer página de
# loja/busca ("preço", "até", "melhor"…) e por isso não podem ser usadas
# para afirmar que um resultado responde ao pedido (relevância de índice
# geral costuma voltar lixo quando só esses termos "batem").
_GENERICOS_CORRESPONDENCIA = {
    "comprar", "compr", "compra", "compre", "oferta", "ofertas", "promo",
    "promoção", "promocao", "preço", "preco", "preços", "precos", "valor",
    "valores", "melhor", "melhores", "barato", "barata", "brasil", "site",
    "site:", "até", "ate", "hoje", "reais", "quanto", "custa", "custam",
    "onde", "encontrar", "encontre", "loja", "lojas", "vale", "pena",
    "desconto", "cupom", "frete", "venda", "vendas", "compare", "comparar",
    "pesquisar", "buscar", "procurar", "queria", "preciso",
    # Follow-ups de interface/ordenação: "agora mostre só os resultados mais
    # baratos" não tem assunto e não pode autorizar busca externa.
    "agora", "apenas", "somente", "mostre", "mostra", "mostrar", "exiba",
    "exibir", "liste", "lista", "listar", "resultado", "resultados",
    "pesquisa", "pesquisados", "encontrados", "encontradas", "opção", "opcao",
    "opções", "opcoes", "ordem", "ordenar", "ordene", "baratos", "baratas",
    "barato", "barata", "caros", "caras", "primeiro", "primeiros", "primeira",
    "primeiras", "segundo", "segunda", "terceiro", "terceira", "dois", "duas",
    "três", "tres", "foto", "fotos", "imagem", "imagens",
}


_GENERICOS_CORRESPONDENCIA.update({
    "principais", "novidades", "acontecimentos", "relevantes",
    "usar", "utilizar", "utilize", "utilizando", "explique-me",
    "como", "funciona", "funcionam", "traga", "trazer", "explique", "explique-me", "fontes", "fonte", "tecnicas", "técnicas",
    "tecnica", "técnica", "analise", "análise", "usando", "sobre", "pesquise",
    "documentacao", "documentação", "oficial", "oficiais", "recentes", "recente",
    "avanços", "avancos", "estudos", "cientificos", "científicos", "cientifica", "científica",
})


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower())
                   if not unicodedata.combining(c))


def _termos(texto: str, minimo: int = 3) -> list:
    return [t for raw in re.findall(r"[0-9a-zà-ú][0-9a-zà-ú\-\+\.]*", (texto or "").lower())
            if len(t := raw.strip(".,;:-")) >= minimo and t not in _ESTOPO]


def _termos_correspondencia(consulta: str) -> list:
    """Termos do pedido que provam correspondência (sem genéricos de loja)."""
    import query_intelligence as qi
    request = qi.analyze(consulta)
    params = request["parameters"]
    if request["domain"] in ("air_travel", "bus_travel") and params.get("origin") and params.get("destination"):
        consulta = params["origin"] + " " + params["destination"]
    elif request["domain"] in ("news", "events") and params.get("location"):
        consulta = params["location"] + (" eventos culturais" if request["domain"] == "events" else "")
    elif request['domain']=='science':
        consulta=re.sub(r'\b(artigos?|cient[ií]fic[oa]s?|estudos?|recentes?)\b',' ',consulta,flags=re.I)
        consulta=re.sub(r'\b(texto completo(?: aberto)?|acesso aberto|com doi|original)\b',' ',consulta,flags=re.I)
    if request['domain'] == 'documents':
        consulta=re.sub(r'\b(documenta[cç][aã]o|documentation|oficial|oficiais)\b', ' ', consulta, flags=re.I)
    consulta=re.sub(r'\bfaz\s+bem\b',' ',consulta,flags=re.I)
    return [t for t in _termos(consulta) if t not in _GENERICOS_CORRESPONDENCIA]


def _tem_termo(termo: str, texto: str) -> bool:
    """Token boundaries prevent API from matching capital or RAM from programa."""
    aliases = {"consumo": ("consome","consumiu","consumido","consumption"), "fotossintese": ("photosynthesis",), "arquitetura": ("architecture",), "baterias": ("batteries",),
               "estado": ("state",), "solido": ("solid",), "assincrono": ("asynchronous",), "cancelamento": ("cancellation", "cancelled", "cancelling"), "materiais": ("materials",), "semicondutores": ("semiconductor", "semiconductors")}
    term = _sem_acentos(termo)
    text = _sem_acentos(texto)
    aliases.update({'exemplos':('examples','example'),'limitacoes':('limitations','limitation')})
    if re.fullmatch(r'[a-z_]\w*(?:\.[a-z_]\w*)+',term):
        # Semantic HTML can split a qualified API name across adjacent spans.
        text=re.sub(r'\s*\.\s*','.',text)
    if re.fullmatch(r"\d+(?:[.,]\d+)*", term):
        # A grouping separator does not change the requested amount: 3.000 = 3000.
        term = re.sub(r"(?<=\d)[.,](?=\d{3}(?:\D|$))", "", term)
        text = re.sub(r"(?<=\d)[.,](?=\d{3}(?:\D|$))", "", text)
    return any(re.search(r"(?<![\w])" + re.escape(value) + r"(?![\w])", text)
               for value in (term, *aliases.get(term, ()), *SINONIMOS.get(term, ())))


def correspondencia_item(a: dict, consulta: str) -> dict:
    termos = _termos_correspondencia(consulta)
    texto = " ".join(str(a.get(k) or "") for k in ("titulo", "trecho"))
    presentes = [t for t in termos if _tem_termo(t, texto)]
    ratio = len(presentes) / len(termos) if termos else 1.0
    tipo = "EXACT_MATCH" if ratio == 1 else "PARTIAL_MATCH" if presentes else "IRRELEVANT"
    return {"tipo": tipo, "cobertura": round(ratio, 3),
            "faltantes": [t for t in termos if t not in presentes]}


def _util_para_pedido(a: dict, termos: list, consulta: str = "") -> bool:
    import query_intelligence as qi
    request = qi.analyze(consulta) if consulta else {}
    params = request.get("parameters") or {}
    text = qi.normalized(" ".join(str(a.get(k) or "") for k in ("titulo", "trecho")))
    if request.get("domain") in ("air_travel", "bus_travel", "news", "events"):
        import search_verticals
        if request.get('domain') == 'news' or params.get('location') or (params.get('origin') and params.get('destination')):
            if not search_verticals.assess(request, a)['eligible']:return False
            if params.get('location') or (params.get('origin') and params.get('destination')):return True
    if _context_mismatch(a, consulta):
        return False
    if a.get("metadata_source") == "academic_provider" and not (a.get("abstract") or "").strip() and not (a.get('open_access') and a.get('pdf_url')):
        return False
    if not termos:
        return True
    texto = " ".join(str(a.get(k) or "") for k in ("titulo", "trecho", "curated_topic"))
    ratio = sum(_tem_termo(t, texto) for t in termos) / len(termos)
    # Comparisons may legitimately need one primary page per compared subject.
    return ratio >= (0.5 if RX_COMPARACAO.search(consulta) else 0.6)


def _context_mismatch(a: dict, consulta: str) -> list:
    """Hard entity/context exclusions, separate from broad lexical coverage."""
    q=_sem_acentos(consulta);body=_sem_acentos(' '.join(str(a.get(k) or '') for k in ('titulo','trecho')))
    models=set(re.findall(r'\b[a-z]{1,16}-?\d+[a-z0-9-]*\b',q))
    matched=[_tem_termo(m,body) for m in models]
    reasons=[]
    if matched and not (any(matched) if RX_COMPARACAO.search(consulta) else all(matched)):
        reasons.append('ENTITY_MISMATCH')
    identifiers=set(re.findall(r'(?<![\w/:])(?:[a-z_]\w*\.)+[A-Z]\w*\b',consulta or ''))
    matched_ids=[_tem_termo(identifier,body) for identifier in identifiers]
    if matched_ids and not (any(matched_ids) if RX_COMPARACAO.search(consulta) else all(matched_ids)):
        reasons.append('ENTITY_MISMATCH')
    import query_intelligence as qi
    operations={r['entity'] for r in qi.answer_requirements(consulta)
                if re.fullmatch(r'\w+(?:\.\w+)+',r['entity'])}
    if operations:
        # A generic calculator/dictionary cannot answer a named API. Preserve
        # sparse metadata when its actual path identifies the requested method.
        raw_path=urllib.parse.unquote(urllib.parse.urlsplit(str(a.get('url') or '')).path)
        path=_sem_acentos(raw_path).replace('/','.')
        scoped=re.sub(r'\s*\.\s*','.',body+' '+path).replace('.prototype.','.')
        def identifies(op):
            op=_sem_acentos(op).replace('.prototype.','.')
            if re.search(r'(?<!\w)'+re.escape(op)+r'(?!\w)',scoped):return True
            # A real parent reference is a navigation lead, not direct evidence.
            # Keep it for the existing bounded link reader; dictionaries and
            # generic homepages do not acquire this exception.
            return bool(re.search(r'/(?:docs?|reference|api|library)/',raw_path,re.I)
                        and re.search(r'(?<!\w)'+re.escape(op.split('.')[0])+r'(?:[./_-]|$)',path))
        present=[identifies(op) for op in operations]
        if not (any(present) if RX_COMPARACAO.search(consulta) else all(present)):
            reasons.append('ENTITY_MISMATCH')
    named = []
    model_entities={r['entity'] for r in qi.answer_requirements(consulta)
                    if r['attribute'] in ('weight','battery','price') and re.search(r'\d',r['entity'])}
    named.extend(qi.entity_alias_matches(name,body) for name in model_entities)
    for entity in qi.topic_profile(consulta)['entities']:
        name = entity['name']
        tokens = _termos(name)
        if len(tokens) >= 2 or entity['kind'] == 'organization' or re.fullmatch(r'[A-Z]{3,}', name) or RX_COMPARACAO.search(consulta):
            exact=all(_tem_termo(t, body) for t in tokens)
            if re.search(r'\d',name):
                exact=qi.entity_alias_matches(name,body)
            named.append(exact)
    if named and not (any(named) if RX_COMPARACAO.search(consulta) else all(named)):
        reasons.append('ENTITY_MISMATCH')
    accessory=r'\b(capa|carregador|pelicula|bateria de reposicao|compativel com|acessorio|acessorios)\b'
    if re.search(accessory,body) and not re.search(accessory,q) and re.search(r'\b(notebook|celular|smartphone|roteador|geladeira|lavadora)\b',q):
        reasons.append('INTENT_MISMATCH')
    return list(dict.fromkeys(reasons))


def _correspondencia(achados: list, termos: list) -> float:
    """Fração dos termos (não-genéricos) presentes nos melhores achados."""
    topo = (achados or [])[:8]
    if not topo:
        return 0.0
    if not termos:
        return 1.0
    juntos = " ".join(((a.get("titulo") or "") + " " + (a.get("trecho") or "")).lower()
                      for a in topo)
    return round(sum(1 for t in termos if _tem_termo(t, juntos)) / len(termos), 3)


def _temas_cobertos(achados: list, consulta: str) -> set:
    """Termos do pedido (não-genéricos) cobertos por algum achado."""
    termos = _termos_correspondencia(consulta)
    texto = " ".join(((a.get("titulo") or "") + " " + (a.get("trecho") or "")).lower()
                     for a in achados or [])
    return {t for t in termos if _tem_termo(t, texto)}


def _retrato(achados: list, consulta: str) -> dict:
    """Retrato do que já foi coberto: domínios distintos e temas do pedido."""
    terms = _termos_correspondencia(consulta)
    useful = [a for a in achados or [] if _util_para_pedido(a, terms, consulta)]
    dominios = {_dominio(a.get("url", "")) for a in useful} - {""}
    return {"dominios": dominios, "temas": _temas_cobertos(useful, consulta)}


def _ganho_informacao(antes: dict, achados: list, consulta: str) -> dict:
    """Ganho real de informação desde o retrato `antes` (não é quantidade:
    é domínio novo e tema do pedido coberto a mais)."""
    agora = _retrato(achados, consulta)
    novos_dominios = sorted(agora["dominios"] - set(antes.get("dominios") or ()))
    novos_temas = sorted(agora["temas"] - set(antes.get("temas") or ()))
    return {"dominios_novos": novos_dominios, "temas_novos": novos_temas,
            "ganho_real": bool(novos_dominios or novos_temas)}


def classificar(consulta: str) -> dict:
    """Assunto(s) da consulta. Só regras determinísticas explícitas."""
    t = consulta or ""
    ta = _sem_acentos(t)
    classes = []
    if RX_TECNICO.search(ta):
        classes.append(sp.CLASSE_TECNICA)
    if RX_ACADEMICO.search(ta):
        classes.append(sp.CLASSE_ACADEMICA)
    if RX_SAUDE.search(ta):
        classes.append(sp.CLASSE_SAUDE)
    if RX_NOTICIA.search(ta):
        classes.append(sp.CLASSE_NOTICIA)
    if RX_DADOS.search(ta):
        classes.append(sp.CLASSE_DADOS)
    if RX_LIVRO.search(ta):
        classes.append(sp.CLASSE_LIVRO)
    if RX_ENCICLOPEDIA.search(ta):
        classes.append(sp.CLASSE_ENCICLOPEDIA)
    if RX_IMAGEM.search(ta):
        classes.append(sp.CLASSE_IMAGEM)
    produto = bool(RX_PRODUTO.search(ta))
    comparacao = bool(RX_COMPARACAO.search(ta))
    temporal = bool(RX_NOTICIA.search(ta) or RX_TEMPORAL.search(ta))
    if not classes:
        classes.append(sp.CLASSE_GERAL)
    return {"classes": classes, "produto": produto, "comparacao": comparacao,
            "temporal": temporal, "tecnica": sp.CLASSE_TECNICA in classes,
            "documentacao": bool(re.search(r"documentacao|documentation|fontes? tecnicas|fontes? oficiais", ta)),
            "academica": sp.CLASSE_ACADEMICA in classes}


# ── Consultas alternativas e complementares ────────────────────────
def query_plan(consulta: str) -> list:
    """Small purpose-labelled plan; execution still shares the existing budgets."""
    import query_intelligence as qi
    profile = qi.topic_profile(consulta)
    original = str(consulta or '').strip()
    focused = profile['focused_query']
    out = []
    if focused and focused.casefold().rstrip('.!?') != original.casefold().rstrip('.!?'):
        out.append({'type': 'TOPIC_FOCUSED', 'query': focused,
                    'purpose': 'antepor assunto explícito e preservar informação requerida'})
    if original:
        out.append({'type': 'ORIGINAL_QUERY', 'query': original, 'purpose': 'pedido original sem condensação'})
    if profile['required_information'] or profile['soft_preferences']:
        exact = profile['primary_topic']
        if not profile['hard_constraints']['unparsed_original_guard'] and exact and all(exact.casefold() != p['query'].casefold() for p in out):
            out.append({'type': 'ENTITY_EXACT', 'query': exact,
                        'purpose': 'resolver assunto explícito quando operações dominam os resultados; validar pelo pedido original'})
    return out


def variantes(consulta: str, classes=None, teto: int = 3, produto: bool = False) -> list:
    """Consultas derivadas da original, determinísticas e conservadoras.

    Regra dura: números, orçamento, marcas, modelos e condições do pedido
    nunca mudam — só se acrescentam termos de busca. Consulta de produto
    não recebe expansão por classe (o termo do pedido é a busca).
    """
    base = re.sub(r"\s+", " ", (consulta or "").strip())
    if not base:
        return []
    classes = list(classes or [])
    out = [base]
    if not produto:
        scholarly = re.match(r"^(?:pesquise|pesquisar|busque|buscar)?\s*((?:estudos|artigos|papers|pesquisas)(?:\s+(?:cient[ií]ficos|cient[ií]ficas|recentes|atuais|de\s+20\d\d)){0,4})\s+(?:sobre|acerca\s+de)\s+(.+)$", base, re.I)
        if scholarly:
            out.insert(0, (scholarly.group(2) + " " + scholarly.group(1)).strip())
    termos = _termos(base)
    trocas = []
    for termo in termos:
        for alt in SINONIMOS.get(termo, ()):  # troca 1 termo por 1 sinônimo
            trocas.append(re.sub(r"\b" + re.escape(termo) + r"\b", alt, base, count=1, flags=re.I))
        if len(trocas) >= 2:
            break
    for alt in trocas[:2]:
        if alt.lower() != base.lower() and alt not in out:
            out.append(re.sub(r"\s+", " ", alt).strip()[:200])
    # Sem acento (índices costumam indexar as duas formas)
    sem_ac = re.sub(r"[àáâãä]", "a", base)
    sem_ac = re.sub(r"[éêë]", "e", sem_ac)
    sem_ac = re.sub(r"[íîï]", "i", sem_ac)
    sem_ac = re.sub(r"[óôõö]", "o", sem_ac)
    sem_ac = re.sub(r"[úûü]", "u", sem_ac)
    sem_ac = re.sub(r"ç", "c", sem_ac)
    if sem_ac.lower() != base.lower() and len(out) < teto:
        out.append(sem_ac[:200])
    # Expansão por classe (nunca para produtos: lá o termo é o pedido)
    if not produto:
        for classe in classes:
            for extra in EXTRAO_CLASSE.get(classe, ()):
                if not extra:
                    continue
                cand = f"{base} {extra}".strip()[:200]
                if cand not in out:
                    out.append(cand)
                if len(out) >= teto:
                    break
    return out[:teto]


def consulta_cientifica(consulta: str) -> str:
    """Small deterministic vocabulary; unknown subjects retain original words."""
    q = _sem_acentos(consulta)
    for pt, en in (("baterias de estado solido", "solid-state batteries"),
                   ("materiais semicondutores", "semiconductor materials"),
                   ("arquitetura transformer", "Transformer architecture")):
        q = q.replace(pt, en)
    q = re.sub(r"\b(pesquise|pesquisar|estudos?|cientificos?|cientificas?|recentes?|avancos|sobre|fontes|tecnicas)\b", " ", q)
    return re.sub(r"\s+", " ", q).strip(" .")[:180]


def termos_para_provedor(consulta: str, classe: str) -> str:
    """Consulta ajustada ao provedor (ex.: técnico → inglês determinístico)."""
    if classe != sp.CLASSE_TECNICA:
        return consulta
    t = consulta
    for pt, en in TECNICO_EN.items():
        t = re.sub(r"\b" + re.escape(pt) + r"\b", en, t, flags=re.I)
    return t[:180]


# V5.7 — reformulação conservadora: remove APENAS a moldura de pergunta
# ("como funciona", "o que é", "quanto custa"…) e artigos iniciais, mantendo
# íntegros nomes, números, modelos e marcas. Usada para tentar a MESMA fonte
# com a consulta de conteúdo quando a consulta original volta sem relação
# (ex.: índice devolve dicionários de "funciona" para "como funciona X").
_SCAFFOLD_PERGUNTA = (
    "me explique como", "me explique", "explique como", "explique", "explica",
    "para que serve", "pra que serve", "para que servem", "o que significa",
    "o que são", "o que sao", "o que é", "o que e", "o que fazem", "o que faz",
    "como funcionam", "como funciona", "como fazer", "como faz", "como usar",
    "como usam", "como montar", "como configurar", "como instalar",
    "como resolver", "como consertar", "quem foram", "quem foi", "quem é",
    "quem e", "quem eram", "quem são", "quem sao", "qual é", "qual e",
    "qual o preço de", "qual o preco de", "qual o", "qual a", "qual foi",
    "quais são", "quais sao", "quais foram", "quando foi", "quando aconteceu",
    "quando ocorreu", "onde fica", "onde ficam", "onde encontrar",
    "onde comprar", "onde achar", "por que", "porque", "pq", "quanto custam",
    "quanto custa",
)


def consulta_conteudo(consulta: str) -> str:
    """Consulta sem a moldura de pergunta; "" quando não há o que reformular.

    Determinística e conservadora: só remove prefixos de pergunta conhecidos
    e artigos iniciais. Se o que sobra não tem termo distintivo (fora dos
    genéricos de loja/estopo), devolve "" — nunca inventa consulta.
    """
    t = re.sub(r"\s+", " ", (consulta or "").strip()).rstrip("?!.:;")
    if not t:
        return ""
    baixo = _sem_acentos(t).lower()
    t = re.sub(r'^(?:pesquise|pesquisar|encontre|busque|procure|mostre|liste)\s+', '', t, flags=re.I)
    baixo = _sem_acentos(t).lower()
    for prefixo in _SCAFFOLD_PERGUNTA:
        pa = _sem_acentos(prefixo).lower()
        if baixo == pa:
            return ""
        if baixo.startswith(pa + " "):
            t = t[len(prefixo):].strip()
            break
    t = re.sub(r"^(?:de|do|da|dos|das|no|na|nos|nas|um|uma|uns|umas|o|a|os|as)\s+",
               "", t, flags=re.I)
    t = re.sub(r"\s+(?:o|a|os|as|um|uma)$", "", t.strip(), flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    if not t or _sem_acentos(t).lower() == _sem_acentos(consulta).lower():
        return ""
    distintivos = [x for x in _termos(t) if x not in _GENERICOS_CORRESPONDENCIA]
    if not distintivos:
        return ""
    return t[:200]


# ── URL canônica, dedupe e ranking ─────────────────────────────────
_RX_TRACKING = re.compile(
    r"^(utm_[a-z]+|gclid|fbclid|msclkid|mc_[a-z]+|ref|ref_src|source|spm|"
    r"_ga|yclid|igshid|si|srsltid|sca_esv|ei|ved|usg|oq|gs_lcp|cvid|"
    r"sa|exp|modified|click_id|aff[_-]?\w*)$", re.I)


def canonizar_url(url: str) -> str:
    """URL canônica para dedupe (sem rastreio, host minúsculo, sem barra final).

    Retorna "" quando não é URL http(s) com host: resultado sem URL
    utilizável não é fonte (não pode ser aberto nem verificado).
    """
    try:
        p = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return ""
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        return ""
    host = p.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    porta = f":{p.port}" if p.port and p.port not in (80, 443) else ""
    pares = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=False)
             if not _RX_TRACKING.match(k)]
    query = urllib.parse.urlencode(sorted(pares))
    caminho = re.sub(r"/+$", "", p.path) or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), host + porta, caminho, query, ""))


def _dominio(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url or "").hostname or "").lower()[:120]
    except ValueError:
        return ""


RX_INDICE_TITULO = re.compile(
    r"^\s*(resultados?( de busca| da busca| para)|p[áa]gina de resultados|"
    r"busca por |busca - |search results|listagem de|[íi]ndice de|"
    r"category:|categoria:)", re.I)
RX_INDICE_CAMINHO = re.compile(
    r"^/(search|busca|resultados?|categoria|category|tags?|[íi]ndice|"
    r"indice|directory)(/|$)", re.I)


def _pagina_de_indice(a: dict) -> bool:
    """Página de índice/listagem geral — não é conteúdo do assunto.

    V5.7 (FASE 2): quando a 1ª rodada traz só índices, o resultado é
    reclassificado: a página é sinalizada e demovida (nunca apagada) e a
    recuperação pede o assunto direto (fontes primárias).
    """
    if RX_INDICE_TITULO.search((a.get("titulo") or "").strip()):
        return True
    try:
        target = urllib.parse.urlsplit(a.get("url_final") or a.get("url") or "")
        caminho = target.path or "/"
    except ValueError:
        return False
    # Aggregator pages/wrappers are discovery, never the publisher's article.
    if (target.hostname or '').lower().rstrip('.') == 'news.google.com':
        return True
    return bool(RX_INDICE_CAMINHO.search(caminho) or
                re.fullmatch(r'/(noticias|news|ultimas-noticias)/?', caminho, re.I))


def _data_do_item(a: dict):
    """Publication only; retrieval, indexing and update dates are not substitutes."""
    import email.utils
    from datetime import datetime, timezone
    meta = a.get("meta") or {}
    bruto = str(a.get("publicado_em") or meta.get("publicado_em")
                or a.get("published_at") or a.get("publication_date")
                or a.get("data") or a.get("year") or "").strip()
    if not bruto:
        return None
    try:
        if re.fullmatch(r"\d{4}(?:-\d{2})?", bruto):
            parts = [int(v) for v in bruto.split("-")]
            dt = datetime(parts[0], parts[1] if len(parts) > 1 else 1, 1, tzinfo=timezone.utc)
        else:
            try:
                dt = email.utils.parsedate_to_datetime(bruto)
            except (TypeError, ValueError):
                dt = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        # Future or malformed dates never get a freshness bonus.
        return dt if dt <= datetime.now(timezone.utc) else None
    except (TypeError, ValueError, OverflowError):
        return None


def deduplicar(achados: list) -> tuple:
    """Agrupa por URL canônica e sinaliza republicações. (únicos, descartes).

    V5.7: título praticamente idêntico (Jaccard >= 0.9, >= 4 termos) entre
    URLs distintas é registrado como republicação — a versão posterior é
    descartada com motivo e a mantida ganha `republicacoes` (nunca apagado).
    "Posterior" usa a data declarada quando ambas existem (a mais antiga
    fica como base); sem data conhecida, mantém a ordem de chegada.
    """
    vistos, unicos, descartes = {}, [], []
    for a in sorted(achados or [], key=lambda item: item.get('content_scope') == 'feed_metadata'):
        url = (a.get("url") or "").strip()
        doi = str(a.get("doi") or "").lower().removeprefix("https://doi.org/").removeprefix("doi:").strip()
        chave = "doi:" + doi if re.fullmatch(r"10\.\d{4,9}/\S+", doi) else canonizar_url(url)
        if not url or not chave:
            descartes.append({"url": url[:200], "motivo": "url inválida"})
            continue
        if chave in vistos:
            anterior = vistos[chave]
            # mantém a versão com mais informação (trecho/título maior)
            if len(a.get("trecho") or "") > len(anterior.get("trecho") or ""):
                anterior["trecho"] = a.get("trecho") or anterior.get("trecho")
            descartes.append({"url": url[:200], "motivo": f"duplicada de {chave[:120]}"})
            continue
        a["url_canonica"] = chave
        vistos[chave] = a
        unicos.append(a)

    # V5.7 — republicações: mesmo texto/título em domínios distintos
    vistos_titulo = []
    finais = []
    for a in unicos:
        tokens = set(_termos(a.get("titulo") or ""))
        if len(tokens) >= 4:
            dono = None
            for conj, item in vistos_titulo:
                if a.get("doi") and item.get("doi") and a["doi"].lower() != item["doi"].lower():
                    continue  # Same title does not override distinct bibliographic identities.
                uniao = len(tokens | conj)
                if uniao and (len(tokens & conj) / uniao) >= 0.9:
                    dono = item
                    break
            if dono is not None:
                d_dono, d_nova = _data_do_item(dono), _data_do_item(a)
                if a.get('content_scope') != 'feed_metadata' and d_nova is not None and d_dono is not None and d_nova < d_dono:
                    # Evidência real (pubDate declarada): a versão mais antiga é
                    # a base; a mantida até aqui vira republicação — sem apagar.
                    reps = list(dono.get("republicacoes") or [])
                    reps.append((dono.get("url") or "")[:200])
                    a["republicacoes"] = reps
                    descartes.append({"url": (dono.get("url") or "")[:200],
                                      "motivo": f"republicação de {(a.get('url') or '')[:120]}"})
                    finais[finais.index(dono)] = a
                    for j, (conj, item) in enumerate(vistos_titulo):
                        if item is dono:
                            vistos_titulo[j] = (conj, a)
                            break
                    continue
                dono.setdefault("republicacoes", []).append((a.get("url") or "")[:200])
                descartes.append({"url": (a.get("url") or "")[:200],
                                  "motivo": f"republicação de {(dono.get('url') or '')[:120]}"})
                continue
            vistos_titulo.append((tokens, a))
        finais.append(a)
    return finais, descartes


RX_ANO_CITADO = re.compile(r"\b(?:19|20)\d{2}\b")


def _ano_do_item(a: dict):
    dt = _data_do_item(a)
    if dt is not None:
        return dt.year
    # An explicit invalid publication date must not fall back to a title year.
    if any(a.get(k) for k in ("data", "publicado_em", "published_at", "publication_date", "year")) or (a.get("meta") or {}).get("publicado_em"):
        return None
    m = RX_ANO_CITADO.search(a.get("titulo") or "")
    if m:
        from datetime import datetime, timezone
        year = int(m.group(0))
        return year if year <= datetime.now(timezone.utc).year else None
    return None


def _ano_alvo(consulta: str, info: dict):
    """Ano de referência do pedido: ano explícito na consulta ou, em consulta
    temporal sem ano, o ano corrente. Sem pedido temporal: None (nada muda)."""
    m = RX_ANO_CITADO.search(consulta or "")
    if m:
        return int(m.group(0))
    if (info or {}).get("temporal"):
        import datetime as _dt
        return _dt.date.today().year
    return None


def _pontos_relevancia(a: dict, consulta: str, classes: list, info: dict) -> float:
    titulo = (a.get("titulo") or "").lower()
    trecho = (a.get("trecho") or "").lower()
    url = (a.get("url") or "").lower()
    termos = _termos_correspondencia(consulta)
    pagina_de_indice = _pagina_de_indice(a)  # V5.7: índice geral não é conteúdo
    pontos = 0.0
    for t in termos:
        if _tem_termo(t, titulo):
            pontos += 3.0
        if _tem_termo(t, trecho):
            pontos += 1.5
        # URL de índice ecoa a busca (?q=…) — não vale ponto de conteúdo
        if _tem_termo(t, url) and not pagina_de_indice:
            pontos += 1.0
    if not termos:
        pontos += 1.0
    if a.get("fonte_primaria"):
        pontos += 2.0
    peso_prov = float(sp.PROVEDORES.get(a.get("origem", ""), {}).get("peso", 4.0))
    pontos += peso_prov * 0.6
    tipo = a.get("tipo", "")
    if sp.CLASSE_TECNICA in classes and tipo == "tecnico":
        pontos += 3.0
    if sp.CLASSE_ACADEMICA in classes and tipo in ("academico", "saude"):
        pontos += 3.0
    if sp.CLASSE_NOTICIA in classes and tipo == "noticia":
        pontos += 3.0
    if sp.CLASSE_ENCICLOPEDIA in classes and tipo == "enciclopedia":
        pontos += 2.5
    if sp.CLASSE_DADOS in classes and tipo == "dados":
        pontos += 3.0
    if sp.CLASSE_SAUDE in classes and tipo == "saude":
        pontos += 2.5
    if sp.CLASSE_LIVRO in classes and tipo == "livro":
        pontos += 2.0
    # V5.7: página de índice/listagem geral não é conteúdo do assunto —
    # sinalizada e demovida (nunca apagada); fontes primárias sobem.
    if pagina_de_indice:
        a["pagina_de_indice"] = True
        pontos -= 2.0
    alvo = _ano_alvo(consulta, info)
    if alvo is not None:
        # V5.7: conteúdo desatualizado é sinalizado e levemente rebaixado
        # (nunca escondido). Regra única do evidence_graph: sem data
        # conhecida, NÃO acusa.
        ano_item = _ano_do_item(a)
        if ano_item is not None:
            a["ano"] = ano_item
            # Bounded freshness, only for a temporal request and declared publication.
            pontos += max(0.0, 3.0 - max(0, alvo - ano_item))
            velho = eg.fonte_desatualizada({"year": ano_item}, ano_ref=alvo)
            a["desatualizado"] = bool(velho)
            if velho:
                pontos -= min(4.5, (alvo - ano_item) * 1.5)
    host = _dominio(a.get("url", ""))
    if host in ("bing.com", "news.bing.com", "google.com", "news.google.com",
                "duckduckgo.com", "marginalia.nu", "old-search.marginalia.nu",
                "pt.wikipedia.org", "stackoverflow.com", "hn.algolia.com"):
        pontos -= 1.5  # página do próprio provedor não é fonte
    if not (a.get("trecho") or "").strip():
        pontos -= 1.0
    return pontos


def ranquear(achados: list, consulta: str, classes: list, info: dict) -> list:
    for a in achados:
        match = correspondencia_item(a, consulta)
        a["correspondencia_tipo"] = match["tipo"]
        a["cobertura_pedido"] = match["cobertura"]
        a["relevancia"] = round(_pontos_relevancia(a, consulta, classes, info), 2)
        a['relevance_reasons'] = _context_mismatch(a, consulta)
        request=info.get('request')
        if request and request['domain'] in ('news','events','air_travel','bus_travel'):
            import search_verticals
            a['vertical']=search_verticals.assess(request,a)
            a['relevance_reasons'] += a['vertical']['reasons']
    return sorted(achados, key=lambda a: (not _util_para_pedido(a, _termos_correspondencia(consulta), consulta),
        -a.get("relevancia", 0.0), not a.get("fonte_primaria", False)))


def preservar_candidatos(achados: list, consulta: str, limite: int = 12) -> list:
    """Preserve the V5991 reader's opportunities before the discovery cut.

    No second ranker/store or extra reads; feeds/media use remaining slots.
    """
    if len(achados) <= limite:
        return list(achados)
    import research
    prioritized = research.selecionar_candidatos_leitura(achados, consulta, min(6, limite))
    urls = {a.get('url') for a in prioritized}
    return (prioritized + [a for a in achados if a.get('url') not in urls])[:limite]


# ── Lacunas do pedido ──────────────────────────────────────────────
RX_PEDE_NUMERO = re.compile(
    r"\b(quanto|quantos|quantas|preço|preco|valor|custo|taxa|total|número|"
    r"numero|porcentagem|percentual|estatística|estatistica)\b", re.I)
RX_PEDE_DATA = re.compile(
    r"\b(quando|que ano|data|prazo|desde|vigência|vigencia)\b|"
    r"\bat[ée]\s+(?:o\s+ano\s+(?:de\s+)?|os\s+anos\s+)?(?:19|20)\d{2}\b|"
    r"\bat[ée]\s+hoje\b", re.I)  # "até R$ 3000" é teto de preço, não data
RX_PEDE_DEFINICAO = re.compile(r"\b(o que é|o que e|quem é|quem e|define|significado)\b", re.I)


def detectar_lacunas(consulta: str, achados: list, classes: list, info: dict) -> list:
    """O que o pedido exige e as fontes ainda não cobrem (texto explícito)."""
    lacunas = []
    texto = " ".join(((a.get("titulo") or "") + " " + (a.get("trecho") or ""))
                     for a in achados).lower()
    if not achados:
        lacunas.append("nenhuma fonte utilizável")
        return lacunas
    if RX_PEDE_NUMERO.search(consulta or "") and not re.search(r"\d", texto):
        lacunas.append("números/valores pedidos não aparecem nas fontes")
    if RX_PEDE_DATA.search(consulta or "") and not re.search(r"(19|20)\d{2}", texto):
        lacunas.append("datas/anos pedidos não aparecem nas fontes")
    if RX_PEDE_DEFINICAO.search(consulta or "") and not any(
            a.get("tipo") == "enciclopedia" for a in achados):
        lacunas.append("sem fonte enciclopédica direta para a definição")
    if info.get("comparacao"):
        origens = {_dominio(a.get("url", "")) for a in achados}
        if len(origens) < 2:
            lacunas.append("comparação pedida exige mais de uma fonte independente")
    if info.get("produto"):
        if not any(a.get("tipo") == "dados" for a in achados) and \
                not any(re.search(r"r\$\s?\d", (a.get("trecho") or ""), re.I) for a in achados):
            lacunas.append("preço/valor comercial não confirmado por fonte de dados")
    if sp.CLASSE_NOTICIA in classes and not info.get("academica") and not any(a.get("tipo") == "noticia" for a in achados):
        lacunas.append("sem fonte de notícia recente")
    if sp.CLASSE_ACADEMICA in classes and not any(
            a.get("tipo") in ("academico", "saude") for a in achados):
        lacunas.append("sem fonte acadêmica/científica direta")
    return lacunas


def _consultas_recuperacao(consulta: str, classes: list, info: dict, lacunas: list,
                           teto: int = 2) -> list:
    """Consultas complementares para cobrir lacunas — sem mexer no pedido."""
    base = re.sub(r"\s+", " ", (consulta or "").strip())[:160]
    out = []
    for lac in lacunas:
        if "números" in lac or "preço" in lac:
            out.append(f"{base} valor preço número")
        elif "datas" in lac or "notícia" in lac:
            from datetime import datetime, timezone
            year = _ano_alvo(consulta, info) or datetime.now(timezone.utc).year
            out.append(f"{base} {year}")
        elif "enciclopédica" in lac:
            out.append(f"{base} definição")
        elif "independente" in lac:
            out.append(f"{base} comparativo")
        elif "acadêmica" in lac:
            out.append(f"{base} estudo artigo")
        if len(out) >= teto:
            break
    unicos, vistos = [], set()
    for q in out:
        if q.lower() not in vistos and q.lower() != base.lower():
            vistos.add(q.lower())
            unicos.append(q[:200])
    return unicos[:teto]


# ── Execução com orçamento ─────────────────────────────────────────
ORCAMENTO_PADRAO = {"max_consultas": 4, "max_provedores": 6, "timeout_total": 28.0,
                    "min_resultados": 3, "max_por_provedor": 6}


def fontes_preferenciais(consulta: str) -> list:
    t = _sem_acentos(consulta)
    docs = bool(re.search(r"documenta[cç][aã]o|documentation|fontes? (?:oficiais|tecnicas)", t))
    entries = []
    if docs and _tem_termo("asyncio", t):
        specific = bool(re.search(r'\b(taskgroup|cancelamento|cancellation|create_task|gather)\b', t))
        entries.append(("Python asyncio TaskGroup tasks documentation" if specific else "Python asyncio documentation",
                        "https://docs.python.org/3/library/asyncio-task.html" if specific else "https://docs.python.org/3/library/asyncio.html"))
    if docs and _tem_termo("fastapi", t):
        entries.append(("FastAPI documentation", "https://fastapi.tiangolo.com/"))
    if docs and _tem_termo("django", t):
        entries.append(("Django documentation", "https://docs.djangoproject.com/en/stable/"))
    if docs and re.search(r"arquitetura\s+transformer|transformer\s+architecture", t):
        entries.append(("Attention Is All You Need (Transformer)", "https://arxiv.org/abs/1706.03762"))
    sources=[{"titulo": title, "url": url, "trecho": "", "origem": "fonte-primaria",
             "tipo": "tecnico", "fonte_primaria": True, "status": "encontrada"}
            for title, url in entries]
    if re.search(r'\btransformer\b',t) and re.search(r'\b(artigo|paper|original|texto completo)\b',t):
        sources=[s for s in sources if s['url']!='https://arxiv.org/abs/1706.03762']
        sources.append({'titulo':'Attention Is All You Need — Transformer','title':'Attention Is All You Need',
            'url':'https://arxiv.org/abs/1706.03762','landing_url':'https://arxiv.org/abs/1706.03762',
            'pdf_url':'https://arxiv.org/pdf/1706.03762','open_access':True,
            'curated_topic':'Transformer architecture',
            'metadata_source':'academic_provider','content_scope':'metadata_only','full_text_fetched':False,
            'origem':'fonte-primaria','tipo':'academico','fonte_primaria':True,'status':'encontrada',
            'trecho':'Referência bibliográfica curada; texto ainda não recuperado.'})
    return sources


def _escolher_provedores(classes: list, info: dict, disponiveis=None) -> list:
    """Provedores por afinidade; dados/notícias só quando fazem sentido."""
    nomes = []
    ordem = []
    if info.get("academica"):
        ordem.append("crossref")
    if info.get("produto"):
        ordem.extend(["bing", "marginalia"])
    request = info.get('request') or {}
    news_intent = not request or request.get('domain') == 'news' or bool(re.search(
        r'\b(noticias?|manchetes|hoje|ontem|recentes?|ultimas?)\b', _sem_acentos(request.get('original_request', ''))))
    if sp.CLASSE_NOTICIA in classes and not info.get("academica") and news_intent:
        if (info.get('request') or {}).get('domain')=='news':
            ordem.append('google-news')
        ordem.extend(["bing-news", "bing", "hn"])
    if sp.CLASSE_TECNICA in classes:
        ordem.extend(["bing", "ddg", "wikipedia", "stackexchange"] if info.get("documentacao")
                     else ["stackexchange", "hn", "bing"])
    if sp.CLASSE_SAUDE in classes:
        ordem.extend(["pubmed", "wikipedia", "bing"])
    if sp.CLASSE_ACADEMICA in classes:
        # Preserve the legacy classes-only API when no domain context exists.
        ordem.extend(["pubmed", "openlibrary", "wikipedia"] if "academica" not in info
                     else ["pubmed", "wikipedia", "bing"] if sp.CLASSE_SAUDE in classes
                     else ["bing", "ddg", "wikipedia", "marginalia"])
    if sp.CLASSE_DADOS in classes:
        ordem.extend(["worldbank", "bcb", "bing"])
    if sp.CLASSE_LIVRO in classes:
        ordem.extend(["openlibrary", "bing"])
    if sp.CLASSE_IMAGEM in classes:
        ordem.extend(["commons", "bing"])
    if sp.CLASSE_ENCICLOPEDIA in classes:
        ordem.extend(["wikipedia", "bing"])
    ordem.extend(["bing", "ddg", "marginalia", "wikipedia"])
    vistos = set()
    todos = set(disponiveis or sp.disponiveis())
    for nome in ordem:
        if nome in vistos or nome not in todos:
            continue
        vistos.add(nome)
        nomes.append(nome)
    return nomes


def _estado_final(achados: list, falhas: list, vazios: list, consultas: int,
                  correspondencia: float = 1.0) -> str:
    if achados:
        if correspondencia <= 0.15:
            return "sem_correspondencia"
        return "ok" if len(achados) >= 2 else "parcial"
    if consultas == 0:
        return "indisponivel"
    codigos = {f.get("codigo") for f in falhas}
    if codigos and codigos <= {"rede"}:
        return "rede"
    if codigos and codigos <= {"bloqueado", "rate_limited"}:
        return "bloqueado"
    if codigos:
        return "indisponivel"
    return "sem_resultados"


CODIGO_TEXTO = {
    "sem_resultados": "os provedores responderam, mas sem resultados para a consulta",
    "sem_correspondencia": "houve resultados, mas nenhum responde ao pedido",
    "bloqueado": "os provedores consultados recusaram a busca (bot-wall/CAPTCHA)",
    "rede": "falha de rede ao consultar os provedores",
    "indisponivel": "provedores indisponíveis neste momento",
    "parcial": "resposta parcial: poucas fontes utilizáveis",
    "ok": "busca concluída",
}


def pesquisar(consulta: str, *, max_resultados: int = 6, timeout: float = 8.0,
              provedores=None, classes_forcadas=None, orcamento: dict = None,
              extra_queries=None, historico=None) -> dict:
    """Busca orquestrada completa. Nunca levanta por falha de provedor."""
    info = classificar(consulta)
    import query_intelligence
    request_info = query_intelligence.analyze(consulta)
    info["request"] = request_info
    if request_info["domain"] in ("air_travel", "bus_travel", "events", "currency"):
        info["produto"] = False
    if request_info["domain"] == "news":
        info["classes"] = list(dict.fromkeys([sp.CLASSE_NOTICIA] + info["classes"]))
    if classes_forcadas:
        info["classes"] = list(dict.fromkeys(list(classes_forcadas) + info["classes"]))
    orc = dict(ORCAMENTO_PADRAO)
    orc.update(orcamento or {})
    consultas = list(extra_queries or [])
    query = request_info["search_query"] if request_info["requires_live_data"] else consulta
    plan = query_plan(query)
    if not consultas and request_info['domain'] not in ('air_travel', 'bus_travel', 'events', 'currency', 'news'):
        consultas = [row['query'] for row in plan]
    params=request_info['parameters']
    if not consultas and request_info['domain'] in ('air_travel','bus_travel') and params.get('origin') and params.get('destination'):
        # Second query discovers route-specific public pages; exact dates/passengers
        # remain in request and the fare gate, never inferred from a promotion.
        host='clickbus.com.br' if request_info['domain']=='bus_travel' else 'voegol.com.br'
        mode='passagens ônibus' if request_info['domain']=='bus_travel' else 'passagens voos'
        consultas=[f'"{params["origin"]}" "{params["destination"]}" {mode} site:{host}',query]
    for q in variantes(query, info["classes"], teto=3,
                       produto=bool(info.get("produto"))):
        if q not in consultas:
            consultas.append(q)
    consultas = consultas[: max(1, int(orc["max_consultas"]))]
    consultas = list(dict.fromkeys(query_intelligence.constrain_discovery(q, request_info) for q in consultas))
    nomes = list(provedores) if provedores else _escolher_provedores(info["classes"], info)
    nomes = nomes[: max(1, int(orc["max_provedores"]))]

    t0 = time.monotonic()
    achados = fontes_preferenciais(consulta) if provedores is None else []
    etapas, falhas, vazios = [], [], []
    tentativas = list(historico or [])
    feitas = {(x["provedor"], x["consulta"].casefold()) for x in tentativas}
    max_tentativas = max(1, int(orc.get("max_tentativas", int(orc["max_provedores"]) * 2)))

    def _tentar(nome, q):
        key = (nome, q.casefold())
        if key in feitas or len(tentativas) >= max_tentativas:
            return False
        if any(f.get("provedor") == nome and f.get("codigo") in ("bloqueado", "rate_limited") for f in falhas):
            return False
        feitas.add(key)
        tentativas.append({"provedor": nome, "consulta": q})
        return True
    usados = {}
    def remember(items, name, query):
        provenance=query_intelligence.provider_provenance(query,name)
        for item in items:
            item.setdefault('discovery_query', query[:240])
            item.setdefault('discovery_provider', name)
            if provenance:item['retrieval_provenance']=provenance
        before = {canonizar_url(a.get('url', '')) for a in achados}
        achados.extend(items)
        attempt = next((a for a in reversed(tentativas) if a['provedor'] == name and a['consulta'] == query), None)
        if attempt is not None:
            attempt.update(discovered=len(items), new_urls=sum(canonizar_url(a.get('url', '')) not in before for a in items),
                           useful_candidates=sum(_util_para_pedido(a, _termos_correspondencia(consulta), consulta) for a in items),
                           evidence_obtained=0, evidence_scope='discovery_only_requires_reading')
    consultas_feitas = 0
    provedor_indice = 0
    termos_c = _termos_correspondencia(consulta)
    ultimo_ganho = True  # ganho da consulta anterior (parada por ganho zero)

    def _uteis() -> int:
        return sum(1 for a in achados if a.get('content_scope') != 'feed_metadata' and _util_para_pedido(a, termos_c, consulta))

    def _retry_com_conteudo(nome: str, q_atual: str) -> bool:
        """Mesma fonte, consulta reformulada (pergunta → conteúdo); 1x por fonte.

        True só quando a reformulada trouxe resultado que responde ao pedido.
        """
        alt = next((p['query'] for p in plan if p['type'] == 'ENTITY_EXACT' and p['query'].casefold() != q_atual.casefold()
                    and (nome, p['query'].casefold()) not in feitas), '') or consulta_conteudo(q_atual)
        if not alt or alt.lower() == (q_atual or "").strip().lower():
            return False
        q_prov = termos_para_provedor(alt, "tecnico" if info["tecnica"]
                                      and nome in ("stackexchange", "hn") else "")
        q_prov = query_intelligence.constrain_provider_query(q_prov)
        restante = float(orc["timeout_total"]) - (time.monotonic() - t0)
        if restante <= 0 or not _tentar(nome, q_prov):
            return False
        try:
            novos = sp.buscar(nome, q_prov,
                              limite=max(2, min(int(orc["max_por_provedor"]),
                                                max_resultados)),
                              timeout=min(timeout, restante))
        except Exception as exc:
            falhas.append({"provedor": nome, "codigo": getattr(exc, "codigo", type(exc).__name__),
                           **({"http": exc.http, "categoria": exc.categoria} if hasattr(exc, "categoria") else {})})
            return False
        usados[nome] = usados.get(nome, 0) + 1
        etapas.append(f"{nome} (consulta reformulada '{alt[:40]}'): "
                      f"{len(novos)} resultados")
        remember(novos, nome, q_prov)
        return bool(novos) and any(_util_para_pedido(a, termos_c, consulta) for a in novos)

    for i, q in enumerate(consultas):
        if _uteis() >= int(orc["min_resultados"]) and i > 0:
            break
        if i > 0 and not ultimo_ganho and _uteis() >= 1:
            # V5.7: parada por ganho real — a consulta anterior não trouxe
            # domínio nem tema novo; insistir só gastaria orçamento.
            etapas.append("parada por ganho zero: consulta anterior sem "
                          "domínio nem tema novo")
            break
        if time.monotonic() - t0 > float(orc["timeout_total"]):
            etapas.append("orçamento de tempo esgotado")
            break
        consultas_feitas += 1
        retrato_antes = _retrato(achados, consulta)
        tentativa_provedor = 0
        while tentativa_provedor < 3 and provedor_indice < len(nomes):
            restante = float(orc["timeout_total"]) - (time.monotonic() - t0)
            if restante <= 0:
                etapas.append("orçamento de tempo esgotado durante fallback")
                break
            nome = nomes[provedor_indice]
            consulta_prov = termos_para_provedor(q, "tecnico" if info["tecnica"]
                                                 and nome in ("stackexchange", "hn") else "")
            consulta_prov = query_intelligence.constrain_provider_query(consulta_prov)
            if not _tentar(nome, consulta_prov):
                provedor_indice += 1
                tentativa_provedor += 1
                continue
            try:
                achados_novos = sp.buscar(nome, consulta_prov,
                                          limite=max(2, min(int(orc["max_por_provedor"]),
                                                            max_resultados)),
                                          timeout=min(timeout, restante))
                usados[nome] = usados.get(nome, 0) + 1
                etapas.append(f"{nome}: {len(achados_novos)} resultados "
                              f"({q[:40]})")
                remember(achados_novos, nome, consulta_prov)
                if achados_novos and all(a.get('content_scope') == 'feed_metadata' for a in achados_novos):
                    etapas.append(f'{nome}: RSS apenas para descoberta; procurando artigos originais')
                    provedor_indice += 1
                    tentativa_provedor += 1
                    continue
                if achados_novos and termos_c and not any(
                        _util_para_pedido(a, termos_c, consulta) for a in achados_novos):
                    # resultados existem, mas nenhum responde ao pedido:
                    # 1º tenta a MESMA fonte com a consulta reformulada
                    # (ex.: "como funciona o freio ABS" → "freio ABS");
                    if _retry_com_conteudo(nome, q):
                        provedor_indice += 1
                        break
                    # 2º segue para o próximo provedor em vez de encerrar aqui
                    etapas.append(f"{nome}: sem correspondência com o pedido; "
                                  f"tentando outro provedor ({q[:40]})")
                    provedor_indice += 1
                    tentativa_provedor += 1
                    continue
                provedor_indice += 1
                break
            except sp.ErroProvedor as exc:
                if exc.codigo in ("vazio", "sem_resultados"):
                    # vazio: 1 tentativa com a consulta reformulada antes de
                    # registrar "sem resultados" (Wikipedia devolve nada para
                    # "o que é X" mas acha o verbete para "X")
                    if _retry_com_conteudo(nome, q):
                        provedor_indice += 1
                        break
                    vazios.append(nome)
                    etapas.append(f"{nome}: sem resultados ({q[:40]})")
                else:
                    falhas.append({"provedor": nome, "codigo": exc.codigo,
                                   **({"http": exc.http, "categoria": exc.categoria} if hasattr(exc, "categoria") else {})})
                    etapas.append(f"{nome}: {exc.codigo} ({q[:40]})")
                provedor_indice += 1
                tentativa_provedor += 1
                continue
            except Exception as exc:  # blindagem: nenhum provedor derruba a busca
                falhas.append({"provedor": nome, "codigo": type(exc).__name__})
                etapas.append(f"{nome}: falha inesperada ({type(exc).__name__})")
                provedor_indice += 1
                tentativa_provedor += 1
                continue
        # V5.7: ganho real da consulta (domínios/temas novos) alimenta a
        # parada por ganho zero na próxima volta
        ultimo_ganho = _ganho_informacao(retrato_antes, achados,
                                         consulta)["ganho_real"]
        if provedor_indice >= len(nomes):
            break

    # A feed is a lead, not an article. Spend at most two existing attempt
    # slots on a specific headline at its declared publisher, never an opaque
    # aggregator decoding endpoint or a bypass. All ordinary budgets still apply.
    if request_info['domain'] == 'news' and _uteis() < int(orc['min_resultados']):
        # Incomplete feed metadata is not proof that the original is irrelevant.
        feeds = sorted([a for a in achados if a.get('content_scope') == 'feed_metadata'],
                       key=lambda a:not _util_para_pedido(a,termos_c,consulta))[:2]
        for feed in feeds:
            publisher = urllib.parse.urlsplit(feed.get('publisher_url') or '').hostname or ''
            title = str(feed.get('titulo') or '').strip()
            label = str(feed.get('publicador') or '').strip()
            if label and title.endswith(' - ' + label):
                title = title[:-(len(label) + 3)]
            if len(title) < 20 or not re.fullmatch(r'[a-zA-Z0-9.-]+', publisher):
                continue
            q_original = f'"{title[:180]}" site:{publisher}'
            q_original = query_intelligence.constrain_provider_query(q_original)
            # Spend the same attempt slots on declared publisher links/feeds
            # before another search response that may only repeat the aggregator.
            def fetch_publisher(url, kind):
                remaining = float(orc['timeout_total']) - (time.monotonic()-t0)
                if remaining<=0 or not _tentar('publisher-feed',url):
                    raise sp.ErroProvedor('Publisher recovery budget exhausted','orcamento')
                return sp._baixar(url,min(timeout,remaining),aceitar=kind)
            try:
                originals=sp.recuperar_feed_publicador(feed,fetch_publisher)
                remember(originals, 'publisher-feed', q_original)
                etapas.append(f'RSS do publicador: {len(originals)} artigo(s) candidato(s), leitura pendente')
            except (sp.ErroProvedor, ValueError) as exc:
                etapas.append('Recuperação no publicador limitada: '+str(getattr(exc,'codigo',type(exc).__name__)))
            if any(a.get('source_recovery',{}).get('publisher_url')==feed.get('publisher_url') for a in achados):
                continue
            for name in [n for n in nomes if n in ('bing', 'ddg', 'marginalia')][:2]:
                remaining = float(orc['timeout_total']) - (time.monotonic() - t0)
                if remaining <= 0 or not _tentar(name, q_original):
                    continue
                try:
                    candidates = sp.buscar(name, q_original, limite=3, timeout=min(timeout, remaining))
                except sp.ErroProvedor as exc:
                    falhas.append({'provedor': name, 'codigo': exc.codigo})
                    continue
                usados[name] = usados.get(name, 0) + 1
                terms = set(_termos(title))
                recovered = []
                for candidate in candidates:
                    host = urllib.parse.urlsplit(candidate.get('url') or '').hostname or ''
                    overlap = len(terms & set(_termos(candidate.get('titulo') or ''))) / max(1, len(terms))
                    if (host == publisher or host.endswith('.' + publisher)) and overlap >= 0.6:
                        candidate['source_recovery'] = {'method':'headline_publisher_search',
                            'feed_url':feed.get('url',''), 'publisher_url':feed.get('publisher_url',''),
                            'feed_title':feed.get('titulo',''), 'state':'original_candidate'}
                        recovered.append(candidate)
                remember(recovered, name, q_original)
                etapas.append(f'{name}: recuperação de manchete no publicador; {len(recovered)} candidato(s), leitura pendente')
                break

    unicos, descartes = deduplicar(achados)
    ranqueados = ranquear(unicos, consulta, info["classes"], info)
    # V5.7: rodada dominada por páginas de índice geral → o resultado é
    # reclassificado (páginas sinalizadas/demovidas, nunca apagadas) e a
    # recuperação pede o assunto direto (fontes primárias não alcançadas).
    indice_geral = [a.get("url") for a in ranqueados if a.get("pagina_de_indice")]
    so_indice = bool(ranqueados) and all(
        a.get("pagina_de_indice") for a in ranqueados[:5])
    if so_indice:
        etapas.append(f"1ª rodada só com páginas de índice geral "
                      f"({len(indice_geral)} sinalizada(s)); fontes primárias "
                      f"não alcançadas")
    # correspondência: fração dos termos do pedido presentes nos melhores
    # (só termos que provam correspondência; genéricos de loja não contam)
    correspondencia = _correspondencia(ranqueados, termos_c)
    lacunas = detectar_lacunas(consulta, ranqueados, info["classes"], info)
    if so_indice:
        lacunas.append("primeira rodada só com páginas de índice geral")
    estado = _estado_final(ranqueados, falhas, vazios, consultas_feitas, correspondencia)
    sem_assunto = bool(ranqueados) and not any(_util_para_pedido(a, termos_c, consulta) for a in ranqueados)
    if sem_assunto:
        estado = 'sem_correspondencia'
        lacunas.append('nenhum candidato confirma assunto e restrições do pedido')
    recuperacao = _consultas_recuperacao(consulta, info["classes"], info, lacunas)
    if sem_assunto:
        for p in reversed(plan):
            if p['type'] == 'ENTITY_EXACT' and p['query'] not in recuperacao:
                recuperacao.insert(0, p['query'])
    # V5.7: enxuta também quando a correspondência é fraca (não só quando é
    # nula) ou quando a rodada foi só de índices — cobre o caso em que só um
    # termo funcional ("funciona") casou.
    if (correspondencia < 0.5 or so_indice) and len(termos_c) >= 2:
        # consulta enxuta: todos os termos distintivos do pedido, sem os
        # genéricos que fazem índices gerais devolverem lixo; nada é
        # acrescentado nem removido do pedido (números e nomes intactos)
        enxuta = " ".join(termos_c)[:200]
        if enxuta.lower() != (consulta or "").strip().lower() and enxuta not in recuperacao:
            recuperacao.insert(0, enxuta)
    from research import candidate_report
    return {
        'query_plan': plan,
        "tentativas_busca": tentativas,
        "achados": preservar_candidatos(ranqueados, consulta, max(6, max_resultados * 2)),
        "candidate_reservoir": candidate_report(achados, ranqueados, consulta),
        "etapas": etapas,
        "estado": estado,
        "estado_texto": CODIGO_TEXTO.get(estado, ""),
        "provedores": {"usados": usados, "falhas": falhas, "vazios": vazios,
                       "consultados": list(dict.fromkeys(x["provedor"] for x in tentativas))},
        "classes": info["classes"],
        "temporal": bool(info.get("temporal")),
        "desatualizados": [a.get("url") for a in ranqueados if a.get("desatualizado")],
        "indice_geral": indice_geral,
        "lacunas": lacunas,
        "consultas": consultas[:consultas_feitas],
        "recuperacao": recuperacao,
        "descartes": descartes[:20],
        "correspondencia": correspondencia,
        "segundos": round(time.monotonic() - t0, 2),
    }


def pesquisar_com_recuperacao(consulta: str, *, max_resultados: int = 6,
                              timeout: float = 8.0, orcamento: dict = None,
                              limite_primeira: float = None) -> dict:
    """Busca + uma rodada de recuperação quando o resultado não cobre o pedido.

    `limite_primeira`: quando a 1ª rodada já gastou esse tempo (s), a
    recuperação é adiada (honesto: `recuperou=False` + motivo declarado).
    """
    res = pesquisar(consulta, max_resultados=max_resultados, timeout=timeout,
                    orcamento=orcamento)
    precisa = (res.get("estado") in ("sem_resultados", "sem_correspondencia", "bloqueado")
               or len(res.get("achados", [])) < 3
               or bool(res.get("lacunas"))
               # V5.7: correspondência fraca também investiga (nunca fingir ok)
               or float(res.get("correspondencia", 1.0)) < 0.5)
    if not precisa or not res.get("recuperacao"):
        res["recuperou"] = False
        return res
    if limite_primeira is not None and float(res.get("segundos", 0.0)) > float(limite_primeira):
        res["recuperou"] = False
        res["recuperacao_adiada"] = ("primeira rodada já consumiu o tempo disponível; "
                                     "lacunas declaradas acima")
        return res
    orc2 = dict(ORCAMENTO_PADRAO)
    orc2.update(orcamento or {})
    restante = float(orc2["timeout_total"]) - float(res.get("segundos", 0))
    # max_consultas is the legacy per-round limit. The total is explicit and
    # bounded across the original round plus at most one recovery round.
    max_total = int(orc2.get("max_consultas_total", 2 * int(orc2["max_consultas"])))
    consultas_restantes = max_total - len(res.get("consultas", []))
    if restante <= 0 or consultas_restantes <= 0:
        res["recuperou"] = False
        res["recuperacao_adiada"] = "orçamento total de tempo/consultas esgotado"
        return res
    orc2["timeout_total"] = restante
    orc2["max_consultas"] = min(int(orc2["max_consultas"]), consultas_restantes)
    blocked = {f.get("provedor") for f in res.get("provedores", {}).get("falhas", [])
               if f.get("codigo") in ("bloqueado", "rate_limited")}
    saudaveis = [p for p in _escolher_provedores(res.get("classes", []), classificar(consulta)) if p not in blocked]
    if not saudaveis:
        res["recuperou"] = False
        res["recuperacao_adiada"] = "nenhum provedor disponível sem bloqueio"
        return res
    retrato_1 = _retrato(res.get("achados", []), consulta)
    extra = pesquisar(consulta, max_resultados=max_resultados, timeout=timeout,
                      orcamento=orc2, extra_queries=res["recuperacao"],
                      provedores=saudaveis, historico=res.get("tentativas_busca", []))
    # merge honesto: marca a rodada de recuperação nas etapas
    res["etapas"] = (res.get("etapas", []) + ["— recuperação por lacuna —"]
                     + extra.get("etapas", []))
    merged = ranquear(
        deduplicar(res.get("achados", []) + extra.get("achados", []))[0],
        consulta, res.get("classes", []),
        {"temporal": bool(res.get("temporal"))})
    res["achados"] = merged
    res["consultas"] = list(dict.fromkeys(res.get("consultas", []) + extra.get("consultas", [])))
    res["tentativas_busca"] = extra.get("tentativas_busca", res.get("tentativas_busca", []))
    original_p, extra_p = res.get("provedores", {}), extra.get("provedores", {})
    used = dict(original_p.get("usados", {}))
    for name, count in extra_p.get("usados", {}).items():
        used[name] = used.get(name, 0) + count
    res["provedores"] = {"usados": used,
        "falhas": original_p.get("falhas", []) + extra_p.get("falhas", []),
        "vazios": list(dict.fromkeys(original_p.get("vazios", []) + extra_p.get("vazios", []))),
        "consultados": list(dict.fromkeys(original_p.get("consultados", []) + extra_p.get("consultados", [])))}
    res["desatualizados"] = [a.get("url") for a in merged if a.get("desatualizado")]
    res["indice_geral"] = [a.get("url") for a in merged if a.get("pagina_de_indice")]
    res["descartes"] = (res.get("descartes", []) + extra.get("descartes", []))[:20]
    res["lacunas"] = extra.get("lacunas", res.get("lacunas", []))
    # estado/correspondência recalculados sobre o resultado final (honesto:
    # a rodada de recuperação não "conserta" correspondência que não existe)
    termos_c = _termos_correspondencia(consulta)
    res["correspondencia"] = _correspondencia(merged, termos_c)
    if not merged:
        res["estado"] = extra.get("estado", res.get("estado", "sem_resultados"))
    elif res["correspondencia"] <= 0.15 and termos_c:
        res["estado"] = "sem_correspondencia"
    else:
        res["estado"] = "ok" if len(merged) >= 2 else "parcial"
    res["estado_texto"] = CODIGO_TEXTO.get(res["estado"], "")
    # V5.7: ganho real da recuperação é medido e declarado — nunca fingir
    # melhora só porque a rodada rodou (quantidade ≠ informação nova)
    ganho = _ganho_informacao(retrato_1, merged, consulta)
    res["ganho_informacao"] = ganho
    if ganho["ganho_real"]:
        res["etapas"].append(
            f"recuperação com ganho novo: {len(ganho['dominios_novos'])} domínio(s), "
            f"{len(ganho['temas_novos'])} tema(s) além da 1ª rodada")
    else:
        res["etapas"].append("recuperação sem ganho novo: nenhum domínio/tema "
                             "além da 1ª rodada")
    res["segundos"] = round(res.get("segundos", 0.0) + extra.get("segundos", 0.0), 2)
    res["recuperou"] = True
    return res
