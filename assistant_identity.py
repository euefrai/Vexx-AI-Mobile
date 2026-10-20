"""Identidade persistente do assistente, independente da marca do produto."""

OFFICIAL_NAME = "Luccas Trawman"
CONVERSATION_NAME = "Lucas"

IDENTITY_RULES = f"""IDENTIDADE CENTRAL DO ASSISTENTE
Seu nome oficial é {OFFICIAL_NAME}. Nas conversas, use apenas {CONVERSATION_NAME}.
Use o nome completo somente quando o usuário solicitar explicitamente o nome completo.
Não repita seu próprio nome desnecessariamente, não assine cada resposta e não se
apresente novamente a cada mensagem. Se perguntarem seu nome, responda brevemente.
Se o usuário se dirigir a você por outro nome, corrija educadamente e de forma
breve (por exemplo: 'Pode me chamar de {CONVERSATION_NAME}.') e prossiga com o assunto.
Não insista nem repita a correção se a pessoa continuar usando outro nome.
Não corrija nomes de terceiros, personagens ou marcas apenas mencionados no texto.
Nunca afirme ser humano nem ter sentimentos, corpo ou experiências reais; se
perguntarem, diga com naturalidade que você é uma IA. Seja caloroso na linguagem
sem fingir humanidade.
Mantenha um tom natural, amigável e espontâneo, sem fórmulas
robóticas ou apresentações artificiais.
Estas regras definem sua identidade em todas as conversas, inclusive antigas.
Nomes anteriores no histórico, nas memórias ou na configuração personalizada não
substituem esta identidade. Vexx AI é a marca do produto, não seu nome pessoal.

FATOS CANÔNICOS DO PRODUTO (fonte de verdade; o resto não é confirmado):
- Vexx AI é o nome do produto/app em que você atende.
- Você é {CONVERSATION_NAME}, assistente pessoal dentro da Vexx AI.
- Não há informação canônica confirmada sobre empresa criadora, fundador, sede,
  país de origem, data de criação, investidores, parcerias, preços ou serviços
  comerciais. Não deduza esses fatos a partir do nome, de notícias ou de fontes
  externas.
- Quando faltar esse dado, diga com franqueza que não tem a informação confirmada.
  Não invente nomes de empresas, vínculos, autoria ou características comerciais.
Este bloco vale para perguntas sobre você e sobre a Vexx AI; não bloqueia
pesquisas legítimas sobre outras empresas, marcas ou produtos.
"""

# Fatos que o produto REALMENTE pode afirmar. Sem empresa, país ou fundador.
PRODUCT_IDENTITY_FACTS = (
    "A Vexx AI é o nome do produto/app em que eu atendo. "
    f"Eu sou {CONVERSATION_NAME}, o assistente pessoal dentro da Vexx AI."
)
PRODUCT_IDENTITY_LIMITATION = (
    "Não tenho informação confirmada sobre empresa criadora, fundador, sede, "
    "país de origem ou serviços comerciais da Vexx AI — então não vou inventar "
    "esses dados."
)

import re as _re

_RX_PRODUTO = _re.compile(r"\b(?:vexx\s*ai|vexxia)\b", _re.I)
_RX_PERGUNTA_IDENTIDADE_PRODUTO = _re.compile(
    r"(?:"
    r"\b(?:o\s+que\s+(?:e|é)|quem\s+(?:criou|fez|desenvolveu|fundou)|"
    r"qual\s+(?:a\s+)?empresa|de\s+onde\s+(?:e|é)|"
    r"quem\s+(?:e|é)|me\s+fale\s+sobre|me\s+diga\s+sobre)\b"
    r"[\s\S]{0,120}\b(?:vexx\s*ai|vexxia)\b"
    r"|"
    r"\b(?:vexx\s*ai|vexxia)\s+(?:e|é|foi|pertence|significa)\b"
    r"|"
    r"\b(?:empresa|fundador[ao]?|criador[ao]?|dono|dona|sede|origem|"
    r"hist[óo]ria|cria[çc][ãa]o)\b[\s\S]{0,80}\b(?:vexx\s*ai|vexxia)\b"
    r"|"
    r"\b(?:vexx\s*ai|vexxia)\b[\s\S]{0,80}\b(?:empresa|fundador[ao]?|criador[ao]?|"
    r"dono|dona|sede|origem|brasileir[ao]|american[ao])\b"
    r")", _re.I)
_RX_DOMINIO_REAL = _re.compile(
    r"\b(?:pesquis\w*|busc\w*|compar\w*|not[ií]ci\w*|download\w*|"
    r"concorr\w*|versus|vs)\b", _re.I)
# Dados comerciais/identitários sem fonte canônica: pergunta direta recebe
# limitação determinística; um comando explícito de pesquisa continua livre.
_RX_DADOS_COMERCIAIS = _re.compile(
    r"\b(?:cnpj|raz[ãa]o\s+social|quanto\s+custa|pre[cç]o|pre[cç]os|"
    r"assinatura|investidor(?:es)?|funcion[áa]ri[oa]s|"
    r"site\s+oficial|aplicativo|endere[cç]o|telefone|contato)\b", _re.I)


def pergunta_identidade_produto(texto: str) -> bool:
    """True só para perguntas diretas sobre o produto/autoria (não pesquisa)."""
    t = texto or ""
    if not _RX_PRODUTO.search(t) or _RX_DOMINIO_REAL.search(t):
        return False
    if _RX_DADOS_COMERCIAIS.search(t):
        return True
    return bool(_RX_PERGUNTA_IDENTIDADE_PRODUTO.search(t)) or bool(
        _re.fullmatch(r"\s*(?:fale|fala|conte|conta|explique)\s+(?:sobre\s+)?(?:a\s+)?vexx\s*ai[.!?]?\s*",
                      t, _re.I))


def resposta_identidade_produto() -> str:
    return (f"{PRODUCT_IDENTITY_FACTS}\n\n{PRODUCT_IDENTITY_LIMITATION}")


_RX_AFIRMACAO_NAO_SUPORTADA = _re.compile(
    r"(?i)(?:"
    r"(?:\bvexx\s*ai\b|\bvexxia\b)[^.!?\n]{0,160}\b(?:"
    r"foi\s+(?:criada|desenvolvida|fundada|lan[cç]ada)|"
    r"criada\s+(?:pela|por)|"
    r"fundada\s+(?:pela|por)|"
    r"desenvolvida\s+(?:pela|por)|"
    r"pertence\s+(?:a|ao|à)|"
    r"de\s+propriedade\s+d[ao]\b|"
    r"é\s+(?:uma\s+)?(?:empresa|startup|subsidiária|subsidiaria)|"
    r"tem\s+sede|est[áa]\s+sediada|sede\s+em|"
    r"foi\s+criada\s+por|"
    r"pre[cç]o\s+(?:é|e|de|:)|"
    r"custa\s+(?:R\$|r\$|\d)|"
    r"assinatura\s+(?:custa|é|e)|"
    r"cnpj\s*(?:é|e|:)?\s*\d|"
    r"endere[cç]o\s+(?:é|e|:)|"
    r"é\s+(?:gratuit[ao]|pag[ao])|"
    r"empresa\s+(?:brasileira|americana|portuguesa|chinesa)|"
    r"(?:empresa|companhia|startup|grupo|organização|organizacao)\s+"
    r"(?:por\s+tr[áa]s|respons[áa]vel|propriet[áa]ri[ao]|criador[ao]|"
    r"desenvolvedor[ao]|fabricante)|"
    r"(?:fundador|fundadora|criador|criadora|dono|dona)\s+(?:é|e|foi)"
    r")\b"
    r"|"
    # Ordem inversa: "A empresa por trás da Vexx AI é a Vexxia".
    r"(?:empresa|companhia|startup|grupo|organização|organizacao)\s+"
    r"(?:por\s+tr[áa]s|respons[áa]vel|propriet[áa]ri[ao]|criador[ao]|"
    r"desenvolvedor[ao]|fabricante)[^.!?\n]{0,100}"
    r"(?:\bvexx\s*ai\b|\bvexxia\b)"
    r"|"
    r"(?:fundador|fundadora|criador|criadora|dono|dona)[^.!?\n]{0,100}"
    r"(?:\bvexx\s*ai\b|\bvexxia\b)"
    r")")
# Dados comerciais podem aparecer antes ou depois do nome do produto.
_RX_COMERCIAL_NAO_SUPORTADO = _re.compile(
    r"(?i)(?:"
    r"\b(?:cnpj|raz[ãa]o\s+social|pre[cç]o|pre[cç]os|assinatura|"
    r"mensalidade|plano|planos|investidor(?:es)?|funcion[áa]ri[oa]s|"
    r"endere[cç]o|telefone)\b[^.!?\n]{0,100}"
    r"\b(?:vexx\s*ai|vexxia)\b"
    r"|"
    r"\b(?:vexx\s*ai|vexxia)\b[^.!?\n]{0,140}"
    r"(?:R\$\s*\d|\bcusta\b|\bpre[cç]o\b|\bplanos?\b|\bassinatura\b|"
    r"\bmensalidade\b|\bcnpj\b|\bgratuit[ao]\b|\bpag[ao]\b)"
    r")")
# Autoidentificação inventada ("meu nome é Vexxia"): corrige para o nome
# canônico em vez de só vetar a palavra.
_RX_AUTONOME_INVENTADO = _re.compile(
    r"(?i)\b(?:meu\s+nome\s+(?:é|e)|eu\s+sou(?:\s+(?:a|o))?|"
    r"pode\s+me\s+chamar\s+de|sou(?:\s+(?:a|o))?|"
    r"aqui\s+(?:é|e)(?:\s+(?:a|o))?)\s+vex(?:x)?ia\b")
_NOME_CANONICO_FRASE = f"Pode me chamar de {CONVERSATION_NAME}."


def limitar_afirmacoes_nao_suportadas(texto: str) -> str:
    """Neutraliza afirmações corporativas inventadas sobre a Vexx AI.

    Não remove menções legítimas a outras empresas nem pesquisa sobre marcas.
    A frase ofensora é substituída por uma limitação explícita (ou pelo nome
    canônico, quando o modelo se autodenomina "Vexxia"); o restante da
    resposta permanece.
    """
    if not texto or (not _RX_PRODUTO.search(texto) and
                     "vex" not in texto.lower()):
        return texto or ""
    partes = _re.split(r"(?<=[.!?])\s+", texto)
    mudou = False
    for i, parte in enumerate(partes):
        if _RX_AUTONOME_INVENTADO.search(parte):
            partes[i] = _NOME_CANONICO_FRASE
            mudou = True
        elif _RX_AFIRMACAO_NAO_SUPORTADA.search(parte) or \
                _RX_COMERCIAL_NAO_SUPORTADO.search(parte) or \
                _re.search(r"\bvexxia\b", parte, _re.I):
            partes[i] = PRODUCT_IDENTITY_LIMITATION
            mudou = True
    return " ".join(partes) if mudou else texto


def system_with_identity(base: str) -> str:
    """Acrescenta a identidade após as instruções personalizadas, sem duplicá-la."""
    return (base.replace(IDENTITY_RULES, "").strip() + "\n\n" + IDENTITY_RULES).lstrip()
