"""Intent Engine 2.0 (V5.1) — interpretação determinística de mensagens.

Produz estrutura validada: intenção principal, secundárias, entidades,
restrições (obrigatórias/proibidas/preferências/formato), referências,
correções, ambiguidades e ferramentas. Stdlib pura, sem LLM, sem rede.

 Decisões exigem MÚLTIPLAS evidências (nunca 1 palavra-chave isolada);
 sem evidência suficiente a intenção é `conversa`. Correções explícitas
 do usuário prevalecem sobre memórias antigas (sinalizadas, não aplicadas
 aqui). Valores sensíveis (senhas, CPF, saúde) nunca viram entidades.
"""
import re
import unicodedata

import shopping

INTENCOES = (    "conversa", "shopping", "pesquisa", "pesquisa_profunda",
    "estudo_prova", "estudo_aula", "estudo_reforco",
    "memoria", "calculo", "codigo", "imagem", "identidade",
    "projeto", "jdui", "pc_controle",
)

FERRAMENTAS_VALIDAS = (
    "llm", "shopping", "research", "research_deep", "learning",
    "memory", "deterministico", "jdui", "pc_controle",
)

def _norm(texto: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower())
                  if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem).strip()


def _ev(t: str, *pats: str) -> int:
    return sum(1 for p in pats if re.search(p, t))


def _produtos_re() -> str:
    cats = sorted((c for c in shopping.CATEGORIAS), key=len, reverse=True)
    base = "|".join(re.escape(c) for c in cats)
    plurais = "|".join(re.escape(c + "s") for c in cats if len(c) > 3)
    return f"(?:{base}|{plurais})"


_PROD = _produtos_re()

# Classes de evidência de compra: verbo, substantivo, preço, spec,
# condição, mídia. 2+ classes distintas roteiam; 1 sozinha não decide.
_CLS_SHOPPING = (
    ("verbo", r"(pesquis\w*|encontr\w*|procur\w*|busc\w*|recomend\w*|compar\w*|"
              r"onde comprar|vale a pena|custo beneficio|menor preco|"
              r"mais barat\w*|barat\w*|\boferta\b|promocao|quero (um|uma)|"
              r"qual |pesquisa de|busca de)"),
    ("substantivo", _PROD),
    ("preco", r"(r\$\s?\d|reais|\bbrl\b|ate r?\$?\s?\d|orcamento|mil\b)"),
    ("spec", r"(\d+\s?gb|\bram\b|\bssd\b|polegadas|\bpol\b|mah|\b5g\b|"
             r"\bnfc\b|[0-9]{2,3}hz|aro \d|octa|snapdragon|ryzen|\bi[3579]\b)"),
    ("condicao", r"(apenas (novos?|novas?|usados?)|\bnovos?\b|\busados?\b|"
                 r"lacrado|seminovo)"),
    ("midia", r"(fotos|imagens|com foto)"),
)


def _classes_shopping(t: str) -> tuple:
    achadas = [nome for nome, rx in _CLS_SHOPPING if re.search(rx, t)]
    return len(achadas), achadas


def _detectar_principal(t: str) -> tuple:
    """(intencao, evidencias[], secundarias[]). Múltiplas evidências exigidas."""
    cands: dict = {}

    def _reg(nome, *pats, peso: int = 1):
        n = _ev(t, *pats)
        if n:
            anterior, _ = cands.get(nome, (0, []))
            cands[nome] = (anterior + n * peso, list(pats))

    ncls, quais = _classes_shopping(t)
    if ncls:
        cands["shopping"] = (ncls, [f"classe:{q}" for q in quais])
    _reg("pesquisa_profunda",
         r"a fundo", r"aprofundad\w*", r"relatorio completo", r"dossie",
         r"verifique se", r"e verdade", r"checar fatos",
         r"compar\w* (as |os |de )?fontes")
    _reg("pesquisa",
         r"pesquis\w* (sobre|acerca|a|o|fundo)", r"busqu\w* (sobre|fontes|na)",
         r"ultimas noticias", r"noticia", r"fontes(\s+(confiaveis|reais))?",
         r"clima (em|de|hoje)|placar|resultado do jogo",
         r"o que (aconteceu|esta acontecendo)",
         r"(hoje|ontem|essa semana) (no|na|em)",
         r"(mundo|pais|brasil|governo|economia) hoje")
    _reg("estudo_prova",
         r"quiz|simulado|questionario|teste de conhecimento|perguntas e respostas",
         r"me (teste|avalie|prove)|prova (de|para)|crie (uma prova|questoes)")
    _reg("estudo_aula",
         r"\baula\b|me (ensine|explique)|explicar (melhor|mais)|"
         r"como funciona (o|a)|quero aprender|\bensine\b")
    _reg("estudo_reforco",
         r"reforco|revisao|rever (o|a)|estou errando|onde (erro|errei)|"
         r"dificuldade em|nao entendi|\bn entendi\b")
    _reg("memoria",
         r"lembre-se|lembre se|guarde (isso|que|aqui)|anote|nao esqueca|"
         r"o que voce (sabe|lembra|conhece)|mostre (sua|a sua) memoria|"
         r"esqueca|pode guardar|meus eventos|minha agenda|compromissos")
    _reg("calculo",
         r"quanto e\b|quanto custa|calcul\w*|porcentagem de|juros|"
         r"convert\w*|quanto fica|qual o total|soma de|media de")
    _reg("codigo",
         r"quero o codigo|mostre o codigo|crie uma funcao|funcao (em|que)|"
         r"codigo (em|para)|script (em|para)", peso=2)
    _reg("codigo",
         r"\bpython\b|\bcodigo\b|regex|\bsql\b|javascript|debugar|"
         r"erro (no|na|do) codigo|programa (em|que)")
    _reg("imagem",
         r"\b(imagem|foto|figura)\b.{0,30}(de|do|da|sobre)|mostre uma foto|"
         r"mande (uma |a )?foto|gere uma imagem")
    _reg("identidade",
         r"qual (e |eh )?(o seu|seu|teu) nome|como .* se chama|se apresente|"
         r"quem e voce|nome completo|voce e humano|tem sentimentos")
    _reg("projeto",
         r"continuar|continue|retomar|retome|volt\w*|onde param|estavamos fazendo|"
         r"aquele projeto|esse projeto|\bo projeto\b|meu projeto|continuacao")
    _reg("pc_controle",
         r"\bclique\b|abrir o programa|abra o (navegador|programa|word|excel)|"
         r"digite|pressione (a tecla|enter)|mova o mouse|captura de tela|"
         r"print da tela|controle (o|meu) (pc|computador)")
    _reg("jdui",
         r"em (forma de |formato de )?(tabela|planilha|grafico|quadro)|"
         r"grafico de (barras|pizza|linhas)|grade de produtos|"
         r"cards de produto|checklist|diagrama|fluxograma|"
         r"tabela comparativa|compar\w* lado a lado", peso=2)
    if not cands:
        return "conversa", [], []
    # Roteamento externo (pesquisa web, compra) exige 2+ evidências;
    # padrões fortes e locais valem com 1 (comportamento legado preservado;
    # pc_controle continua sugerido com 1 evidência — a autorização é
    # exigida na execução, não aqui).
    DEMOVER_1PT = ("pesquisa", "shopping", "jdui", "codigo")
    # Desempate: em pontos iguais, intenção local/segura vence a externa.
    ordenadas = sorted(cands.items(),
                       key=lambda kv: (kv[1][0], kv[0] not in DEMOVER_1PT),
                       reverse=True)
    melhor, (pontos, _) = ordenadas[0]
    if pontos >= 2 or melhor not in DEMOVER_1PT:
        evidencias = [f"{melhor}:{pontos}e"]
        secundarias = [n for n, (p, _) in ordenadas[1:4] if p >= 1]
        if melhor == "jdui":
            # Formato é modificador, não tarefa: tarefa com 2+ evidências
            # (ou 1 evidência forte local) vira principal; hipótese fraca
            # de ferramenta externa não rouba o formato.
            for n, (p, _) in ordenadas[1:4]:
                if n in ("shopping", "pesquisa", "pesquisa_profunda",
                         "estudo_prova", "estudo_aula", "estudo_reforco",
                         "memoria", "projeto", "calculo", "codigo") and (
                         p >= 2 or (p >= 1 and n not in DEMOVER_1PT)):
                    secs = ["jdui"] + [x for x in secundarias if x != "jdui"]
                    return n, [f"tarefa:{n}"], secs[:3]
        return melhor, evidencias, secundarias
    # 1 evidência fraca p/ ferramenta externa: conversa honesta + hipótese.
    secundarios = [n for n, _ in ordenadas[:2]]
    return "conversa", [], secundarios


_NUMERO_EXTENSO = {"uma": 1, "um": 1, "duas": 2, "dois": 2, "tres": 3,
                   "três": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
                   "oito": 8, "nove": 9, "dez": 10}


def _extrair_restricoes(t: str) -> dict:
    proibidas, obrigatorias, preferencias = [], [], []
    formato: dict = {}
    if re.search(r"nao (pesquise|busque)(?=\s*(,|;|\.|$|apenas|so\b|mas\b))", t):
        proibidas.append("pesquisar")
    if re.search(r"(sem usar a internet|nao use (a internet|o google)|offline)", t):
        proibidas.append("internet")
    for m in re.finditer(
            r"(?:nao quero|nao (?:me |nos |te )?use|nao utilize|nao (?:me |nos )?mostre|"
            r"nao traga|nao inclua|nao pesquise|nao busque|nada de|nem pensar em|"
            r"evite|proibido|sem)\s*,?\s*([a-zà-ú0-9 /.-]{2,60})", t):
        proibidas.append(m.group(1).strip(" .,")[:60])
    for m in re.finditer(
            r"(?:^|[,;.])\s*nada\s+([a-zà-ú]{3,30}(?:\s+[a-zà-ú]{2,30}){0,2})", t):
        proibidas.append(m.group(1).strip(" .,")[:60])
    if re.search(r"\bnao (pesquise|busque)\b", t) and \
            not any("pesquis" in p or "busca" in p for p in proibidas):
        proibidas.append("pesquisar")
    for m in re.finditer(
            r"(?:apenas|soment[eo]|s[oó]|exclusivamente|tem que (ter|ser)|"
            r"[eé] obrigat[oó]rio)\s+([a-zà-ú0-9 /.,-]{2,60})", t):
        obrigatorias.append(m.group(2).strip(" .,")[:60])
    m = re.search(r"(?:em|no maximo|máximo de|limite de)\s+(\d{1,2}|uma|um|duas|dois|tres|três|quatro|cinco)\s+linhas?", t)
    if m:
        bruto = m.group(1)
        formato["max_linhas"] = min(int(bruto) if bruto.isdigit()
                                    else _NUMERO_EXTENSO.get(bruto, 4), 40)
    elif re.search(r"\b(curto|curta|resumid[oa]|sucinto|direto ao ponto|em poucas palavras)\b", t):
        formato["max_linhas"] = 4
    elif re.search(r"\b(detalhad[oa]|completo|longo|aprofundad[oa])\b", t):
        formato["detalhe"] = "alto"
    if re.search(r"(com|mostre|mande|quero ver|inclua|ver)\s+(as?\s+)?(fotos|imagens|ilustracoes)", t):
        formato["midia"] = "imagens"
    if re.search(r"em tabela", t):
        formato["tabela"] = True
    for m in re.finditer(r"(?:prefiro|prefira|gosto mais de|melhor se)\s+([a-zà-ú0-9 /.,-]{2,60})", t):
        preferencias.append(m.group(1).strip(" .,")[:60])
    return {"obrigatorias": obrigatorias[:6], "proibidas": list(dict.fromkeys(proibidas))[:6],
            "preferencias": preferencias[:6], "formato": formato}


_CORRECAO_RE = re.compile(
    r"^(nao[,.]?\s+)?(eu quis dizer|quis dizer|quero dizer|foi mal|"
    r"digo\b|corrigindo|na verdade|esqueci de dizer|alias|desculp|errei)|"
    r"^nao,?\s+(era|e)\s")


def _eh_correcao(t: str) -> bool:
    return bool(_CORRECAO_RE.search(t))


def _extrair_referencias(t: str) -> dict:
    m = re.search(r"(os|as) (\d+|dois|tres|tr[eê]s|primeiros?)", t)
    if m and ("primeir" in t or m.group(2) in ("dois", "tres", "três", "2", "3")):
        n = {"dois": 2, "tres": 3, "três": 3, "2": 2, "3": 3}.get(m.group(2), 2)
        return {"tipo": "primeiros_n", "n": n}
    if re.search(r"\b(o|a) (ultim[oa]|terceir[oa]|segund[oa]|primeir[oa])\b", t):
        qual = re.search(r"(ultim[oa]|terceir[oa]|segund[oa]|primeir[oa])", t).group(1)
        return {"tipo": {"ultimo": "ultimo", "ultima": "ultimo"}.get(qual, qual), "n": 1}
    if re.search(r"\b(esses|essas|eles|elas|entre eles|desses)\b", t):
        return {"tipo": "selecao", "n": 0}
    if re.search(r"(mais barat\w*|menor preco|mais car\w*|maior preco|orden\w*)", t):
        return {"tipo": "ordenacao", "n": 0}
    if re.search(r"\b(isso|isto|aquilo|aquele|aquela|esse|essa)\b", t):
        return {"tipo": "anafórico", "n": 0}
    if re.search(r"(igual|mesmo).{0,15}(mas|por[eé]m|s[oó])", t):
        return {"tipo": "variacao", "n": 0}
    return {"tipo": None, "n": 0}


def _ambiguidades(t: str, intencao: str, entidades: dict, referencias: dict) -> list:
    out = []
    if intencao == "shopping" and not entidades.get("categoria"):
        out.append("categoria do produto não identificada")
    if intencao == "shopping" and not (entidades.get("orcamento") or {}):
        out.append("sem faixa de preço (buscar sem teto)")
    if referencias["tipo"] in ("selecao", "anafórico") and referencias["n"] == 0:
        out.append("referência depende de resultados anteriores")
    if _eh_correcao(t) and intencao == "conversa":
        out.append("correção sem pedido anterior claro")
    return out


def _ferramentas(intencao: str, secundarias: list, formato: dict,
                 podem_pesquisar: bool) -> list:
    mapa = {
        "shopping": ["shopping", "jdui", "llm"],
        "pesquisa": ["research", "llm"],
        "pesquisa_profunda": ["research_deep", "llm"],
        "estudo_prova": ["learning", "jdui", "llm"],
        "estudo_aula": ["learning", "llm"],
        "estudo_reforco": ["learning", "llm"],
        "memoria": ["memory", "llm"],
        "calculo": ["deterministico", "jdui", "llm"],
        "codigo": ["llm"],
        "imagem": ["llm"],
        "identidade": ["deterministico"],
        "projeto": ["deterministico", "memory", "llm"],
        "jdui": ["jdui", "llm"],
        "pc_controle": ["pc_controle"],
        "conversa": ["llm"],
    }
    ferramentas = list(mapa.get(intencao, ["llm"]))
    if intencao != "conversa":
        for sec in secundarias[:3]:
            for f in mapa.get(sec, ["llm"]):
                if f not in ferramentas:
                    ferramentas.append(f)
    if not podem_pesquisar:
        ferramentas = [f for f in ferramentas
                       if f not in ("shopping", "research", "research_deep")]
        if "deterministico" not in ferramentas and "llm" not in ferramentas:
            ferramentas.append("llm")
    if formato.get("midia") == "imagens" and "jdui" not in ferramentas:
        ferramentas.append("jdui")
    return [f for f in ferramentas if f in FERRAMENTAS_VALIDAS]


def analisar(texto: str, contexto: dict | None = None) -> dict:
    """Interpreta a mensagem. `contexto` opcional: {"ultimos_resultados":
    "shopping"|"research"|"learning"|None} — resolve follow-ups
    ("compare os dois primeiros") para a ferramenta anterior.
    Nunca levanta; sem evidência → conversa."""
    try:
        t = _norm(texto)
        if not t:
            return _vazio()
        intencao, evidencias, secundarias = _detectar_principal(t)
        restricoes = _extrair_restricoes(t)
        referencias = _extrair_referencias(t)
        ultimo = ((contexto or {}).get("ultimos_resultados") or "") if contexto else ""
        if intencao == "conversa" and referencias["tipo"] in (
                "primeiros_n", "selecao", "ultimo", "ordenacao") and ultimo in (
                "shopping", "research", "learning"):
            intencao = {"shopping": "shopping", "research": "pesquisa",
                        "learning": "estudo_reforco"}[ultimo]
            evidencias = [f"followup:{ultimo}"]
            secundarias = []
        correcao = _eh_correcao(t)
        if intencao == "conversa" and correcao and re.search(
                r"(meu (nome|foco|objetivo)|minha (meta|prova)|"
                r"aniversario|lembre|guarde|anote|esqueca)", t):
            intencao = "memoria"
            evidencias = ["correcao+memoria"]
        if intencao == "conversa" and referencias["tipo"] == "variacao" and \
                re.search(r"(python|codigo|funcao|\bsql\b|javascript)", t):
            intencao = "codigo"
            evidencias = ["variacao+codigo"]
        if intencao == "projeto" and re.match(
                r"^(isso mesmo|isso|sim|ok|certo|pode ser)[,. ]", t) and not re.search(
                r"(projeto|site|tcc|computador|\bpc\b|pesquisa|tarefa|trabalho)", t):
            intencao = "conversa"
            evidencias = []
            secundarias = ["projeto"]
        entidades: dict = {}
        if intencao == "shopping":
            try:
                crit = shopping.extrair_criterios(texto or "")
                entidades = {"categoria": crit.get("categoria", ""),
                             "marcas": crit.get("marcas", [])[:3],
                             "orcamento": crit.get("orcamento", {}) or {},
                             "specs": crit.get("specs", {}) or {}}
            except Exception:
                entidades = {}
        proib_txt = " ".join(restricoes["proibidas"])
        podem_pesquisar = not re.search(
            r"(pesquis|busca|internet|web|online|lojas?|ofertas?|precos?)", proib_txt)
        ambiguidades = _ambiguidades(t, intencao, entidades, referencias)
        formato = restricoes.get("formato", {})
        ferramentas = _ferramentas(intencao, secundarias, formato, podem_pesquisar)
        if evidencias and intencao != "conversa":
            conf = 0.95 if intencao in ("identidade", "memoria") else 0.85
        else:
            conf = 0.5 if secundarias else 0.3
        return {"intencao": intencao, "confianca": conf,
                "evidencias": evidencias[:4], "secundarias": secundarias[:3],
                "entidades": entidades, "restricoes": restricoes,
                "referencias": referencias, "correcao": correcao,
                "ambiguidades": ambiguidades[:4],
                "ferramentas": ferramentas,
                "podem_pesquisar": podem_pesquisar}
    except Exception:
        return _vazio()


def _vazio() -> dict:
    return {"intencao": "conversa", "confianca": 0.3, "evidencias": [],
            "secundarias": [], "entidades": {},
            "restricoes": {"obrigatorias": [], "proibidas": [],
                           "preferencias": [], "formato": {}},
            "referencias": {"tipo": None, "n": 0}, "correcao": False,
            "ambiguidades": [], "ferramentas": ["llm"],
            "podem_pesquisar": True}


# ── Validador de relevância da resposta (determinístico) ───────────────

_ACAO_ALEGADA_RE = (
    r"(pesquisei|busquei|encontrei|executei|fiz a busca|conclu[ií]|"
    r"rodei|verifiquei (nas|nos) fontes|analisei os dados)")

_CLAIM_VAGO_RE = r"(menor pre[cç]o da internet|melhor (produto|oferta) (do|da) (mercado|internet))"


def validar(intent: dict, resposta: str,
            evidencias: dict | None = None) -> dict:
    """Checa a resposta contra intenção/restrições. Retorna
    {violacoes:[{codigo, detalhe}], ok: bool}. Sem LLM; só regras literais."""
    ev = evidencias or {}
    violacoes = []
    texto = _norm(resposta or "")
    restricoes = (intent or {}).get("restricoes", {}) or {}
    formato = restricoes.get("formato", {}) or {}

    if not (resposta or "").strip():
        return {"violacoes": [{"codigo": "resposta_vazia",
                               "detalhe": "resposta sem conteúdo"}], "ok": False}

    for proib in restricoes.get("proibidas", [])[:6]:
        for palavra in _norm(proib).split():
            if len(palavra) < 4:
                continue
            idx = texto.find(palavra)
            if idx < 0:
                continue
            antes = texto[max(0, idx - 15):idx]
            if re.search(r"(nao|nunca|nem|sem|jamais)\b", antes):
                continue
            violacoes.append({"codigo": "restricao_proibida",
                              "detalhe": f"contém item proibido: {proib[:50]}"})
            break

    max_linhas = formato.get("max_linhas")
    if isinstance(max_linhas, int):
        n_linhas = len([l for l in (resposta or "").splitlines() if l.strip()])
        if n_linhas > max_linhas + 2:
            violacoes.append({"codigo": "formato_longo",
                              "detalhe": f"{n_linhas} linhas > {max_linhas} pedidas"})

    ferramentas = set((intent or {}).get("ferramentas", []) or [])
    usadas = set(ev.get("ferramentas_usadas", []) or [])
    if re.search(_ACAO_ALEGADA_RE, texto):
        if "research" in ferramentas and "research" not in usadas \
                and "research_deep" not in usadas:
            violacoes.append({"codigo": "acao_nao_executada",
                              "detalhe": "alega pesquisa sem ferramenta usada"})
        if "shopping" in ferramentas and "shopping" not in usadas:
            violacoes.append({"codigo": "acao_nao_executada",
                              "detalhe": "alega busca de produtos sem ferramenta usada"})

    if re.search(_CLAIM_VAGO_RE, texto):
        violacoes.append({"codigo": "afirmacao_inverificavel",
                          "detalhe": "superlativo absoluto sem cobertura"})

    if (intent or {}).get("intencao") == "shopping" and ev.get("produtos") == []:
        if "```jdui" in (resposta or "") and "product" in (resposta or ""):
            violacoes.append({"codigo": "card_sem_dados",
                              "detalhe": "cards de produto sem ofertas verificadas"})

    return {"violacoes": violacoes[:8], "ok": not violacoes}
