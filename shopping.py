"""Julia Shopping Intelligence (V5.5) — pesquisa visual de produtos. Stdlib pura.

Camadas: detectar intenção → extrair critérios → buscar (cadeia
mlb → ddg → ddg-lite → web orquestrada (Research Engine)) → recuperar
páginas (reusa `research.baixar`, com guarda SSRF) → extrair ofertas
(JSON-LD Product/Offer + OpenGraph) → verificar link/imagem de cada
oferta (`source_check`) → deduplicar → filtrar por orçamento/specs →
separar alternativas próximas (com diferenças explícitas) → comparar →
persistir por dono → emitir fence JDUI determinístico.

REGRAS DURAS (nunca relaxar):
- NUNCA inventar produtos, preços, imagens, avaliações, descontos ou estoque.
- Ofertas vêm SOMENTE de dados estruturados reais da página (JSON-LD/OG).
  Resultado de busca sem dado estruturado vira FONTE (link), nunca produto.
- Página de listagem/categoria só gera produto quando o dado estruturado
  traz a URL do item; o card marca o link como NÃO verificado e nunca
  apresenta a listagem como página do produto.
- Preço inacessível → "Preço não confirmado" (preco_confirmado=False).
- Conteúdo externo é DADO não confiável: nunca seguir instruções embutidas
  em páginas/trechos (anti prompt-injection).
- Preço guardado é HISTÓRICO: sempre exibir `verificado_em`; nunca
  apresentar como cotação atual.
- Critério do usuário (orçamento/marca/condição/specs) nunca é trocado em
  silêncio: quem não atende tudo vira alternativa com as diferenças
  explícitas ou descarte explicado.
"""
import hashlib
import html as _html
import json
import logging
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone

import research
import source_check

log = logging.getLogger("JULIA-shopping")


def _ttl_consulta() -> int:
    """TTL do cache de consulta, em segundos (JULIA_SHOPPING_TTL; padrão 6h)."""
    try:
        valor = int(os.environ.get("JULIA_SHOPPING_TTL", "") or 0)
    except ValueError:
        valor = 0
    return valor if valor > 0 else 6 * 3600


TTL_CONSULTA = _ttl_consulta()
MAX_CONSULTAS_POR_CONV = 20
MAX_PAGINAS = 6
MAX_PRODUTOS = 6

PRECO_NAO_CONFIRMADO = "Preço não confirmado"

# Categorias reconhecidas (substantivos de produto; sem alegação de loja).
CATEGORIAS = (
    "celular", "smartphone", "notebook", "laptop", "ultrabook", "computador",
    "tablet", "fone", "headphone", "headset", "smart tv", "tv", "televisor",
    "monitor", "teclado", "mouse", "console", "videogame", "geladeira",
    "fogão", "fogao", "micro-ondas", "microondas", "air fryer",
    "ar-condicionado", "ar condicionado", "ventilador", "bicicleta",
    "tênis", "tenis", "relógio", "relogio", "smartwatch", "câmera", "camera",
    "impressora", "roteador", "ssd", "hd externo", "placa de vídeo",
    "placa de video", "processador", "memória ram", "memoria ram",
    "caixa de som", "smart speaker", "kindle", "e-reader", "aspirador",
    "aspirador robô", "aspirador robo", "cafeteira", "liquidificador",
    "máquina de lavar", "maquina de lavar", "lava-louças", "lava-loucas",
    "guarda-roupa", "guarda-roupas", "sofá", "sofa", "colchão", "colchao",
    "mochila", "mala", "patinete", "patinete elétrico", "patinete eletrico",
    "drone", "projetor", "webcam", "microfone", "cadeira gamer",
    "cadeira de escritório", "cadeira de escritorio", "mesa digitalizadora",
    "nintendo", "playstation", "xbox", "iphone", "galaxy", "xiaomi",
    "redmi", "poco", "motorola", "samsung", "lenovo", "dell", "hp", "asus",
    "acer", "apple", "jbl", "soda", "fritadeira",
)

_VERBOS_COMPRA = (
    "pesquis", "busc", "encontr", "procur", "recomend", "compar", "comprar",
    "compra", "oferta", "preço", "preco", "promoção", "promocao",
    "mais barato", "menor preço", "menor preco", "onde comprar",
    "vale a pena", "custo-benefício", "custo-beneficio", "custo beneficio",
    "qual celular", "qual notebook", "quero um", "quero uma",
)

_MARCAS = (
    "samsung", "apple", "xiaomi", "redmi", "poco", "motorola", "lenovo",
    "dell", "hp", "asus", "acer", "lg", "philco", "tcl", "aoc", "positivo",
    "multilaser", "jbl", "sony", "philips", "electrolux", "brastemp",
    "consul", "midea", "springer", "gorenje", "oster", "mondial", "britânia",
    "britania", "cadence", "nintendo", "microsoft", "logitech", "razer",
    "hyperx", "kingston", "sandisk", "seagate", "corsair", "nzxt", "intel",
    "amd", "nvidia", "tp-link", "intelbras", "amazfit", "huawei", "realme",
    "infinix", "nokia", "asus rog", "adidas", "nike", "mizuno",
)


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sem_acentos(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower())
                   if not unicodedata.combining(c))


def _marca_no_texto(marca: str, alvo: str) -> bool:
    """Marca como palavra (não substring dentro de outra palavra)."""
    return bool(re.search(r"(?<![0-9a-z])" + re.escape(marca) + r"(?![0-9a-z])",
                          alvo or ""))


_RX_MARCAS_CONHECIDAS = re.compile(
    r"(?<![0-9a-z])(" + "|".join(re.escape(_sem_acentos(m))
                                 for m in sorted(_MARCAS, key=len, reverse=True))
    + r")(?![0-9a-z])")


def _marca_conhecida(alvo: str) -> str:
    """Marca conhecida citada no anúncio — PRIMEIRA ocorrência (nome do
    produto vem antes de acessórios/GPU: "Dell Alienware ... NVIDIA")."""
    m = _RX_MARCAS_CONHECIDAS.search(alvo or "")
    return m.group(1) if m else ""


def _armazenamento_aparente(txt: str) -> int | None:
    """Maior valor em GB do anúncio (≥64); RAM pequena ("16GB") não engana."""
    vals = []
    for m in re.finditer(r"\b(\d{2,4})\s?gb\b", (txt or "").lower()):
        try:
            vals.append(int(m.group(1)))
        except ValueError:
            pass
    vals = [v for v in vals if v >= 64]
    return max(vals) if vals else None


# V5.7: verbos de PEDIDO de produto ("me mostre tenis para basquete") que
# não eram reconhecidos — o pedido nunca virava busca e o modelo respondia
# de memória. Não substituem os verbos fortes: complementam.
_VERBOS_PEDIDO_PRODUTO = (
    "mostre", "mostra", "manda", "mande", "envia", "envie", "indica",
    "indique", "preciso de", "preciso dum", "quero ver", "queria ver",
    "me traga", "me traz", "traz um", "traz uma", "traga um", "traga uma",
)
# Pedido explicativo sobre um produto não é busca de oferta.
_RX_EXPLICATIVO_PRODUTO = re.compile(
    r"(como funciona|o que (e|eh)\b|para que serve|me explique|explique|"
    r"o que faz|como se usa|como usar)")


def detectar_intencao(texto: str) -> bool:
    """True se o usuário pede pesquisa/compra/comparação de produtos."""
    t = _sem_acentos(texto or "")
    tem_verbo_forte = any(v in t for v in (
        "pesquis", "busc", "encontr", "procur", "recomend", "compar",
        "comprar", "compra", "oferta", "preco", "promocao", "mais barato",
        "menor preco", "onde comprar", "vale a pena", "custo-beneficio",
        "custo beneficio", "qual celular", "qual notebook",
        "quero um", "quero uma", "qual tem mais", "qual o melhor",
        "o melhor celular", "o melhor notebook"))
    tem_pedido = any(v in t for v in _VERBOS_PEDIDO_PRODUTO)
    if not (tem_verbo_forte or tem_pedido):
        return False
    if tem_pedido and not tem_verbo_forte and _RX_EXPLICATIVO_PRODUTO.search(t):
        return False
    tem_produto = ("produto" in t or "modelo" in t or "marca" in t or "loja" in t
                   or bool(re.search(r"\b(ram|memoria|bateria|armazenamento|polegadas|"
                                     r"processador|gb|ssd|5g|nfc)\b", t))
                   or any(c in t for c in CATEGORIAS))
    return bool(tem_produto)


# ── Critérios ─────────────────────────────────────────────────────────

def _extrair_orcamento(texto: str) -> dict:
    """Retorna {min, max} em BRL. 'até R$ 1000' → max=1000.

    Números de modelo NÃO viram orçamento: 'iPhone 15 Pro Max 256GB' não
    tem teto de R$ 256 (o 'max' é edição do aparelho) e 'até 512GB' é
    capacidade, não preço.
    """
    t = (texto or "").lower().replace("\u00a0", " ")
    valores = []

    def _num(bruto: str):
        bruto = bruto.strip().replace(" ", "")
        try:
            if "." in bruto and "," in bruto:
                return float(bruto.replace(".", "").replace(",", "."))
            if "," in bruto:
                return float(bruto.replace(",", "."))
            return float(bruto.replace(".", "") if len(bruto) > 4 else bruto)
        except ValueError:
            return None

    for m in re.finditer(r"r\$\s?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)", t):
        v = _num(m.group(1))
        if v is not None:
            valores.append(v)
    for m in re.finditer(r"(\d[\d.]*(?:,\d{1,2})?)\s?(?:reais|brl)", t):
        v = _num(m.group(1))
        if v is not None:
            valores.append(v)
    criterios = {}
    # só o que NÃO for capacidade/medida entra como orçamento
    _nao_unidade = r"(?!\d)(?!\s?(?:gb|tb|mah|hz|mm|pol|polegadas))"
    # 'pro max' é edição de produto — o 'max' não é teto de preço
    t_busca = re.sub(r"\bpro\s+m[aá]x\b", " ", t)
    m_ate = re.search(
        r"(?:at[eé]|abaixo de|menos de|or[cç]amento(?: de)?(?: at[eé])?)\s?"
        r"(?:de\s?)?(?:r\$\s?)?(\d[\d.]*(?:,\d{1,2})?)" + _nao_unidade, t)
    if m_ate:
        v = _num(m_ate.group(1))
        if v is not None:
            criterios["max"] = v
    m_max = re.search(
        r"(?<![a-z0-9])m[aá]x(?:imo)?\s?(?:de\s?)?(?:r\$\s?)?"
        r"(\d[\d.]*(?:,\d{1,2})?)" + _nao_unidade, t_busca)
    if m_max and "max" not in criterios:
        v = _num(m_max.group(1))
        if v is not None:
            criterios["max"] = v
    m_entre = re.search(
        r"entre\s?(?:r\$\s?)?(\d[\d.]*(?:,\d{1,2})?)" + _nao_unidade +
        r"\s?e\s?(?:r\$\s?)?(\d[\d.]*(?:,\d{1,2})?)" + _nao_unidade, t)
    if m_entre:
        a, b = _num(m_entre.group(1)), _num(m_entre.group(2))
        if a is not None and b is not None:
            criterios["min"], criterios["max"] = min(a, b), max(a, b)
    if "max" not in criterios and valores:
        if re.search(r"(?:at[eé]|abaixo|menos|m[aá]x|or[cç]amento)", t_busca):
            criterios["max"] = max(valores)
    return criterios


def _extrair_ram(texto: str) -> dict:
    """Diferencia RAM FÍSICA de RAM VIRTUAL (ex.: '+8GB RAM Plus' é virtual)."""
    t = (texto or "").lower()
    out = {}
    for m in re.finditer(r"(\d{1,2})\s?gb\s?(?:de\s?)?ram|ram\s?(?:de\s?)?(\d{1,2})\s?gb", t):
        num = m.group(1) or m.group(2)
        apos = t[m.end():m.end() + 15]
        antes = t[max(0, m.start() - 20):m.start()]
        virtual = bool(re.search(r"^\s*(plus|virtual|expans|estendida|extendida)\b", apos)
                       or re.search(r"\b(virtual|expansivel|estendida|extendida|plus)\s*(de\s*)?$", antes))
        try:
            v = int(num)
        except (TypeError, ValueError):
            continue
        if virtual:
            out["ram_virtual_gb"] = max(out.get("ram_virtual_gb", 0), v)
        else:
            out["ram_fisica_gb"] = max(out.get("ram_fisica_gb", 0), v)
    return out


# ── Identidade do produto: versão/edição e modelo (FASE 4) ────────────
# Variante incompatível NUNCA vira correspondência exata. Só se conclui
# conflito a partir do que o anúncio NEGAn de forma legível:
# - versão/edição diferente (Pro × padrão, Plus, Ultra, Mini...);
# - modelo "irmão" com número diferente (s23 para pedido s24);
# - família com número divergente ("iphone 14" para pedido "iphone 15").
# Ausência de número no anúncio não cria compatibilidade afirmada.

_TIERS = ("pro max", "pro", "plus", "ultra", "mini", "lite", "max")

# 'pro' em pt-BR costuma ser contração de "para o" ("notebook pro meu
# filho") — nesses casos NÃO é versão do produto.
_RX_PRO_STOP = re.compile(
    r"pro\s+(?:o|a|os|as|um|uma|meu|minha|meus|minhas|seu|sua|seus|suas|"
    r"ele|ela|eles|elas|isso|isto|aquilo|mim|nos|voc[eê]|que|quem|onde|"
    r"trabalho|estudo|faculdade|escola|jogo|jogar|filho|filha|esposa|"
    r"marido|namorad[ao]|casa|dia|mes|ano|viagem|presente|comprar|usar|"
    r"fazer|ver|dormir|estudar|trabalhar)")


def _tiers_no_texto(texto: str) -> list:
    """Edições citadas no texto ('pro', 'pro max', 'plus', 'ultra'...)."""
    t = _sem_acentos(texto or "").lower()
    if not t:
        return []
    achados = []
    for tier in _TIERS:
        padrao = tier.replace(" ", r"\s+")
        ocorrencias = list(re.finditer(
            r"(?<![a-z0-9])" + padrao + r"(?![a-z0-9])", t))
        if not ocorrencias:
            continue
        if tier == "pro" and not any(
                not _RX_PRO_STOP.match(t, m.start())
                for m in ocorrencias):
            continue
        if tier == "max" and not any(
                not re.search(r"(?:no|pelo|pelas?|ate|em)\s+$",
                              t[max(0, m.start() - 6):m.start()])
                for m in ocorrencias):
            continue
        achados.append(tier)
    if "pro max" in achados:
        achados = [a for a in achados if a not in ("pro", "max")]
    return achados


def _tiers_expandidos(tiers) -> set:
    """'pro' cabe em 'pro max'; 'pro max' não cabe em 'pro'."""
    out = set(str(t) for t in (tiers or []))
    if "pro max" in out:
        out.update(("pro", "max"))
    return out


_RX_TOKEN_MODELO = re.compile(
    r"(?<![a-z0-9])([a-z]{1,4})(\d{2,4})([a-z]{0,2})(?![a-z0-9])")


def _tokens_modelo(texto: str) -> set:
    """Tokens colados letra+número ('s24', 'a54', 'rtx4060')."""
    t = _sem_acentos(texto or "").lower()
    return {m.group(1) + m.group(2) + m.group(3)
            for m in _RX_TOKEN_MODELO.finditer(t)}


_RX_FAMILIA_NUM = re.compile(
    r"(?<![a-z0-9])(air\s?max|iphone|ipad|note|pixel|redmi|flip|fold|watch|"
    r"series|playstation|ps|rtx|gtx|zenfone|kindle)\s*(\d{1,4})(?![a-z0-9])")


def _numeros_familia(texto: str) -> dict:
    """'iphone 15' → {'iphone': ['15']} (família + número separados)."""
    t = _sem_acentos(texto or "").lower()
    out: dict = {}
    for m in _RX_FAMILIA_NUM.finditer(t):
        fam = re.sub(r"\s+", "", m.group(1))
        out.setdefault(fam, set()).add(m.group(2))
    return {k: sorted(v) for k, v in out.items()}


def _partes_token(tok: str):
    m = re.match(r"([a-z]{1,4})(\d{2,4})([a-z]{0,2})$", str(tok or ""))
    return (m.group(1), m.group(2)) if m else None


def _numero_relacionado(a: str, b: str) -> bool:
    """'15'~'15'/'150' relacionam; '14' × '15' não."""
    a, b = str(a), str(b)
    return a == b or a.startswith(b) or b.startswith(a)


def _conflito_modelo(ped_tokens, ped_fams: dict, produto_txt: str):
    """(pedido, achado) quando o anúncio indica OUTRO modelo da família."""
    prod_tokens = _tokens_modelo(produto_txt)
    if not (set(ped_tokens or ()) & prod_tokens):
        for q in sorted(set(ped_tokens or ())):
            pq = _partes_token(q)
            for ptok in sorted(prod_tokens):
                pp = _partes_token(ptok)
                if pq and pp and pq[0] == pp[0] \
                        and len(pq[1]) == len(pp[1]) and pq[1] != pp[1]:
                    return (q, ptok)
    prod_fams = _numeros_familia(produto_txt)
    for fam in sorted(ped_fams or {}):
        nums_prod = prod_fams.get(fam) or []
        nums_ped = [str(n) for n in (ped_fams.get(fam) or [])]
        for pnum in nums_prod:
            if not any(_numero_relacionado(pnum, qnum) for qnum in nums_ped):
                return (f"{fam} {nums_ped[0]}", f"{fam} {pnum}")
    return None


def _modelo_mencionado(specs: dict, produto_txt: str) -> bool:
    """O anúncio cita o modelo/família pedidos (confirmável, não 'sem info')?"""
    tokens = set(specs.get("modelos") or [])
    prod_tokens = _tokens_modelo(produto_txt)
    if tokens and not (tokens & prod_tokens):
        return False
    fams = dict(specs.get("familias") or {})
    if not fams:
        return bool(tokens)
    prod_fams = _numeros_familia(produto_txt)
    for fam, nums in fams.items():
        encontrados = prod_fams.get(fam) or []
        if not any(_numero_relacionado(pq, str(q))
                   for pq in encontrados for q in (nums or [])):
            return False
    return True


def _extrair_specs(texto: str) -> dict:
    t = (texto or "").lower()
    specs = {}
    specs.update(_extrair_ram(texto))
    m = re.search(r"(\d{2,4})\s?gb(?!\s?ram)", t)
    if m and ("armazen" in t or "ssd" in t or "interno" in t or "memória" in t or "memoria" in t):
        try:
            specs["armazenamento_gb"] = int(m.group(1))
        except ValueError:
            pass
    m = re.search(r"(\d)\s?tb", t)
    if m and ("armazen" in t or "ssd" in t or "hd" in t):
        try:
            specs["armazenamento_gb"] = int(m.group(1)) * 1024
        except ValueError:
            pass
    m = re.search(r"(\d{1,2}(?:[.,]\d)?)\s?(?:polegadas|pol|\"|”)", t)
    if m and ("tela" in t or "polegadas" in t or "pol" in t or "tv" in t):
        try:
            specs["tela_pol"] = float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    m = re.search(r"(\d{4,5})\s?mah", t)
    if m:
        try:
            specs["bateria_mah"] = int(m.group(1))
        except ValueError:
            pass
    for flag in ("5g", "nfc", "carregamento rápido", "carregamento rapido",
                 "tela amoled", "amoled", "120hz", "144hz", "60hz",
                 "ip68", "a prova d'água", "a prova dagua", "dual chip",
                 "desbloqueado", "novo", "lacrado", "gamer", "ultrabook",
                 "2 em 1", "touchscreen", "ssd", "placa dedicada"):
        if flag in t:
            specs["flag_" + re.sub(r"\W+", "_", flag).strip("_")] = True
    tiers = _tiers_no_texto(texto)
    if tiers:
        specs["tiers"] = tiers
    tokens = _tokens_modelo(texto)
    fams = _numeros_familia(texto)
    if tokens:
        specs["modelos"] = sorted(tokens)
    if fams:
        specs["familias"] = fams
    return specs


def extrair_criterios(texto: str) -> dict:
    """Categoria, orçamento, marcas e specs obrigatórias do pedido."""
    t = _sem_acentos(texto or "")
    marcas = [m for m in _MARCAS if m in t]
    categoria = ""
    for c in sorted(CATEGORIAS, key=len, reverse=True):
        if c in t and c not in marcas:
            categoria = c
            break
    orc = _extrair_orcamento(texto or "")
    specs = _extrair_specs(texto or "")
    if categoria in ("notebook", "celular", "tablet") and \
            ("ram_fisica_gb" not in specs or "armazenamento_gb" not in specs):
        # V5.7: par "8gb 512gb" (sem as palavras ram/ssd) é o formato típico
        # de anúncio de notebook/celular; só nesses casos e com faixas sãs.
        par = re.search(r"\b(\d{1,2})\s?gb\b[^\d]{0,24}?\b(\d{3,4})\s?gb\b", t)
        if par:
            ram, arm = int(par.group(1)), int(par.group(2))
            if 2 <= ram <= 64 and 64 <= arm <= 8192:
                specs.setdefault("ram_fisica_gb", ram)
                specs.setdefault("armazenamento_gb", arm)
    comparacao = bool(re.search(r"compar|versus|\bvs\b|diferen|qual melhor|prós e contras|pros e contras", t))
    return {"categoria": categoria, "orcamento": orc, "marcas": marcas,
            "specs": specs, "comparacao": comparacao,
            "texto": (texto or "")[:200]}


# ── Preços ────────────────────────────────────────────────────────────

def normalizar_preco(valor, moeda: str = "") -> tuple | None:
    """(valor_float, moeda_ISO). Suporta 'R$ 1.234,56', '1299,99', '$1,299.00'."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if 0 < valor < 1e9:
            return round(float(valor), 2), (moeda or "BRL").upper()[:3] or "BRL"
        return None
    s = str(valor or "").strip()
    if not s or len(s) > 40:
        return None
    s_up = s.upper()
    if "R$" in s_up or "REAIS" in s_up or "BRL" in s_up:
        moeda = "BRL"
    elif "US$" in s_up or "USD" in s_up:
        moeda = "USD"
    m = re.search(r"\d[\d.,\s]*\d|\d", s)
    if not m:
        return None
    bruto = m.group(0).replace(" ", "")
    moeda = (moeda or "BRL").upper()[:3]
    try:
        if "." in bruto and "," in bruto:
            v = float(bruto.replace(".", "").replace(",", "."))
        elif "," in bruto:
            v = float(bruto.replace(",", "."))
        elif re.fullmatch(r"\d+\.\d{1,2}", bruto):
            v = float(bruto)  # separador decimal explícito (ex.: 1299.99)
        else:
            v = float(bruto.replace(".", "").replace(",", ""))
    except ValueError:
        return None
    if not 0 < v < 1e9:
        return None
    return round(v, 2), moeda or "BRL"


def formatar_preco(valor: float | None, moeda: str = "BRL") -> str:
    if valor is None:
        return PRECO_NAO_CONFIRMADO
    s = f"{valor:,.2f}"
    if (moeda or "BRL").upper() == "BRL":
        return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{moeda} {s}"


# ── Extração estruturada (JSON-LD + OpenGraph) ─────────────────────────

_RX_LDJSON = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.S)

_RX_META = re.compile(
    r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']'
    r'|<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']([^"\']+)["\']',
    re.IGNORECASE)


def _limpa(s, teto: int) -> str:
    s = _html.unescape(re.sub(r"<.*?>", "", str(s or ""))).strip()
    return re.sub(r"\s+", " ", s)[:teto]


def _nome_marca(b) -> str:
    if isinstance(b, dict):
        return _limpa(b.get("name"), 80)
    return _limpa(b, 80)


def _primeira_imagem(img) -> str:
    if isinstance(img, list):
        for i in img:
            u = _primeira_imagem(i)
            if u:
                return u
        return ""
    if isinstance(img, dict):
        return _limpa(img.get("url") or img.get("contentUrl"), 500)
    u = _limpa(img, 500)
    return u if re.match(r"^https?://", u, re.IGNORECASE) else ""


_DISPONIBILIDADES = {"InStock": "em_estoque", "OutOfStock": "sem_estoque",
                     "LimitedAvailability": "estoque_limitado",
                     "PreOrder": "pre_venda"}


def _disp_normalizada(bruta) -> str:
    d = str(bruta or "")
    d = d.rsplit("/", 1)[-1] if "/" in d else d
    return _DISPONIBILIDADES.get(d, "desconhecida")


def _ofertas_de(ofertas) -> list:
    if isinstance(ofertas, dict):
        ofertas = [ofertas]
    if not isinstance(ofertas, list):
        return []
    out = []
    for o in ofertas:
        if not isinstance(o, dict):
            continue
        tipo = str(o.get("@type", ""))
        itens = o.get("offers", []) if tipo == "AggregateOffer" else [o]
        if isinstance(itens, dict):
            itens = [itens]
        if tipo == "AggregateOffer" and not itens:
            # Faixa (lowPrice/highPrice) sem ofertas aninhadas: o MENOR vira
            # preço e o teto fica marcado — nunca apresentar um só número
            # como se fosse o preço único. Sem números → nenhuma oferta.
            lp = normalizar_preco(o.get("lowPrice"),
                                  str(o.get("priceCurrency") or ""))
            hp = normalizar_preco(o.get("highPrice"),
                                  str(o.get("priceCurrency") or ""))
            base = lp or hp
            if base:
                out.append({
                    "preco": base[0],
                    "moeda": base[1],
                    "preco_confirmado": True,
                    "preco_alto": hp[0] if (hp and hp[0] != base[0]) else None,
                    "disponibilidade": _disp_normalizada(o.get("availability")),
                    "url_oferta": _limpa(o.get("url"), 500),
                    "loja": _nome_marca(o.get("seller")),
                    "valido_ate": _limpa(o.get("priceValidUntil"), 20),
                })
            continue
        for it in itens:
            if not isinstance(it, dict):
                continue
            pv = normalizar_preco(it.get("price"), str(it.get("priceCurrency") or ""))
            vendedor = it.get("seller")
            out.append({
                "preco": pv[0] if pv else None,
                "moeda": pv[1] if pv else "BRL",
                "preco_confirmado": bool(pv),
                "disponibilidade": _disp_normalizada(it.get("availability")),
                "url_oferta": _limpa(it.get("url"), 500),
                "loja": _nome_marca(vendedor),
                "valido_ate": _limpa(it.get("priceValidUntil"), 20),
            })
    return out


def _produto_de_no(no: dict) -> dict | None:
    tipos = no.get("@type", [])
    tipos = [tipos] if isinstance(tipos, str) else list(tipos or [])
    if "Product" not in tipos:
        return None
    nome = _limpa(no.get("name"), 160)
    if not nome:
        return None
    agg = no.get("aggregateRating") if isinstance(no.get("aggregateRating"), dict) else {}
    try:
        aval = float(str(agg.get("ratingValue", "")).replace(",", "."))
        aval = aval if 0 <= aval <= 5 else None
    except (TypeError, ValueError):
        aval = None
    try:
        n_aval = int(float(str(agg.get("reviewCount", "") or "0").replace(".", "").replace(",", "")))
    except (TypeError, ValueError):
        n_aval = None
    return {
        "nome": nome,
        "marca": _nome_marca(no.get("brand")),
        "modelo": _limpa(no.get("model") or no.get("mpn") or no.get("sku"), 80),
        "variante": _limpa(no.get("color"), 80),
        "imagem": _primeira_imagem(no.get("image")),
        "descricao": _limpa(no.get("description"), 300),
        "avaliacao": aval,
        "n_avaliacoes": n_aval,
        "ofertas_ld": _ofertas_de(no.get("offers")),
        "url_produto": _limpa(no.get("url"), 500),
    }


def _nos_produto(obj) -> list:
    achados = []
    if isinstance(obj, dict):
        if "@graph" in obj and isinstance(obj["@graph"], list):
            for item in obj["@graph"]:
                achados.extend(_nos_produto(item))
        else:
            p = _produto_de_no(obj)
            if p:
                achados.append(p)
            for v in obj.values():
                achados.extend(_nos_produto(v))
    elif isinstance(obj, list):
        for item in obj:
            achados.extend(_nos_produto(item))
    return achados


def extrair_ofertas_jsonld(pagina: str) -> list:
    """Produtos com ofertas a partir de blocos JSON-LD. Nunca inventa."""
    out = []
    for m in _RX_LDJSON.finditer(pagina or ""):
        try:
            obj = json.loads(m.group(1))
        except (ValueError, TypeError, RecursionError):
            continue
        try:
            out.extend(_nos_produto(obj))
        except (AttributeError, TypeError, RecursionError):
            continue
        if len(out) >= 4:
            break
    return out[:4]


def extrair_opengraph(pagina: str) -> dict:
    """Fallback: og:title/image + product:price. Sem preço → não confirmado."""
    metas: dict = {}
    for m in _RX_META.finditer(pagina or ""):
        k = (m.group(1) or m.group(4) or "").lower()
        v = (m.group(2) or m.group(3) or "")
        if k and v and k not in metas:
            metas[k] = _limpa(v, 300)
    pv = normalizar_preco(metas.get("product:price:amount") or metas.get("og:price:amount") or "",
                          metas.get("product:price:currency") or metas.get("og:price:currency") or "")
    titulo = metas.get("og:title", "")
    if not titulo:
        return {}
    img = metas.get("og:image", "")
    img = img if re.match(r"^https?://", img, re.IGNORECASE) else ""
    return {"nome": titulo[:160], "marca": "", "modelo": "", "variante": "",
            "imagem": img[:500], "descricao": metas.get("og:description", "")[:300],
            "avaliacao": None, "n_avaliacoes": None,
            "ofertas_ld": [{"preco": pv[0] if pv else None,
                             "moeda": pv[1] if pv else "BRL",
                             "preco_confirmado": bool(pv),
                             "disponibilidade": "desconhecida",
                             "url_oferta": "", "loja": "", "valido_ate": ""}]}


# ── Normalização / dedupe / filtros ────────────────────────────────────

def _chave_nome(nome: str) -> str:
    t = _sem_acentos(nome)
    t = re.sub(r"\b(smartphone|celular|notebook|laptop|novo|original|lacrado|oferta|promocao|promoção)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def chave_dedupe(prod: dict) -> str:
    base = (_chave_nome(prod.get("nome", "")) + "|" +
            _sem_acentos(prod.get("marca", "")) + "|" +
            _sem_acentos(prod.get("modelo", "")) + "|" +
            _sem_acentos(prod.get("variante", "")))
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def _dominio(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url or "").hostname or "")[:120]
    except ValueError:
        return ""


def montar_produto(extraido: dict, url: str, url_final: str,
                   titulo_fonte: str, validacao: dict = None,
                   url_item: str = "") -> dict:
    ofertas = extraido.get("ofertas_ld") or []
    loja = ""
    for o in ofertas:
        if not loja and o.get("loja"):
            loja = o["loja"]
    # FASE 4: várias ofertas/faixa → menor preço com "a partir de"
    # (o preço de UMA variante nunca é apresentado como preço único).
    confirmadas = [o for o in ofertas if o.get("preco") is not None]
    preco = None
    moeda = "BRL"
    confirmado = False
    disp = "desconhecida"
    faixa = False
    if confirmadas:
        precos = sorted({round(float(o["preco"]), 2) for o in confirmadas})
        preco = precos[0]
        dono = next(o for o in confirmadas
                    if round(float(o["preco"]), 2) == preco)
        moeda = dono.get("moeda", "BRL")
        disp = dono.get("disponibilidade") or "desconhecida"
        confirmado = True
        faixa = len(precos) > 1 or any(
            o.get("preco_alto") is not None for o in confirmadas)
    if not loja:
        dom = _dominio(url_final or url)
        loja = dom[4:] if dom.startswith("www.") else dom
    agora = agora_iso()
    specs = extraido.get("specs") if isinstance(extraido.get("specs"), dict) else {}
    # Link do ITEM (página do produto em si): URL declarada no dado
    # estruturado > URL da 1ª oferta > página analisada. Nunca inventado.
    # FASE 4: home/busca declarada não vence um link de produto real; se
    # for o único dado, é mantida mesmo assim (não inventamos outro).
    candidatos = []
    for cand in (url_item or extraido.get("url_produto") or "",
                 *[o.get("url_oferta") for o in ofertas],
                 url_final or url):
        cand = _limpa(cand, 500)
        if cand:
            candidatos.append(cand)
    item = next((c for c in candidatos
                 if not source_check.url_de_listagem(c)), "")
    if not item and candidatos:
        item = candidatos[0]
    val = validacao if isinstance(validacao, dict) else {}
    val_codigo = _limpa(val.get("codigo"), 40)
    val_veredito = _limpa(val.get("veredito"), 24)
    if val_veredito not in source_check.VEREDITOS:
        val_veredito = ""
    return {
        "id": chave_dedupe({"nome": extraido.get("nome", ""),
                             "marca": extraido.get("marca", ""),
                             "modelo": extraido.get("modelo", ""),
                             "variante": extraido.get("variante", "")}),
        "nome": extraido.get("nome", "")[:160],
        "marca": extraido.get("marca", "")[:80],
        "modelo": extraido.get("modelo", "")[:80],
        "variante": extraido.get("variante", "")[:80],
        "imagem": extraido.get("imagem", "")[:500],
        "descricao": extraido.get("descricao", "")[:300],
        "loja": loja[:80],
        "loja_dominio": _dominio(url_final or url),
        "url": (url or "")[:500],
        "url_final": (url_final or url or "")[:500],
        "url_item": item,
        "preco": preco,
        "moeda": moeda,
        "preco_confirmado": confirmado,
        "preco_a_partir_de": bool(confirmado and faixa),
        "preco_texto": (f"a partir de {formatar_preco(preco, moeda)}"
                        if (confirmado and faixa)
                        else formatar_preco(preco, moeda)),
        "preco_origem": _limpa(extraido.get("origem_preco"), 24) if confirmado else "",
        "disponibilidade": disp,
        "avaliacao": extraido.get("avaliacao"),
        "n_avaliacoes": extraido.get("n_avaliacoes"),
        "specs": {str(k)[:40]: str(v)[:120]
                  for k, v in list(specs.items())[:12]},
        "verificado_em": agora,
        "fonte_titulo": (titulo_fonte or "")[:160],
        "link_veredito": val_veredito,
        "link_codigo": val_codigo,
        "link_motivo": _limpa(val.get("motivo"), 160),
        "item_de_listagem": val_codigo == "item_de_listagem",
        "imagem_veredito": "",
    }


def deduplicar(produtos: list) -> list:
    """Mesmo produto em lojas distintas → 1 produto com N ofertas."""
    por_chave: dict = {}
    for p in produtos:
        pid = p.get("id") or chave_dedupe(p)
        p["id"] = pid
        if pid not in por_chave:
            por_chave[pid] = p
            por_chave[pid]["ofertas"] = []
        dest = por_chave[pid]
        dest["ofertas"].append({
            "loja": p.get("loja", ""), "preco": p.get("preco"),
            "moeda": p.get("moeda", "BRL"),
            "preco_texto": p.get("preco_texto", PRECO_NAO_CONFIRMADO),
            "url": p.get("url_item") or p.get("url_final") or p.get("url", ""),
            "disponibilidade": p.get("disponibilidade", "desconhecida"),
            "verificado_em": p.get("verificado_em", ""),
        })
        if not dest.get("imagem") and p.get("imagem"):
            dest["imagem"] = p["imagem"]
        if p.get("preco") is not None and (
                dest.get("preco") is None or p["preco"] < dest["preco"]):
            for k in ("preco", "moeda", "preco_texto", "preco_a_partir_de",
                      "loja", "url_final",
                      "disponibilidade", "verificado_em", "url_item",
                      "preco_origem", "link_veredito", "link_codigo",
                      "link_motivo", "item_de_listagem"):
                dest[k] = p.get(k)
            dest["preco_confirmado"] = True
    for p in por_chave.values():
        vistos, unicas = set(), []
        for o in p["ofertas"]:
            k = (o.get("loja", ""), o.get("preco"), o.get("url", ""))
            if k not in vistos:
                vistos.add(k)
                unicas.append(o)
        unicas.sort(key=lambda o: (o.get("preco") is None, o.get("preco") or 0))
        p["ofertas"] = unicas[:6]
    return list(por_chave.values())


def _ram_do_produto(p: dict) -> tuple | None:
    """(fisica_gb, virtual_gb) a partir de specs/nome. None se desconhecida."""
    texto = " ".join([p.get("nome", ""), p.get("modelo", ""),
                      json.dumps(p.get("specs", {}), ensure_ascii=False)]).lower()
    fis, vir = [], []
    for m in re.finditer(r"(\d{1,2})\s?gb\s?(?:de\s?)?ram", texto):
        janela = texto[max(0, m.start() - 30):m.end() + 30]
        (vir if re.search(r"virtual|plus|expans|estendida|extendida", janela)
         else fis).append(int(m.group(1)))
    if not fis and not vir:
        return None
    return (max(fis) if fis else 0, max(vir) if vir else 0)


def aplicar_filtros(produtos: list, criterios: dict) -> tuple:
    """(dentro, fora_com_motivo). Fora do orçamento/specs vem explicado.

    Cada produto fora carrega `excluido_codigos` (ex.: preco_acima, usado)
    para a etapa de alternativas não depender de texto.
    """
    dentro, fora = [], []
    orc = criterios.get("orcamento", {}) or {}
    specs = criterios.get("specs", {}) or {}
    marcas_pedido = [_sem_acentos(str(m)) for m in (criterios.get("marcas") or [])
                     if str(m).strip()]
    for p in produtos:
        motivos, codigos = [], []
        if orc.get("max") is not None and p.get("preco") is not None \
                and p["preco"] > orc["max"]:
            motivos.append(f"acima do orçamento ({p['preco_texto']})")
            codigos.append("preco_acima")
        if orc.get("min") is not None and p.get("preco") is not None \
                and p["preco"] < orc["min"]:
            motivos.append(f"abaixo da faixa ({p['preco_texto']})")
            codigos.append("preco_abaixo")
        if marcas_pedido:
            # V5.7: marca pedida é critério obrigatório — nunca misturar
            # marcas diferentes como se fossem o pedido (marca do anúncio
            # ou menção clara no nome; sem isso, é "não confirmada").
            alvo = _sem_acentos((p.get("marca") or "") + " " + (p.get("nome") or ""))
            if not any(_marca_no_texto(m, alvo) for m in marcas_pedido):
                conhecida = (_marca_conhecida(_sem_acentos(p.get("marca") or ""))
                             or _marca_conhecida(_sem_acentos(p.get("nome") or "")))
                if conhecida:
                    motivos.append("marca diferente do pedido "
                                   f"({conhecida}; pedido: {', '.join(marcas_pedido)})")
                    codigos.append("marca_diferente")
                else:
                    motivos.append("marca não confirmada no anúncio "
                                   f"(pedido: {', '.join(marcas_pedido)})")
                    codigos.append("marca_nao_confirmada")
        if specs.get("ram_fisica_gb"):
            ram = _ram_do_produto(p)
            if ram is not None and ram[0] < specs["ram_fisica_gb"] and ram[0] > 0:
                motivos.append(f"RAM física abaixo do pedido ({ram[0]}GB)")
                codigos.append("ram_abaixa")
            elif ram is not None and ram[0] == 0 and specs["ram_fisica_gb"] > 0:
                motivos.append("só informa RAM virtual/expansível")
                codigos.append("ram_virtual")
        if specs.get("flag_novo"):
            cond = str((p.get("specs", {}) or {}).get("Condicao", "")).lower()
            if cond == "usado":
                motivos.append("usado (pedido: somente novos)")
                codigos.append("usado")
        if specs.get("armazenamento_gb"):
            txt = (p.get("nome", "") + json.dumps(p.get("specs", {}))).lower()
            ap = _armazenamento_aparente(txt)
            if ap is not None and ap < specs["armazenamento_gb"]:
                motivos.append("armazenamento abaixo do pedido")
                codigos.append("armazenamento_abaixa")
        # FASE 4: versão/edição e modelo pedidos são identidade, não enfeite.
        tiers_pedido = [str(x) for x in (specs.get("tiers") or [])
                        if str(x).strip()]
        if tiers_pedido:
            titulo_p = (p.get("nome") or "") + " " + (p.get("modelo") or "")
            tiers_prod = _tiers_no_texto(titulo_p)
            if not _tiers_expandidos(tiers_pedido).issubset(
                    _tiers_expandidos(tiers_prod)):
                motivos.append(
                    "versão não confere com o pedido (pedido: "
                    + " + ".join(tiers_pedido) + "; anúncio: "
                    + (" + ".join(tiers_prod) or "sem indicação de versão")
                    + ")")
                codigos.append("versao_diferente")
        modelos_pedido = set(specs.get("modelos") or [])
        familias_pedido = dict(specs.get("familias") or {})
        if modelos_pedido or familias_pedido:
            alvo_p = _sem_acentos((p.get("nome") or "") + " "
                                  + (p.get("modelo") or "")).lower()
            conflito = _conflito_modelo(modelos_pedido, familias_pedido, alvo_p)
            if conflito:
                motivos.append("modelo diferente do pedido (pedido: "
                               f"{conflito[0]}; anúncio: {conflito[1]})")
                codigos.append("modelo_diferente")
            elif not _modelo_mencionado(specs, alvo_p):
                motivos.append("modelo do pedido não indicado no anúncio "
                               f"({', '.join(sorted(modelos_pedido)) or ''}"
                               f"{' ' if modelos_pedido and familias_pedido else ''}"
                               + ", ".join(f"{k} {v[0]}" for k, v in
                                           sorted(familias_pedido.items()))
                               + ")")
                codigos.append("modelo_nao_confirmado")
        if motivos:
            p["excluido_por"] = "; ".join(motivos)
            p["excluido_codigos"] = codigos
            fora.append(p)
        else:
            dentro.append(p)
    dentro.sort(key=lambda p: (not p.get("preco_confirmado"),
                               p.get("preco") is None, p.get("preco") or 0))
    return dentro, fora


def separar_alternativas(fora: list, criterios: dict, maximo: int = 3,
                         tolerancia_preco: float = 0.25) -> list:
    """'Quase atende' → alternativa com diferenças explícitas; resto, descarte.

    Nunca esconde a diferença: preço acima do teto (até +25%), RAM ou
    armazenamento abaixo do pedido, RAM só virtual, usado quando pediu
    novo — cada uma vira texto claro em `diferencas`. Muito acima do
    orçamento ou produto de outra faixa (abaixo do mínimo) é descarte.
    """
    orc = criterios.get("orcamento", {}) or {}
    specs = criterios.get("specs", {}) or {}
    alts = []
    for p in fora or []:
        codigos = set(p.get("excluido_codigos") or [])
        difs: list = []
        distancias: list = []
        if "marca_diferente" in codigos or "marca_nao_confirmada" in codigos:
            # outra marca entra como ALTERNATIVA explícita, nunca como se
            # fosse o pedido (V5.7)
            pedido = ", ".join(_sem_acentos(str(m))
                               for m in (criterios.get("marcas") or []))
            if "marca_diferente" in codigos:
                achada = (_marca_conhecida(_sem_acentos(p.get("marca") or ""))
                          or _marca_conhecida(_sem_acentos(p.get("nome") or "")))
                difs.append(f"outra marca: {achada or 'não confirmada'} "
                            f"(pedido: {pedido})")
                distancias.append(0.55)
            else:
                difs.append(f"marca não confirmada no anúncio (pedido: {pedido})")
                distancias.append(0.7)
        if "preco_acima" in codigos:
            teto = orc.get("max")
            if not teto or p.get("preco") is None:
                continue
            excesso = (p["preco"] - float(teto)) / float(teto)
            if excesso > tolerancia_preco:
                continue
            difs.append(f"{p.get('preco_texto', PRECO_NAO_CONFIRMADO)} — "
                        f"{excesso * 100:.0f}% acima do teto "
                        f"({formatar_preco(float(teto))})")
            distancias.append(excesso)
        if "ram_abaixa" in codigos or "ram_virtual" in codigos:
            ram = _ram_do_produto(p)
            pedido = specs.get("ram_fisica_gb") or 0
            if ram and ram[0] and pedido:
                difs.append(f"RAM {ram[0]}GB (pedido: {pedido}GB)")
                distancias.append(max(0.0, (pedido - ram[0]) / float(pedido)))
            else:
                difs.append(f"RAM física não confirmada (pedido: {pedido}GB)"
                            if pedido else "RAM não confirmada")
                distancias.append(0.6)
        if "armazenamento_abaixa" in codigos:
            pedido = specs.get("armazenamento_gb") or 0
            txt = (p.get("nome", "") + json.dumps(p.get("specs", {}))).lower()
            ap = _armazenamento_aparente(txt)
            if ap is not None and pedido:
                difs.append(f"armazenamento {ap}GB (pedido: {pedido}GB)")
                distancias.append(max(0.0, 1 - ap / float(pedido)))
            else:
                difs.append("armazenamento abaixo do pedido")
                distancias.append(0.6)
        if "usado" in codigos:
            difs.append("condição: usado (pedido: somente novos)")
            distancias.append(0.5)
        if "versao_diferente" in codigos:
            tiers_prod = _tiers_no_texto((p.get("nome") or "") + " "
                                         + (p.get("modelo") or ""))
            pedido_v = " + ".join(str(t) for t in (specs.get("tiers") or []))
            difs.append("versão "
                        + (" + ".join(tiers_prod) or "padrão/sem indicação")
                        + f" (pedido: {pedido_v})")
            distancias.append(0.35)
        if "modelo_diferente" in codigos or "modelo_nao_confirmado" in codigos:
            if "modelo_diferente" in codigos:
                conflito = _conflito_modelo(
                    set(specs.get("modelos") or []),
                    dict(specs.get("familias") or {}),
                    _sem_acentos((p.get("nome") or "") + " "
                                 + (p.get("modelo") or "")).lower())
                difs.append(f"modelo {conflito[1]} (pedido: {conflito[0]})"
                            if conflito else "modelo diferente do pedido")
            else:
                pedido_m = ", ".join(
                    sorted(set(specs.get("modelos") or [])
                           | {f"{k} {v[0]}" for k, v in
                              (specs.get("familias") or {}).items()}))
                difs.append(f"modelo não indicado no anúncio (pedido: {pedido_m})")
            distancias.append(0.45)
        if not difs:
            continue
        alt = dict(p)
        alt["diferencas"] = " · ".join(difs)
        alt["diferencas_lista"] = difs
        alt["distancia"] = round(min(distancias), 3)
        alts.append(alt)
    alts.sort(key=lambda a: (a.get("distancia", 1.0),
                             a.get("preco_confirmado") is False,
                             a.get("preco") or 0))
    return alts[:maximo]


# ── Persistência (por dono; preço guardado = histórico) ─────────────────

def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS shopping_consultas (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
        conv TEXT NOT NULL DEFAULT '', consulta TEXT NOT NULL DEFAULT '',
        criterios TEXT NOT NULL DEFAULT '{}', resultado TEXT NOT NULL DEFAULT '{}',
        criado_em TEXT NOT NULL, expira_em TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_shop_owner_conv "
               "ON shopping_consultas(owner_id, conv, criado_em)")
    db.commit()


def _id_consulta(owner: str, consulta: str) -> str:
    return "shop-" + hashlib.sha256(
        f"{owner}\x00{research.normalizar_consulta(consulta)}".encode()
    ).hexdigest()[:16]


def salvar_consulta(db, owner: str, conv: str, consulta: str,
                    criterios: dict, resultado: dict) -> str:
    import secrets as _s
    sid = _id_consulta(owner, consulta) + _s.token_hex(2)
    with db:
        db.execute("INSERT INTO shopping_consultas (id, owner_id, conv, consulta,"
                   " criterios, resultado, criado_em, expira_em)"
                   " VALUES (?,?,?,?,?,?,?,?)",
                   (sid, owner, conv or "", consulta[:200],
                    json.dumps(criterios, ensure_ascii=False)[:4000],
                    json.dumps(resultado, ensure_ascii=False)[:60000],
                    agora_iso(),
                    datetime.fromtimestamp(time.time() + TTL_CONSULTA,
                                           timezone.utc).isoformat()))
        db.execute("DELETE FROM shopping_consultas WHERE owner_id=? AND conv=? AND id NOT IN "
                   "(SELECT id FROM shopping_consultas WHERE owner_id=? AND conv=?"
                   " ORDER BY criado_em DESC LIMIT ?)",
                   (owner, conv or "", owner, conv or "", MAX_CONSULTAS_POR_CONV))
    return sid


def ultima_consulta(db, owner: str, conv: str) -> dict | None:
    row = db.execute("SELECT id, consulta, criterios, resultado, criado_em"
                     " FROM shopping_consultas WHERE owner_id=? AND conv=?"
                     " ORDER BY criado_em DESC LIMIT 1",
                     (owner, conv or "")).fetchone()
    if not row:
        return None
    try:
        return {"id": row[0], "consulta": row[1],
                "criterios": json.loads(row[2] or "{}"),
                "resultado": json.loads(row[3] or "{}"),
                "criado_em": row[4]}
    except (TypeError, ValueError):
        return None


def consulta_em_cache(db, owner: str, consulta: str) -> dict | None:
    row = db.execute("SELECT resultado, criado_em FROM shopping_consultas"
                     " WHERE id LIKE ? AND owner_id=? AND expira_em > ?"
                     " ORDER BY criado_em DESC LIMIT 1",
                     (_id_consulta(owner, consulta) + "%", owner, agora_iso())).fetchone()
    if not row:
        return None
    try:
        res = json.loads(row[0])
        res["de_cache"] = True
        res["verificado_em"] = row[1]
        return res
    except (TypeError, ValueError):
        return None


# ── Provedores de busca (V4.9.1.1: cadeia com fallback) ────────────────
# Ordem: API oficial e estruturada primeiro (sem chave, sem scraping),
# depois busca web genérica. Nenhum provedor é contornado: bloqueio/
# CAPTCHA/bot-wall vira falha registrada + fallback, nunca bypass.
# - Mercado Livre (api.mercadolibre.com/sites/MLB): JSON oficial, preço,
#   foto, link, loja/vendedor, condição e estoque reais.
# - DuckDuckGo HTML / Lite (research.buscar_ddg): links p/ extração JSON-LD.

MLB_SEARCH_URL = "https://api.mercadolibre.com/sites/MLB/search"
MLB_TIMEOUT = 8.0


def _get_json(url: str, timeout: float) -> dict:
    """GET JSON com a mesma disciplina SSRF de `research.baixar` (só texto
    vira JSON aqui): URL validada, redirects revalidados um a um, teto de
    tamanho e tempo. Bloqueio do provedor vira ResearchErro, nunca bypass."""
    import urllib.error
    import urllib.parse as _up
    atual = research.url_segura(url)
    for _ in range(research.MAX_REDIRECTS + 1):
        try:
            resp = research._abrir(atual, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                loc = exc.headers.get("Location", "")
                if not loc:
                    raise research.ResearchErro("Redirect sem destino.", "redirect")
                atual = research.url_segura(_up.urljoin(atual, loc))
                continue
            raise research.ResearchErro(f"Provedor HTTP {exc.code}.", "http")
        except (OSError, TimeoutError, ValueError) as exc:
            raise research.ResearchErro(
                f"Falha de rede ({type(exc).__name__}).", "rede") from None
        with resp:
            if getattr(resp, "status", 200) >= 400:
                raise research.ResearchErro(
                    f"Provedor HTTP {resp.status}.", "http")
            try:
                ctype = (resp.headers.get_content_type()
                         if hasattr(resp.headers, "get_content_type")
                         else str(resp.headers.get("Content-Type", "")).split(";")[0])
            except Exception:
                ctype = ""
            if "json" not in (ctype or "").lower():
                raise research.ResearchErro("Provedor sem JSON.", "tipo_bloqueado")
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            if total > 512 * 1024:
                raise research.ResearchErro("Resposta grande demais.", "tamanho")
            raw = resp.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise research.ResearchErro("Resposta grande demais.", "tamanho")
            try:
                obj = json.loads(raw.decode("utf-8", errors="ignore"))
            except (ValueError, TypeError) as exc:
                raise research.ResearchErro("JSON inválido.", "formato") from None
            if not isinstance(obj, dict):
                raise research.ResearchErro("JSON inesperado.", "formato")
            return obj
    raise research.ResearchErro("Redirects demais.", "redirect")


def buscar_mlb(consulta: str, limite: int = 10,
               timeout: float = MLB_TIMEOUT) -> list:
    """Busca oficial no Mercado Livre (sem chave). Levanta ResearchErro."""
    import urllib.parse as _up
    q = (consulta or "").strip()[:120]
    if not q:
        return []
    dados = _get_json(
        MLB_SEARCH_URL + "?" + _up.urlencode(
            {"q": q, "limit": min(max(int(limite), 1), 20)}),
        timeout=timeout)
    out = []
    for item in (dados.get("results") or [])[:limite]:
        if not isinstance(item, dict):
            continue
        link = str(item.get("permalink", ""))[:500]
        titulo = _limpa(item.get("title"), 160)
        if not link.startswith("http") or not titulo:
            continue
        out.append({"titulo": titulo, "url": link,
                     "trecho": f"{titulo} — {formatar_preco(item.get('price'), str(item.get('currency_id') or 'BRL'))}",
                     "origem": "mlb", "mlb": item})
    if not out:
        raise research.ResearchErro("Provedor sem resultados.", "vazio")
    return out


def produto_de_mlb(item: dict) -> dict | None:
    """Converte item da API oficial em extraído (preço/foto/loja reais)."""
    if not isinstance(item, dict):
        return None
    nome = _limpa(item.get("title"), 160)
    link = str(item.get("permalink", ""))[:500]
    if not nome or not link.startswith("http"):
        return None
    marca, condicao = "", str(item.get("condition", "")).lower()
    for at in (item.get("attributes") or []):
        if not isinstance(at, dict):
            continue
        aid = str(at.get("id", "")).upper()
        if aid in ("BRAND", "MARCA") and not marca:
            marca = _limpa(at.get("value_name"), 80)
    pv = normalizar_preco(item.get("price"), str(item.get("currency_id") or "BRL"))
    try:
        estoque = int(item.get("available_quantity", -1))
    except (TypeError, ValueError):
        estoque = -1
    vendedor = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    nick = _limpa(vendedor.get("nickname"), 40)
    img = _primeira_imagem(item.get("thumbnail"))
    specs = {}
    if condicao == "new":
        specs["Condicao"] = "Novo"
    elif condicao == "used":
        specs["Condicao"] = "Usado"
    return {
        "nome": nome, "marca": marca, "modelo": "", "variante": "",
        "imagem": img, "descricao": "",
        "avaliacao": None, "n_avaliacoes": None,
        "condicao_mlb": condicao,
        "specs": specs,
        "origem_preco": "mlb",
        "url_produto": link,
        "ofertas_ld": [{
            "preco": pv[0] if pv else None,
            "moeda": pv[1] if pv else "BRL",
            "preco_confirmado": bool(pv),
            "disponibilidade": "em_estoque" if estoque > 0 else (
                "sem_estoque" if estoque == 0 else "desconhecida"),
            "url_oferta": link,
            "loja": "Mercado Livre" + (f" · {nick}" if nick else ""),
            "valido_ate": "",
        }],
    }


def buscar_ddg_chain(consulta: str, max_resultados: int = 6) -> tuple:
    """DDG HTML → Lite. Retorna (achados, etapas). Nunca levanta."""
    etapas = []
    for base_nome, base in (("ddg", research.DDG_HTML), ("ddg-lite", research.DDG_LITE)):
        try:
            achados = research.buscar_ddg(consulta, base=base,
                                          max_resultados=max_resultados) or []
        except Exception as exc:
            etapas.append(f"{base_nome}: falhou ({type(exc).__name__})")
            continue
        if achados:
            etapas.append(f"{base_nome}: {len(achados)} resultados")
            return achados, etapas
        etapas.append(f"{base_nome}: sem resultados (bloqueio?)")
    return [], etapas


def buscar_web_v55(consulta: str, max_resultados: int = 10) -> tuple:
    """Etapa web do Research Engine V5.5: orquestrador multi-provedor real.

    Roda por ÚLTIMO na cadeia (não muda a ordem mlb → ddg → ddg-lite dos
    diagnósticos legados). Nunca levanta: bloqueio/vazio viram etapa.
    Retorna (achados, etapas).
    """
    try:
        achados, info = research._buscar_orquestrado(consulta, max_resultados=max_resultados)
    except Exception as exc:
        return [], [f"web: falhou ({type(exc).__name__})"]
    estado = (info or {}).get("estado", "") or "?"
    if not achados:
        return [], [f"web: sem resultados ({estado})"]
    usados = ((info or {}).get("provedores", {}) or {}).get("usados", {}) or {}
    nomes = "+".join(sorted(usados)[:3]) or "orquestrado"
    return achados, [f"web: {len(achados)} resultados ({nomes}, {estado})"]


def buscar_com_fallback(consulta: str, buscar_fn=None,
                        limite_mlb: int = 10) -> tuple:
    """Cadeia mlb → ddg → lite → web (orquestrador). Retorna (achados, etapas).

    Nunca levanta. A etapa `web` roda por último e só quando as anteriores
    não trouxeram nada; ela é a mesma busca multi-provedor do Research
    Engine (Bing/Marginalia/Wikipedia/...), sem bypass de bloqueio.
    """
    if buscar_fn is not None:
        try:
            return list(buscar_fn(consulta) or [])[:12], ["injetado (teste)"]
        except Exception as exc:
            return [], [f"injetado falhou ({type(exc).__name__})"]
    etapas: list = []
    try:
        achados = buscar_mlb(consulta, limite=limite_mlb)
        etapas.append(f"mlb: {len(achados)} ofertas (API oficial)")
        return achados, etapas
    except Exception as exc:
        etapas.append(f"mlb: falhou ({type(exc).__name__})")
    ddg, detapas = buscar_ddg_chain(consulta)
    etapas.extend(detapas)
    if ddg:
        return ddg, etapas
    achados, wetapas = buscar_web_v55(consulta)
    etapas.extend(wetapas)
    return achados, etapas


def diagnosticar_provedores(timeout: float = 6.0) -> list:
    """Sonda cada provedor com consulta mínima. Sem bypass; só registra."""
    diag = []
    try:
        n = len(buscar_mlb("celular", limite=1, timeout=timeout))
        diag.append({"provedor": "mlb", "ok": True,
                     "detalhe": f"API oficial respondeu ({n} item)"})
    except Exception as exc:
        diag.append({"provedor": "mlb", "ok": False,
                     "detalhe": f"{type(exc).__name__}: {exc}"})
    for base_nome, base in (("ddg", research.DDG_HTML), ("ddg-lite", research.DDG_LITE)):
        try:
            achados = research.buscar_ddg("celular comprar", base=base,
                                          max_resultados=1, timeout=timeout)
            diag.append({"provedor": base_nome, "ok": bool(achados),
                         "detalhe": f"{len(achados)} resultado(s)" if achados
                         else "página sem resultados (bot-wall?)"})
        except Exception as exc:
            diag.append({"provedor": base_nome, "ok": False,
                         "detalhe": f"{type(exc).__name__}: {exc}"})
    return diag


# ── Busca orquestrada (reusa Research Engine; sem loja única) ──────────

_RX_PEDIDO_WORDS = re.compile(
    r"\b(?:me\s+mostre|mostre|mostra|quero|queria|procuro|pesquis[ea]|"
    r"pesquise|busque|buscar|encontre|encontrar|pre[cç]os?|preco|imagens?|"
    r"fotos?|links?|comprar|compra|ofertas?|promo[cç][aã]o|promo|onde|"
    r"quanto|custa|por\s+favor|pra\s+mim|para\s+mim|imagem)\b",
    re.IGNORECASE)


def _termo_referencia(texto: str) -> str:
    """Referência do usuário sem as palavras de pedido ('me mostre', ...).

    A busca não pode descartar o modelo pedido ('Adidas Pro Model 2.0',
    'Galaxy S24') — era essa lacuna que devolvia resultados genéricos.
    """
    t = re.sub(r"\s+", " ", (texto or "")).strip()
    if not t:
        return ""
    t = _RX_PEDIDO_WORDS.sub(" ", t)
    vazias = {"e", "o", "a", "os", "as", "de", "do", "da", "dos", "das",
              "por", "com", "para", "pra", "no", "na", "nos", "nas"}
    palavras = [w for w in t.split()
                if w.lower() not in vazias
                and not re.fullmatch(r"[.,;:!?()\-]+", w)]
    t = " ".join(palavras)
    t = re.sub(r"\s+", " ", t).strip(" .,;:-")
    return t[:80]


def _consultas_produto(criterios: dict, texto: str) -> list:
    base = [criterios.get("categoria", ""),
            " ".join(criterios.get("marcas", [])[:2])]
    specs = criterios.get("specs", {}) or {}
    orc = criterios.get("orcamento", {}) or {}
    detalhe = ""
    if specs.get("ram_fisica_gb"):
        detalhe += f" {specs['ram_fisica_gb']}GB RAM"
    if specs.get("armazenamento_gb"):
        detalhe += f" {specs['armazenamento_gb']}GB"
    ref = _termo_referencia(texto)
    if ref and orc.get("max"):
        ref = re.sub(r"\b(?:at[eé]|abaixo\s+de|menos\s+de|no\s+m[aá]ximo)"
                     r"\s*R?\$?\s*[\d.,]+", " ", ref, flags=re.IGNORECASE)
        ref = re.sub(r"\s+", " ", ref).strip(" .,;:-")
    nucleo = " ".join(t for t in base if t).strip() or ref or (texto or "")[:80]
    if ref:
        consultas = [f"{ref} comprar oferta".strip()]
        if orc.get("max"):
            consultas.append(f"{ref} preço até {orc['max']:g}".strip())
        else:
            consultas.append(f"melhor {ref} comprar Brasil".strip())
    else:
        consultas = [f"{nucleo}{detalhe} comprar oferta".strip()]
        if orc.get("max"):
            consultas.append(f"{nucleo}{detalhe} preço até {orc['max']:g}".strip())
        else:
            consultas.append(f"melhor {nucleo}{detalhe} comprar Brasil".strip())
    vistos, final = set(), []
    for q in consultas:
        chave = q.lower()
        if q and chave not in vistos:
            vistos.add(chave)
            final.append(q)
    return final[:2]


def _mesmo_recurso(a: str, b: str) -> bool:
    """As duas URLs apontam para o mesmo recurso? (host+caminho normalizados)

    Ignora www., barra final, query e âncora — diferenças que não mudam a
    página. Esquema é ignorado de propósito (http→https é o mesmo recurso).
    """
    def _norm(u: str) -> str:
        try:
            p = urllib.parse.urlsplit((u or "").strip())
        except ValueError:
            return ""
        host = (p.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        caminho = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
        return f"{host}{caminho}" if host else ""
    na, nb = _norm(a), _norm(b)
    return bool(na) and na == nb


def _recuperar_ofertas(url: str, titulo: str, baixar_fn=None,
                       consulta: str = "") -> list:
    """Extrai produtos estruturados de 1 página, com verificação honesta.

    V5.5: a página baixada é avaliada por `source_check.avaliar_pagina`
    (sem novo download). Produto de página de listagem/categoria só entra
    quando o dado estruturado traz a URL do item — e o card marca o link
    como NÃO verificado (a página do item não foi aberta). Página sem
    sinais de produto nunca vira card (vira fonte).
    """
    try:
        if baixar_fn is not None:
            rec = baixar_fn(url)
            final = rec.get("final", url) if isinstance(rec, dict) else url
            pagina = rec.get("texto", "") if isinstance(rec, dict) else ""
            if not pagina or "<" not in pagina:
                return []
        else:
            final, pagina = research.baixar(url, timeout=6.0)
    except research.ResearchErro as exc:
        log.info("shopping: página ignorada (%s): %s", exc.codigo, url[:80])
        return []
    except Exception as exc:
        log.info("shopping: página ignorada (%s): %s", type(exc).__name__, url[:80])
        return []
    try:
        aval = source_check.avaliar_pagina(
            pagina, final, consulta=consulta or titulo,
            esperado={"tipo": "produto"})
    except Exception:
        aval = {}
    listagem = aval.get("codigo") == "listagem_nao_produto"
    if aval.get("codigo") == "produto_removido":
        # HTTP 200 dizendo que o produto não existe mais: página ignorada
        # por inteiro (nem JSON-LD residual vira card) — soft 404 é fonte,
        # nunca oferta.
        log.info("shopping: página de produto removido/indisponível: %s (%s)",
                 url[:80], str(aval.get("motivo") or "")[:80])
        return []
    saidas = []
    try:
        for ext in extrair_ofertas_jsonld(pagina):
            ext["origem_preco"] = "jsonld"
            url_item = ext.get("url_produto") or ""
            if listagem:
                if not url_item or source_check.url_de_listagem(url_item):
                    continue  # listagem sem link próprio do item → fonte
                val = {"veredito": "nao_verificado", "codigo": "item_de_listagem",
                       "motivo": "item extraído de listagem; página do item não aberta"}
            elif url_item and not _mesmo_recurso(url_item, final):
                # O veredito vale para a página ABERTA; o link do card aponta
                # para outra página (não aberta) → nunca marcar como verificado.
                val = {"veredito": "nao_verificado", "codigo": "item_nao_aberto",
                       "motivo": "link do item declarado na página analisada; "
                                 "a página do item não foi aberta"}
            else:
                val = aval
            try:
                saidas.append(montar_produto(ext, url, final, titulo,
                                             validacao=val, url_item=url_item))
            except Exception:
                continue
        if not saidas and not listagem:
            og = extrair_opengraph(pagina)
            if og.get("nome") and aval.get("veredito") in ("verificado", "parcial"):
                if og["ofertas_ld"][0].get("preco_confirmado"):
                    og["origem_preco"] = "opengraph"
                try:
                    saidas.append(montar_produto(og, url, final, titulo,
                                                 validacao=aval))
                except Exception:
                    pass
    except Exception:
        return []
    return saidas


def verificar_imagens(produtos: list, maximo: int = 3, timeout: float = 5.0,
                      abrir=None, workers: int = 3) -> list:
    """Valida até `maximo` imagens (formato real, dimensões, tamanho).

    Reprovar (conteúdo não-imagem, pixel de rastreador) limpa a imagem para
    o card mostrar "sem foto" em vez de imagem quebrada. Não verificado
    (rede/bloqueio) mantém a imagem e fica registrado. Nunca inventa.
    """
    from concurrent.futures import ThreadPoolExecutor
    alvos = [p for p in (produtos or [])
             if re.match(r"^https?://", (p.get("imagem") or "").strip(), re.I)]
    alvos = alvos[:max(0, int(maximo))]
    if not alvos:
        return produtos or []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(alvos))),
                            thread_name_prefix="juliaimg") as pool:
        futs = [(p, pool.submit(source_check.validar_imagem, (p.get("imagem") or "").strip(),
                                timeout=timeout, abrir=abrir))
                for p in alvos]
        for p, fut in futs:
            try:
                res = fut.result()
            except Exception:
                continue
            if not isinstance(res, dict):
                continue
            p["imagem_veredito"] = res.get("veredito", "") or ""
            if res.get("veredito") == "reprovado":
                p["imagem_motivo"] = _limpa(res.get("motivo"), 120)
                p["imagem"] = ""
    return produtos or []


def _resumo_verificacao(produtos: list, descartes: list = None,
                        alternativas: list = None) -> dict:
    """Contagem honesta de vereditos (link e imagem) dos produtos exibidos.

    FASE 4 (aditivo): com `descartes`/`alternativas`, conta também os
    códigos de exclusão (`excluido_codigos`) que mais derrubaram anúncios —
    sem alterar chamadas antigas."""
    links = {v: 0 for v in source_check.VEREDITOS}
    imagens = {v: 0 for v in source_check.VEREDITOS}
    for p in produtos or []:
        v = p.get("link_veredito") or ""
        if v in links:
            links[v] += 1
        iv = p.get("imagem_veredito") or ""
        if iv in imagens:
            imagens[iv] += 1
    links["total"] = sum(links[v] for v in source_check.VEREDITOS)
    imagens["total"] = sum(imagens[v] for v in source_check.VEREDITOS)
    resumo = {"links": links, "imagens": imagens}

    def _por_codigo(itens):
        cont: dict = {}
        for it in itens or []:
            for c in it.get("excluido_codigos") or []:
                cont[c] = cont.get(c, 0) + 1
        return dict(sorted(cont.items(), key=lambda kv: (-kv[1], kv[0])))

    if descartes is not None:
        resumo["descartes_por_codigo"] = _por_codigo(descartes)
    if alternativas is not None:
        resumo["alternativas_por_codigo"] = _por_codigo(alternativas)
    return resumo


def pesquisar(db, owner: str, texto: str, conv: str = "",
              buscar_fn=None, baixar_fn=None,
              progresso=None, teto_paginas: int = MAX_PAGINAS,
              criterios_base: dict | None = None, usar_cache: bool = True) -> dict:
    """Pipeline completo. `progresso(fase, detalhe)` emite eventos reais."""
    from concurrent.futures import ThreadPoolExecutor
    criterios = extrair_criterios(texto)
    if criterios_base is not None:
        # Explicit follow-up edits override only the fields the user supplied.
        import copy
        base = copy.deepcopy(criterios_base)
        for key in ('orcamento','specs'):
            base[key] = {**base.get(key,{}), **criterios.get(key,{})}
        for key in ('categoria','marcas'):
            if criterios.get(key):base[key]=criterios[key]
        base['texto'] = texto[:200]
        criterios = base
    consulta = (criterios.get("categoria", "") + " " +
                " ".join(criterios.get("marcas", []))).strip() or (texto or "")[:80]

    def _prog(fase, detalhe=""):
        try:
            if progresso:
                progresso(fase, detalhe)
        except Exception:
            pass

    _prog("buscando", consulta)
    em_cache = consulta_em_cache(db, owner, consulta) if usar_cache else None
    if em_cache is not None:
        return em_cache

    consultas = _consultas_produto(criterios, texto)
    achados, vistas, etapas_prov = [], set(), []
    for q in consultas:
        parcial, detapas = buscar_com_fallback(q, buscar_fn=buscar_fn)
        etapas_prov.extend(f"{q[:40]}: {e}" for e in detapas)
        for a in parcial[:12]:
            if a.get("url") and a["url"] not in vistas:
                vistas.add(a["url"])
                if "_consulta" not in a:
                    a["_consulta"] = q
                achados.append(a)
    if not achados:
        resultado = {"produtos": [], "fontes": [], "criterios": criterios,
                     "total_bruto": 0, "excluidos": [], "de_cache": False,
                     "verificado_em": agora_iso(), "erro": "provedor_indisponivel",
                     "etapas_provedores": etapas_prov[:8]}
        salvar_consulta(db, owner, conv, consulta, criterios, resultado)
        return resultado

    _prog("identificando", f"{len(achados)} anúncios candidatos")
    # Itens da API oficial já vêm estruturados: montagem direta, sem
    # visita a página. Demais URLs passam pela extração JSON-LD/OG.
    brutos: list = []
    paginas = []
    for a in achados[:teto_paginas + 4]:
        if a.get("origem") == "mlb" and isinstance(a.get("mlb"), dict):
            try:
                extraido = produto_de_mlb(a["mlb"])
                if extraido:
                    brutos.append(montar_produto(
                        extraido, a["url"], a["url"], "Mercado Livre (API oficial)"))
                    continue
            except Exception as exc:
                log.info("shopping: item mlb ignorado (%s)", type(exc).__name__)
        paginas.append(a)
    alvos = paginas[:teto_paginas]
    _prog("consultando", f"{len(alvos)} páginas")
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="juliashop") as pool:
        futs = {pool.submit(_recuperar_ofertas, a["url"], a.get("titulo", ""),
                            baixar_fn, a.get("_consulta", "")): a for a in alvos}
        for fut, a in futs.items():
            try:
                brutos.extend(fut.result())
            except Exception as exc:
                log.info("shopping: extração falhou (%s)", type(exc).__name__)
    _prog("extraindo", f"{len(brutos)} ofertas estruturadas")
    dedup = deduplicar(brutos)
    _prog("validando", f"{len(dedup)} modelos únicos")
    dentro, fora = aplicar_filtros(dedup, criterios)
    produtos = dentro[:MAX_PRODUTOS]
    alternativas = separar_alternativas(fora, criterios)
    ids_alt = {a.get("id") for a in alternativas}
    duros = [p for p in fora if p.get("id") not in ids_alt]
    if baixar_fn is None and produtos:
        _prog("verificando", "imagens reais dos produtos")
        # V5.7: valida a imagem de TODOS os cards exibidos (até MAX_PRODUTOS).
        verificar_imagens(produtos, maximo=MAX_PRODUTOS)
    _prog("organizando", f"{len(produtos)} recomendações"
          + (f", {len(alternativas)} alternativas" if alternativas else ""))
    fontes = [{"id": f"S{i + 1}", "titulo": (a.get("titulo") or "")[:160],
               "url": a.get("url", "")[:500]}
              for i, a in enumerate(achados[:8])]
    resultado = {"produtos": produtos, "alternativas": alternativas,
                 "fontes": fontes, "criterios": criterios,
                 "total_bruto": len(brutos), "excluidos": duros[:6],
                 "verificacao": _resumo_verificacao(
                     produtos + alternativas, duros, alternativas),
                 "de_cache": False, "verificado_em": agora_iso(),
                 "etapas_provedores": etapas_prov[:8]}
    salvar_consulta(db, owner, conv, consulta, criterios, resultado)
    return resultado


# ── Comparação determinística ──────────────────────────────────────────

def comparar(produtos: list) -> list:
    """Linhas {label, valores[], melhor}. Sem benchmarks inventados."""
    linhas = []
    if not produtos:
        return linhas
    precos = [p["preco"] for p in produtos if p.get("preco") is not None]
    linhas.append({"label": "Preço", "valores": [p.get("preco_texto", PRECO_NAO_CONFIRMADO)
                                                 for p in produtos],
                    "melhor": 0 if precos and min(precos) == (produtos[0].get("preco")) else -1})
    linhas.append({"label": "Loja", "valores": [p.get("loja", "—") or "—" for p in produtos],
                    "melhor": -1})
    avals = []
    for p in produtos:
        a = p.get("avaliacao")
        avals.append(f"{a:.1f}★" + (f" ({p.get('n_avaliacoes')})" if p.get("n_avaliacoes") else "")
                     if isinstance(a, (int, float)) else "não informada")
    linhas.append({"label": "Avaliação", "valores": avals, "melhor": -1})
    disp_map = {"em_estoque": "Em estoque", "sem_estoque": "Sem estoque",
                "estoque_limitado": "Estoque limitado",
                "pre_venda": "Pré-venda", "desconhecida": "Não informada"}
    linhas.append({"label": "Disponibilidade",
                    "valores": [disp_map.get(p.get("disponibilidade", ""), "Não informada")
                                for p in produtos], "melhor": -1})
    chaves = []
    for p in produtos:
        for k in (p.get("specs", {}) or {}):
            if k not in chaves:
                chaves.append(k)
    for k in chaves[:8]:
        linhas.append({"label": k.replace("_", " ").title(),
                        "valores": [(p.get("specs", {}) or {}).get(k, "—") or "—"
                                    for p in produtos], "melhor": -1})
    nome_menor = ("Vantagem: menor preço confirmado"
                  if len(precos) >= 2 else "Vantagem: — (preços insuficientes)")
    linhas.append({"label": "Vantagens",
                    "valores": [nome_menor if p.get("preco") is not None and precos
                                and p["preco"] == min(precos) else "—" for p in produtos],
                    "melhor": -1})
    linhas.append({"label": "Limitações",
                    "valores": ["Preço não confirmado na página" if not p.get("preco_confirmado")
                                else ("Imagem não disponível" if not p.get("imagem") else "—")
                                for p in produtos], "melhor": -1})
    return linhas


# ── Grounding para o LLM (texto; cards vão no fence determinístico) ───

def _link_do_produto(p: dict) -> str:
    return p.get("url_item") or p.get("url_final") or p.get("url", "") or ""


def _selo_verificacao(p: dict) -> str:
    """Rótulo curto e honesto do estado do link (nunca "ok" sem verificação)."""
    if p.get("item_de_listagem"):
        return "link do item veio de listagem (página do item NÃO aberta)"
    if p.get("link_codigo") == "item_nao_aberto":
        return "link do item não foi aberto (declarado em outra página)"
    v = p.get("link_veredito") or ""
    return {"verificado": "página verificada",
            "parcial": "verificação parcial",
            "reprovado": "link REPROVADO — não indicar como página de compra",
            "nao_verificado": "link não verificado"}.get(v, "link não verificado")


def bloco_para_llm(resultado: dict) -> str:
    """Bloco system com ofertas verificadas. Sem dado → ordem de honestidade."""
    prods = (resultado or {}).get("produtos", [])
    alts = (resultado or {}).get("alternativas", []) or []
    de_cache = bool((resultado or {}).get("de_cache"))
    quando = _data_br_curta((resultado or {}).get("verificado_em", ""))
    # V5.7: cache é histórico — o bloco declara a idade e proíbe apresentar
    # como "verificado agora" (preço/link podem ter mudado desde a consulta).
    if de_cache:
        estado = ("consulta reaproveitada do cache local — verificação original em "
                  + (quando or "data desconhecida")
                  + "; cite essa data e nunca como verificação de agora")
    else:
        estado = "executada agora"
    if not prods:
        linhas = [f"RESULTADO DE PESQUISA DE PRODUTOS ({estado}): nenhuma "
                  "oferta atende a TODOS os critérios com dados estruturados "
                  "verificáveis (preço/imagem)."]
        if alts:
            linhas.append("OPÇÕES PRÓXIMAS (NÃO atendem a tudo; cite SEMPRE as "
                          "diferenças e nunca como se atendessem):")
            for a in alts[:3]:
                linhas.append(
                    f"- {a.get('nome', '')[:120]} | {a.get('preco_texto', PRECO_NAO_CONFIRMADO)}"
                    f" | loja: {a.get('loja', '')} | {_link_do_produto(a)}"
                    f" | diferenças: {a.get('diferencas', '')}")
        linhas.append("Diga com honestidade o que faltou e peça um modelo mais "
                      "específico. PROIBIDO inventar produtos, preços, lojas, "
                      "fotos, avaliações ou links.")
        return "\n".join(linhas)
    if de_cache:
        linhas = ["RESULTADO DE PESQUISA DE PRODUTOS (consulta reaproveitada do "
                  "cache local — verificação original em "
                  + (quando or "data desconhecida")
                  + "; cite essa data e nunca como verificação de agora; só cite "
                  "ESTES produtos/preços/lojas/links; os cards visuais serão "
                  "anexados pela ferramenta):"]
    else:
        linhas = ["RESULTADO DE PESQUISA DE PRODUTOS (dados verificados agora; "
                  "só cite ESTES produtos/preços/lojas/links; os cards visuais "
                  "serão anexados pela ferramenta):"]
    for i, p in enumerate(prods[:6]):
        specs = ", ".join(f"{k}={v}" for k, v in
                          list((p.get("specs", {}) or {}).items())[:6])
        linhas.append(
            f"- [{i + 1}] {p.get('nome', '')} | {p.get('preco_texto', PRECO_NAO_CONFIRMADO)}"
            f" | loja: {p.get('loja', '')} | link: {_link_do_produto(p)}"
            f" | {_selo_verificacao(p)}"
            f" | aval: {p.get('avaliacao') if p.get('avaliacao') is not None else 'não informada'}"
            f" | disp: {p.get('disponibilidade', '')}"
            + (f" | specs: {specs}" if specs else ""))
    if alts:
        linhas.append("OPÇÕES PRÓXIMAS DO PEDIDO (NÃO atendem a todos os critérios; "
                       "cite SEMPRE as diferenças, nunca como se atendessem):")
        for a in alts[:3]:
            linhas.append(
                f"- {a.get('nome', '')[:120]} | {a.get('preco_texto', PRECO_NAO_CONFIRMADO)}"
                f" | loja: {a.get('loja', '')} | {_link_do_produto(a)}"
                f" | diferenças: {a.get('diferencas', '')}")
    for ex in (resultado or {}).get("excluidos", [])[:3]:
        linhas.append(f"- EXCLUÍDO (explique se citar): {ex.get('nome', '')[:80]}"
                       f" ({ex.get('excluido_por', '')})")
    linhas.append("Apresente em texto curto; NÃO emita blocos jdui de produto.")
    return "\n".join(linhas)


# ── Fences JDUI determinísticos (dados reais; nunca JSON bruto) ──────

COMPONENTES_PRODUTO = ("productcard", "productgrid", "productcompare",
                       "productdetails", "productgallery")


def _jdui_produto(p: dict) -> dict:
    return {
        "nome": p.get("nome", "")[:160],
        "marca": p.get("marca", "")[:80],
        "modelo": p.get("modelo", "")[:80],
        "variante": p.get("variante", "")[:80],
        "imagem": p.get("imagem", "")[:500],
        "preco": p.get("preco_texto", PRECO_NAO_CONFIRMADO)[:40],
        "preco_valor": p.get("preco"),
        "moeda": p.get("moeda", "BRL")[:3],
        "loja": p.get("loja", "")[:80],
        "url": _link_do_produto(p)[:500],
        "specs": {str(k)[:40]: str(v)[:120]
                  for k, v in list((p.get("specs", {}) or {}).items())[:12]},
        "avaliacao": p.get("avaliacao"),
        "n_avaliacoes": p.get("n_avaliacoes"),
        "disponibilidade": p.get("disponibilidade", "desconhecida"),
        "verificado_em": _data_br_curta(p.get("verificado_em", "")),
        "link_veredito": (p.get("link_veredito") or "")[:24],
        "link_motivo": (p.get("link_motivo") or "")[:120],
        "item_de_listagem": bool(p.get("item_de_listagem")),
        "imagem_veredito": (p.get("imagem_veredito") or "")[:24],
        "imagem_motivo": (p.get("imagem_motivo") or "")[:120],
        "ofertas": [{
            "loja": (o.get("loja", "") or "")[:80],
            "preco": o.get("preco_texto", PRECO_NAO_CONFIRMADO)[:40],
            "url": (o.get("url", "") or "")[:500],
        } for o in (p.get("ofertas", []) or [])[:6]],
    }


def _data_br_curta(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (iso or "")[:10])
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return (iso or "")[:10]


def _sources_de(fontes: list) -> list:
    out = []
    for i, f in enumerate(fontes or []):
        fid = f.get("id") or f"S{i + 1}"
        out.append({"id": str(fid)[:100], "title": (f.get("titulo", "") or "")[:160],
                    "url": (f.get("url", "") or "")[:500]})
        if len(out) >= 20:
            break
    return out


def fence_resultado(resultado: dict) -> str:
    """1 produto → productcard; vários → productgrid; vazio → ''."""
    import jdui
    prods = (resultado or {}).get("produtos", [])
    if not prods:
        return ""
    fontes = _sources_de((resultado or {}).get("fontes", []))
    if len(prods) == 1:
        msg = {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "productcard",
             "props": {"produto": _jdui_produto(prods[0]), "sources": fontes}}]}
    else:
        msg = {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "productgrid",
             "props": {"title": "Opções encontradas",
                       "items": [_jdui_produto(p) for p in prods[:6]],
                       "sources": fontes}}]}
    ok, _, _ = jdui.validar_mensagem(msg)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(msg, ensure_ascii=False) + "\n```"


def fence_comparacao(produtos: list, fontes: list | None = None) -> str:
    """Tabela visual determinística entre 2..4 produtos."""
    import jdui
    alvos = (produtos or [])[:4]
    if len(alvos) < 2:
        return fence_resultado({"produtos": alvos, "fontes": fontes or []})
    msg = {"version": jdui.VERSION, "blocks": [
        {"type": "ui", "component": "productcompare",
         "props": {"title": "Comparativo",
                   "items": [_jdui_produto(p) for p in alvos],
                   "sources": _sources_de(fontes or [])}}]}
    ok, _, _ = jdui.validar_mensagem(msg)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(msg, ensure_ascii=False) + "\n```"


def resumo_texto(resultado: dict) -> str:
    """Texto Markdown do chat (cards vão no fence; sem JSON bruto)."""
    prods = (resultado or {}).get("produtos", [])
    alts = (resultado or {}).get("alternativas", []) or []
    crit = (resultado or {}).get("criterios", {}) or {}
    if not prods:
        if (resultado or {}).get("erro") == "provedor_indisponivel":
            return ("Não consegui consultar ofertas agora (provedor indisponível). "
                    "Tente de novo em instantes. 🔍")
        if alts:
            linhas = [f"Encontrei {len(alts)} opção(ões), mas **nenhuma atende a "
                      "todos os critérios**. Próximas do pedido (com as diferenças):"]
            for a in alts[:3]:
                linhas.append(f"- **{a.get('nome', '')[:80]}** — "
                               f"{a.get('preco_texto', PRECO_NAO_CONFIRMADO)}"
                               f" · {a.get('loja', '')}"
                               f"\n  _diferenças: {a.get('diferencas', '')}_")
            return "\n".join(linhas)
        return ("Pesquisei anúncios, mas nenhuma página trouxe dados estruturados "
                "confiáveis (preço/imagem) para montar cards. Me diga um modelo "
                "específico que eu aprofundo a busca. 🔍")
    cat = crit.get("categoria") or "produtos"
    todos_ok = all(p.get("link_veredito") == "verificado" for p in prods)
    cabeca = (f"Encontrei **{len(prods)}** {cat} com dados verificados:"
              if todos_ok else
              f"Encontrei **{len(prods)}** {cat} com dados estruturados reais:")
    linhas = [cabeca]
    for p in prods:
        marca = ""
        if p.get("item_de_listagem") or p.get("link_veredito") in ("nao_verificado", "reprovado"):
            marca = " · _link não verificado_"
        linhas.append(f"- **{p['nome']}** — {p.get('preco_texto', PRECO_NAO_CONFIRMADO)}"
                       f" · {p.get('loja', '')}{marca}")
    for a in alts[:3]:
        linhas.append(f"- _Próxima do pedido_: **{a.get('nome', '')[:60]}** — "
                       f"{a.get('preco_texto', PRECO_NAO_CONFIRMADO)}"
                       f" _({a.get('diferencas', '')})_")
    for ex in (resultado or {}).get("excluidos", [])[:3]:
        linhas.append(f"- _{ex.get('nome', '')[:60]}_: fora ({ex.get('excluido_por', '')})")
    if (resultado or {}).get("de_cache"):
        linhas.append(f"\n_Preços de consulta anterior (verificados em "
                       f"{_data_br_curta((resultado or {}).get('verificado_em', ''))})._")
    return "\n".join(linhas)


_RX_FENCE = re.compile(r"```jdui\s*\n([\s\S]*?)(?:```|$)", re.IGNORECASE)


def remover_fences_produto(texto: str) -> str:
    """Remove fences ```jdui do modelo que usem componentes de produto.

    Os cards verdadeiros vêm da ferramenta (dados verificados); o modelo
    NÃO deve emitir productcard/productgrid/... com dados inventados.
    """
    def _trocar(m):
        try:
            obj = json.loads((m.group(1) or "").strip())
        except (ValueError, TypeError):
            return m.group(0)
        blocos = obj.get("blocks") if isinstance(obj, dict) else None
        if isinstance(blocos, list) and any(
                isinstance(b, dict) and b.get("component") in COMPONENTES_PRODUTO
                for b in blocos):
            return ""
        return m.group(0)
    limpo = _RX_FENCE.sub(_trocar, texto or "")
    return re.sub(r"\n{3,}", "\n\n", limpo).strip()


# ── Follow-ups (reusam última consulta; sem nova busca) ─────────────────
_FOLLOWUP_RESUMO = re.compile(
    r"(mais barat|menor pre|ordena|orden|filtra|s[oó] os|apenas|quero apenas|"
    r"outras lojas|outros modelos|quais lojas|onde tem|tem em estoque|"
    r"qual tem mais|qual o melhor|melhor custo|segunda op|terceira)", re.IGNORECASE)

_FOLLOWUP_COMPARE = re.compile(
    r"(compare|compar|versus|\bvs\b|diferen).{0,30}(dois primeiros|primeiros|"
    r"1 e 2|esses dois|entre eles)|^(compare os dois)", re.IGNORECASE)


def eh_followup(texto: str) -> bool:
    t = _sem_acentos(texto or "")
    return bool(_FOLLOWUP_RESUMO.search(texto or "") or
                _FOLLOWUP_COMPARE.search(texto or "") or
                ("compar" in t and "os dois" in t))


_FOLLOWUP_FOTOS = re.compile(
    r"(\btem fotos?\b|\bver as (fotos?|imagens?)\b|\bquero (ver )?(as )?(fotos?|imagens?)\b|"
    r"\bmostra(r)? (as )?(fotos?|imagens?)\b|"
    r"\bmanda(r)? (as |uma )?(fotos?|imagens?)\b|"
    r"\b(fotos?|imagens?) (deles|delas|desses|dessas)\b|"
    r"\b(fotos?|imagens?) (dos?|das?) (produtos?|modelos?|itens|resultados|opções|opcoes)\b)",
    re.IGNORECASE)


def quer_fotos(texto: str) -> bool:
    """Pedido de fotos ligado a produtos de uma consulta anterior.

    Nunca dispara busca nova: o worker reusa a última consulta
    (determinístico, com cards e imagens verificadas); sem consulta
    anterior, o fluxo normal segue (LLM/imagem)."""
    return bool(_FOLLOWUP_FOTOS.search(texto or ""))


def responder_followup(db, owner: str, conv: str, texto: str) -> dict | None:
    """Retorna {texto, fence} ou None (sem consulta anterior)."""
    ultima = ultima_consulta(db, owner, conv)
    if not ultima:
        return None
    prods = (ultima.get("resultado", {}) or {}).get("produtos", [])
    if not prods:
        return None
    t = (texto or "").lower()
    if _FOLLOWUP_COMPARE.search(texto or "") or ("compar" in t and "dois" in t):
        alvos = prods[:2]
        if len(alvos) < 2:
            return None
        linhas_txt = [f"**{alvos[0]['nome']}** ({alvos[0]['preco_texto']}) vs "
                       f"**{alvos[1]['nome']}** ({alvos[1]['preco_texto']})"]
        return {"texto": "\n".join(linhas_txt),
                "fence": fence_comparacao(alvos),
                "produtos": alvos}
    ordenados = list(prods)
    if re.search(r"mais barat|menor pre", t):
        ordenados.sort(key=lambda p: (p.get("preco") is None, p.get("preco") or 0))
        cab = "Do mais barato ao mais caro:"
    elif re.search(r"melhor avali|maior nota", t):
        ordenados.sort(key=lambda p: (p.get("avaliacao") is None),
                       reverse=False)
        ordenados.sort(key=lambda p: -(p.get("avaliacao") or -1))
        cab = "Por avaliação:"
    elif re.search(r"mais mem|mais ram", t):
        ordenados.sort(key=lambda p: -((_ram_do_produto(p) or (0, 0))[0]))
        cab = "Por memória RAM (física primeiro):"
    elif re.search(r"fotos?|imagens?", t):
        ordenados.sort(key=lambda p: (not p.get("imagem"),))  # com foto primeiro
        cab = "Opções guardadas da última pesquisa (com foto primeiro):"
    else:
        cab = "Opções guardadas da última pesquisa:"
    linhas = [cab] + [f"- **{p['nome']}** — {p['preco_texto']} ({p.get('loja', '')})"
                       for p in ordenados[:6]]
    return {"texto": "\n".join(linhas),
            "fence": fence_resultado({**ultima["resultado"], "produtos": ordenados[:6]}),
            "produtos": ordenados[:6]}
