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

# ── Classes de assunto ─────────────────────────────────────────────
RX_TECNICO = re.compile(
    r"\b(python|javascript|typescript|java|c\+\+|c#|rust|golang|sql|api|sdk|"
    r"docker|kubernetes|linux|windows|android|ios|react|node|django|fastapi|"
    r"erro|bug|exceção|exception|stack ?trace|compile|compilar|instalar|"
    r"configurar|regex|algoritmo|banco de dados|sqlite|postgres|mysql|git|"
    r"servidor|deploy|json|xml|csv|html|css|criptografia|hash|token)\b", re.I)
RX_ACADEMICO = re.compile(
    r"\b(artigo|paper|estudo|pesquisa científica|tese|dissertação|doi|"
    r"revisão sistemática|meta-?análise|pubmed|scopus|openalex|crossref|"
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
    r"\b(comparar|comparação|comparacao|versus|\bvs\b|diferença|diferenca|"
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
}


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower())
                   if not unicodedata.combining(c))


def _termos(texto: str, minimo: int = 3) -> list:
    return [t for t in re.findall(r"[0-9a-zà-ú][0-9a-zà-ú\-\+\.]*", (texto or "").lower())
            if len(t) >= minimo and t not in _ESTOPO]


def _termos_correspondencia(consulta: str) -> list:
    """Termos do pedido que provam correspondência (sem genéricos de loja)."""
    return [t for t in _termos(consulta) if t not in _GENERICOS_CORRESPONDENCIA]


def _util_para_pedido(a: dict, termos: list) -> bool:
    """O achado responde ao pedido? (menciona algum termo não-genérico).

    Sem termos aproveitáveis no pedido, todo achado conta como útil —
    não há como distinguir correspondência melhor.
    """
    if not termos:
        return True
    texto = ((a.get("titulo") or "") + " " + (a.get("trecho") or "")).lower()
    return any(t in texto for t in termos)


def _correspondencia(achados: list, termos: list) -> float:
    """Fração dos termos (não-genéricos) presentes nos melhores achados."""
    topo = (achados or [])[:8]
    if not topo:
        return 0.0
    if not termos:
        return 1.0
    juntos = " ".join(((a.get("titulo") or "") + " " + (a.get("trecho") or "")).lower()
                      for a in topo)
    return round(sum(1 for t in termos if t in juntos) / len(termos), 3)


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
            "academica": sp.CLASSE_ACADEMICA in classes}


# ── Consultas alternativas e complementares ────────────────────────
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


def deduplicar(achados: list) -> tuple:
    """Agrupa por URL canônica. Retorna (únicos, descartes)."""
    vistos, unicos, descartes = {}, [], []
    for a in achados or []:
        url = (a.get("url") or "").strip()
        chave = canonizar_url(url)
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
    return unicos, descartes


def _pontos_relevancia(a: dict, consulta: str, classes: list, info: dict) -> float:
    titulo = (a.get("titulo") or "").lower()
    trecho = (a.get("trecho") or "").lower()
    url = (a.get("url") or "").lower()
    termos = _termos(consulta)
    pontos = 0.0
    for t in termos:
        if t in titulo:
            pontos += 3.0
        if t in trecho:
            pontos += 1.5
        if t in url:
            pontos += 1.0
    if not termos:
        pontos += 1.0
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
    if info.get("temporal"):
        ano = re.search(r"\b(20\d{2})\b", titulo + " " + trecho)
        if ano:
            try:
                pontos += max(0, min(3.0, (int(ano.group(1)) - 2015) * 0.3))
            except ValueError:
                pass
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
        a["relevancia"] = round(_pontos_relevancia(a, consulta, classes, info), 2)
    return sorted(achados, key=lambda a: -a.get("relevancia", 0.0))


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
    if sp.CLASSE_NOTICIA in classes and not any(a.get("tipo") == "noticia" for a in achados):
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
            out.append(f"{base} 2026")
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


def _escolher_provedores(classes: list, info: dict, disponiveis=None) -> list:
    """Provedores por afinidade; dados/notícias só quando fazem sentido."""
    nomes = []
    ordem = []
    if info.get("produto"):
        ordem.extend(["bing", "marginalia"])
    if sp.CLASSE_NOTICIA in classes:
        ordem.extend(["bing-news", "bing", "hn"])
    if sp.CLASSE_TECNICA in classes:
        ordem.extend(["stackexchange", "hn", "bing"])
    if sp.CLASSE_SAUDE in classes:
        ordem.extend(["pubmed", "wikipedia", "bing"])
    if sp.CLASSE_ACADEMICA in classes:
        ordem.extend(["pubmed", "openlibrary", "wikipedia"])
    if sp.CLASSE_DADOS in classes:
        ordem.extend(["worldbank", "bcb", "bing"])
    if sp.CLASSE_LIVRO in classes:
        ordem.extend(["openlibrary", "bing"])
    if sp.CLASSE_IMAGEM in classes:
        ordem.extend(["commons", "bing"])
    if sp.CLASSE_ENCICLOPEDIA in classes:
        ordem.extend(["wikipedia", "bing"])
    ordem.extend(["bing", "marginalia", "wikipedia"])
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
    if codigos and codigos <= {"bloqueado"}:
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
              extra_queries=None) -> dict:
    """Busca orquestrada completa. Nunca levanta por falha de provedor."""
    info = classificar(consulta)
    if classes_forcadas:
        info["classes"] = list(dict.fromkeys(list(classes_forcadas) + info["classes"]))
    orc = dict(ORCAMENTO_PADRAO)
    orc.update(orcamento or {})
    consultas = list(extra_queries or [])
    for q in variantes(consulta, info["classes"], teto=3,
                       produto=bool(info.get("produto"))):
        if q not in consultas:
            consultas.append(q)
    consultas = consultas[: max(1, int(orc["max_consultas"]))]
    nomes = list(provedores) if provedores else _escolher_provedores(info["classes"], info)
    nomes = nomes[: max(1, int(orc["max_provedores"]))]

    t0 = time.monotonic()
    achados, etapas, falhas, vazios = [], [], [], []
    usados = {}
    consultas_feitas = 0
    provedor_indice = 0
    termos_c = _termos_correspondencia(consulta)

    def _uteis() -> int:
        return sum(1 for a in achados if _util_para_pedido(a, termos_c))

    def _retry_com_conteudo(nome: str, q_atual: str) -> bool:
        """Mesma fonte, consulta reformulada (pergunta → conteúdo); 1x por fonte.

        True só quando a reformulada trouxe resultado que responde ao pedido.
        """
        alt = consulta_conteudo(q_atual)
        if not alt or alt.lower() == (q_atual or "").strip().lower():
            return False
        q_prov = termos_para_provedor(alt, "tecnico" if info["tecnica"]
                                      and nome in ("stackexchange", "hn") else "")
        try:
            novos = sp.buscar(nome, q_prov,
                              limite=max(2, min(int(orc["max_por_provedor"]),
                                                max_resultados)),
                              timeout=timeout)
        except Exception:
            return False
        usados[nome] = usados.get(nome, 0) + 1
        etapas.append(f"{nome} (consulta reformulada '{alt[:40]}'): "
                      f"{len(novos)} resultados")
        achados.extend(novos)
        return bool(novos) and any(_util_para_pedido(a, termos_c) for a in novos)

    for i, q in enumerate(consultas):
        if _uteis() >= int(orc["min_resultados"]) and i > 0:
            break
        if time.monotonic() - t0 > float(orc["timeout_total"]):
            etapas.append("orçamento de tempo esgotado")
            break
        consultas_feitas += 1
        tentativa_provedor = 0
        while tentativa_provedor < 3 and provedor_indice < len(nomes):
            nome = nomes[provedor_indice]
            consulta_prov = termos_para_provedor(q, "tecnico" if info["tecnica"]
                                                 and nome in ("stackexchange", "hn") else "")
            try:
                achados_novos = sp.buscar(nome, consulta_prov,
                                          limite=max(2, min(int(orc["max_por_provedor"]),
                                                            max_resultados)),
                                          timeout=timeout)
                usados[nome] = usados.get(nome, 0) + 1
                etapas.append(f"{nome}: {len(achados_novos)} resultados "
                              f"({q[:40]})")
                achados.extend(achados_novos)
                if achados_novos and termos_c and not any(
                        _util_para_pedido(a, termos_c) for a in achados_novos):
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
                    falhas.append({"provedor": nome, "codigo": exc.codigo})
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
        if provedor_indice >= len(nomes) and _uteis() >= int(orc["min_resultados"]):
            break

    unicos, descartes = deduplicar(achados)
    ranqueados = ranquear(unicos, consulta, info["classes"], info)
    # correspondência: fração dos termos do pedido presentes nos melhores
    # (só termos que provam correspondência; genéricos de loja não contam)
    correspondencia = _correspondencia(ranqueados, termos_c)
    lacunas = detectar_lacunas(consulta, ranqueados, info["classes"], info)
    estado = _estado_final(ranqueados, falhas, vazios, consultas_feitas, correspondencia)
    recuperacao = _consultas_recuperacao(consulta, info["classes"], info, lacunas)
    # V5.7: enxuta também quando a correspondência é fraca (não só quando é
    # nula) — cobre o caso em que só um termo funcional ("funciona") casou.
    if correspondencia < 0.5 and len(termos_c) >= 2:
        # consulta enxuta: todos os termos distintivos do pedido, sem os
        # genéricos que fazem índices gerais devolverem lixo; nada é
        # acrescentado nem removido do pedido (números e nomes intactos)
        enxuta = " ".join(termos_c)[:200]
        if enxuta.lower() != (consulta or "").strip().lower() and enxuta not in recuperacao:
            recuperacao.insert(0, enxuta)
    return {
        "achados": ranqueados[:max(6, max_resultados * 2)],
        "etapas": etapas,
        "estado": estado,
        "estado_texto": CODIGO_TEXTO.get(estado, ""),
        "provedores": {"usados": usados, "falhas": falhas, "vazios": vazios,
                       "consultados": nomes[: max(1, provedor_indice)]},
        "classes": info["classes"],
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
    orc2["max_consultas"] = max(1, int(orc2.get("max_consultas", 4)) - len(res["consultas"]))
    if orc2["max_consultas"] < 1:
        orc2["max_consultas"] = 1
    extra = pesquisar(consulta, max_resultados=max_resultados, timeout=timeout,
                      orcamento=orc2, extra_queries=res["recuperacao"])
    # merge honesto: marca a rodada de recuperação nas etapas
    res["etapas"] = (res.get("etapas", []) + ["— recuperação por lacuna —"]
                     + extra.get("etapas", []))
    merged = ranquear(
        deduplicar(res.get("achados", []) + extra.get("achados", []))[0],
        consulta, res.get("classes", []), {"temporal": False})
    res["achados"] = merged
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
    res["segundos"] = round(res.get("segundos", 0.0) + extra.get("segundos", 0.0), 2)
    res["recuperou"] = True
    return res
