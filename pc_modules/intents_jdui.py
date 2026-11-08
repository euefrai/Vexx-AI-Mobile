"""Módulo do PC Agent: Classificadores de intenção (factual, pesquisa, imagem, widget) e sintetizadores JDUI."""
import jdui
import json
import re
import research
import unicodedata

from pc_modules.db_core import DONO_PADRAO, dono_valido, gerar_texto, log
from pc_modules.memory_store import memorias_relevantes

# ── Pesquisa web opcional (stdlib, sem dependências) ─────────────────
TERMOS_PESQUISA = ("pesquise", "pesquisar", "pesquisa por", "pesquisa sobre", "pesquisa profunda", "busque", "buscar", "google",
                   "últimas notícias", "ultimas noticias", "notícia", "noticia",
                   "fontes", "referências", "referencias", "atualizado", "hoje",
                   "preço", "preco", "clima", "placar", "resultado",
                   "documentação oficial", "documentacao oficial")


def intencao_pesquisa(texto: str) -> bool:
    t = (texto or "").lower()
    explicit_find=bool(re.search(r'\b(?:encontre|procure)\b',t)) and not re.search(
        r'\b(?:c[oó]digo|bug|erro|algoritmo|no (?:meu )?pc|arquivos? locais?|meus? arquivos?)\b',t)
    if not any(k in t for k in TERMOS_PESQUISA) and not explicit_find:
        return False
    # V5.7.3: gatilho genérico ("resultado", "preço", "agora") não basta.
    # Sem assunto não-genérico, a busca só devolveria páginas fora do pedido
    # (incidente 429: clima/investimentos após follow-up de shopping).
    return research.consulta_tem_assunto(re.sub(r'\b(?:encontre|procure)\b',' ',texto,flags=re.I) if explicit_find else texto)


# P0-3: retrieval-first para perguntas factuais. O gatilho explicito acima
# continua valendo; este classificador cobre quem/qual/quando/onde/como,
# entidades, datas, numeros, comparacoes e recomendacoes sem transformar
# conversa pessoal, memoria, codigo local ou criacao em busca web.
_RX_FACTUAL_STRONG_Q = re.compile(
    r"\b(?:quem|qual|quais|quando|onde|quanto|quantos|quantas)\b")
_RX_FACTUAL_WHAT = re.compile(
    r"\b(?:o que (?:e|sao|foi|foram|eram|significa|quer dizer)|"
    r"que (?:e|sao|foi|foram)|quem (?:e|foi|eram|sao)|"
    r"em que (?:ano|dia|pais|epoca|seculo)|que (?:ano|dia))\b")
_RX_FACTUAL_HOW = re.compile(
    r"\bcomo (?:funciona|funcionam|surgiu|surgiram|foi|foram|e feito|"
    r"e produzid[oa]|acontece|aconteceu|se formou|se formam|nasceu|morreu)\b")
_RX_FACTUAL_WHY = re.compile(r"\b(?:por que|porque)\b")
_RX_FACTUAL_COMPARE = re.compile(
    r"\b(?:diferenca entre|comparacao entre|compare|comparar|versus|"
    r"vs|melhor que)\b")
_RX_FACTUAL_RECOMMEND = re.compile(
    r"\b(?:me recomende|recomende|recomendacao|qual (?:e )?(?:o|a) melhor|"
    r"quais (?:sao )?(?:os|as) melhores|vale a pena|qual devo|o que devo)\b")
_RX_FACTUAL_VERB = re.compile(
    r"\b(?:foi|eram|nasceu|morreu|criou|inventou|descobriu|lancou|ganhou|"
    r"elegeu|aconteceu|assinou|fundou|comecou|terminou|escreveu|publicou|"
    r"estreou|acontecera|sera)\b")
_RX_FACTUAL_TIME = re.compile(
    r"\b(?:1[0-9]{3}|20[0-9]{2}|seculo|hoje|ontem|anteontem|amanha|"
    r"esta semana|este mes|este ano|ultimas noticias|agora|atualmente)\b")
_RX_FACTUAL_NUMBER = re.compile(
    r"(?:r\$\s?\d|\d+(?:[.,]\d+)?\s*(?:%|km|kg|m|cm|mm|milhoes|bilhoes|"
    r"habitantes|anos|graus|celsius|fahrenheit|dolares|reais))")
_RX_FACTUAL_SUMMARY = re.compile(
    r"\b(?:resuma|resumir|resumo (?:de|sobre|do|da))\b")
_RX_FACTUAL_TALK = re.compile(
    r"\b(?:me fale|fale|fala|me conte|conte) sobre\b")
_RX_FACTUAL_HISTORY = re.compile(
    r"\b(?:historia|origem|surgimento|contexto historico)\b")
_RX_FACTUAL_ENTITY = re.compile(
    r"(?:[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]{2,}|[A-Z]{2,})")

_RX_FACTUAL_NO_SEARCH = re.compile(
    r"\b(?:nao|sem)\s+(?:pesquis\w*|busc\w*|internet|google)\b|\boffline\b")
_RX_FACTUAL_CREATIVE = re.compile(
    r"\b(?:piada|poema)\b|"
    r"\b(?:conte|escreva|crie|gere|faca|desenhe)\b.{0,30}"
    r"\b(?:uma|um)\s+(?:historia|conto|roteiro|musica|letra|cancao|"
    r"imagem|foto|desenho)\b|"
    r"\b(?:gere|desenhe|crie)\s+(?:uma?\s+)?(?:imagem|foto|desenho)\b")
_RX_FACTUAL_INSTRUCTION = re.compile(
    r"^\s*(?:escreva|conte|crie|gere|faca|monte|desenhe|traduza|corrija|"
    r"refatore|implemente|programe|calcule|responda|liste|mostre|explique)\b")
_RX_FACTUAL_CODE = re.compile(
    r"\b(?:codigo|python|javascript|typescript|java|sql|regex|html|css|"
    r"bug|funcao|script|programa)\b")
_RX_FACTUAL_HOWTO = re.compile(
    r"\bcomo (?:faco|fazer|consigo|posso|criar|abrir|instalar|configurar|"
    r"usar|baixar|acessar|mudar|corrigir)\b")
_RX_FACTUAL_PERSONAL = re.compile(
    r"\b(?:meu|minha|meus|minhas)\s+(?:nome|prova|agenda|arquivo|pc|"
    r"computador|codigo|conversa|memoria|rotina|tarefa|trabalho|vida|"
    r"saude|peso|altura|idade|email|telefone|endereco|senha|gastos|"
    r"conta|sentimento|filha|filho|familia)\b|"
    r"\b(?:quanto|o que|como)\s+eu\s+(?:tenho|ganho|gasto|sinto|estou|"
    r"peso|media|faco|sou)\b|"
    r"\b(?:nossa|nesta|desta)\s+(?:conversa|vida|rotina)\b|"
    r"\b(?:o que|que)\s+(?:ja )?(?:falei|disse)\b|"
    r"\bsobre mim\b|"
    r"\b(?:lembre-se|lembra|memoria|guarde|anote|esqueca)\b")
_RX_FACTUAL_IDENTITY = re.compile(
    r"\b(?:quem (?:e|foi) voce|qual (?:e )?(?:o )?(?:seu|teu) nome|"
    r"se apresente|como (?:voce|vc) funciona|"
    r"voce (?:e|foi) (?:um )?(?:humano|robo|ia|modelo)|"
    r"(?:fale|fala|conte) sobre (?:voce|vc))\b")
_RX_FACTUAL_LOCAL = re.compile(
    r"\bque horas (?:sao|e)\b|\bque dia (?:e|foi) hoje\b|"
    r"\b(?:clima|temperatura) (?:aqui|onde estou)\b")
_RX_FACTUAL_MATH = re.compile(
    r"^\s*(?:quanto (?:e|vale)\s*)?[\d\s()+\-*/^.,%]+$")
_RX_FACTUAL_DOC = re.compile(r"\b(?:documento|arquivo|anexo|pdf)\b")
_RX_FACTUAL_DOC_ACT = re.compile(
    r"\b(?:resuma|resumir|analise|analisar|leia|ler|deste|desse|"
    r"anexado|enviado)\b")
_RX_FACTUAL_META = re.compile(
    r"\b(?:voce|vc)\b.{0,40}\b(?:acha|pensa|gosta|prefere|comeu|sente)\b")


def _sem_acentos_factual(texto: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower())
                  if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem).strip()


def _entidades_factuais(texto: str) -> list:
    """Nomes proprios/acronimos, ignorando a primeira palavra da frase."""
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]+", texto or "")
    return [p for i, p in enumerate(palavras)
            if i > 0 and _RX_FACTUAL_ENTITY.fullmatch(p)]


def classificar_intencao_factual(texto: str) -> dict:
    """Classifica pergunta factual que se beneficia de busca web.

    Retorna ``{"factual": bool, "score": int, "signals": [...],
    "entities": [...], "reason": str}``. E deterministico e conservador:
    perguntas pessoais, memoria, codigo local, calculo, criacao e documentos
    anexados nao disparam busca automatica. O objetivo e retrieval-first sem
    transformar toda conversa em pesquisa.
    """
    bruto = texto or ""
    t = _sem_acentos_factual(bruto)
    info = {"factual": False, "score": 0, "signals": [],
            "entities": [], "reason": ""}
    if len(t) < 8:
        info["reason"] = "curta"
        return info
    for rx, motivo in (
            (_RX_FACTUAL_NO_SEARCH, "pedido_sem_busca"),
            (_RX_FACTUAL_PERSONAL, "pessoal_ou_memoria"),
            (_RX_FACTUAL_IDENTITY, "identidade"),
            (_RX_FACTUAL_CREATIVE, "criativo"),
            (_RX_FACTUAL_HOWTO, "instrucao_local"),
            (_RX_FACTUAL_LOCAL, "dado_local"),
            (_RX_FACTUAL_META, "meta_conversa")):
        if rx.search(t):
            info["reason"] = motivo
            return info
    if _RX_FACTUAL_MATH.match(t):
        info["reason"] = "calculo_local"
        return info
    if _RX_FACTUAL_DOC.search(t) and _RX_FACTUAL_DOC_ACT.search(t):
        info["reason"] = "documento_anexado"
        return info
    try:
        tem_assunto = research.consulta_tem_assunto(bruto)
    except Exception:
        info["reason"] = "erro_classificador"
        return info
    if not tem_assunto:
        info["reason"] = "sem_assunto"
        return info

    forte = bool(_RX_FACTUAL_STRONG_Q.search(t))
    o_que = bool(_RX_FACTUAL_WHAT.search(t))
    como = bool(_RX_FACTUAL_HOW.search(t))
    por_que = bool(_RX_FACTUAL_WHY.search(t))
    comparacao = bool(_RX_FACTUAL_COMPARE.search(t))
    recomendacao = bool(_RX_FACTUAL_RECOMMEND.search(t))
    resumo = bool(_RX_FACTUAL_SUMMARY.search(t))
    fale = bool(_RX_FACTUAL_TALK.search(t))
    historia = bool(_RX_FACTUAL_HISTORY.search(t))
    verbo = bool(_RX_FACTUAL_VERB.search(t))
    tempo = bool(_RX_FACTUAL_TIME.search(t))
    numero = bool(_RX_FACTUAL_NUMBER.search(t))
    entidades = _entidades_factuais(bruto)

    # Instrucoes locais e codigo so continuam quando ha sinal factual forte
    # (ex.: "compare Python e JavaScript").
    if _RX_FACTUAL_INSTRUCTION.search(t) and not (
            o_que or como or comparacao or recomendacao or resumo or fale):
        info["reason"] = "instrucao"
        return info
    if _RX_FACTUAL_CODE.search(t) and not (o_que or como or comparacao):
        info["reason"] = "codigo_local"
        return info
    # Follow-up curto sem entidade/data ("qual a capital?", "e ele?") precisa
    # do contexto da conversa; nao vira busca generica.
    if len(t.split()) <= 3 and not (entidades or tempo or numero
                                   or comparacao or recomendacao):
        info["reason"] = "followup_curto"
        return info

    pontos, sinais = 0, []
    for ativo, nome, peso in (
            (o_que, "o_que_e", 2),
            (como, "como_funciona", 2),
            (comparacao, "comparacao", 2),
            (recomendacao, "recomendacao", 2),
            (forte, "pergunta_factual", 2),
            (por_que, "por_que", 2),
            (resumo, "resumo_pedido", 1),
            (fale, "fale_sobre", 1),
            (historia, "contexto_historico", 1),
            (verbo, "verbo_factual", 1),
            (tempo, "data_ou_atualidade", 1),
            (numero, "numero_ou_unidade", 1),
            (bool(entidades), "entidade", 1)):
        if ativo:
            pontos += peso
            sinais.append(nome)
    info.update(factual=pontos >= 2, score=pontos, signals=sinais,
                entities=entidades[:8],
                reason="factual" if pontos >= 2 else "sinais_insuficientes")
    return info


def intencao_factual(texto: str) -> bool:
    """Atalho booleano do classificador factual (P0-3)."""
    return bool(classificar_intencao_factual(texto).get("factual"))


APROFUNDADA_TRIGGERS = ("a fundo", "aprofundada", "aprofundado", "relatório completo",
                        "relatorio completo", "dossiê", "dossie", "verifique se",
                        "é verdade", "e verdade", "checar fatos", "comparar fontes")


def intencao_pesquisa_aprofundada(texto: str) -> bool:
    t = (texto or "").lower()
    return any(k in t for k in APROFUNDADA_TRIGGERS)


_MEMORIA_GATILHOS = ("aquela prova", "aquele trabalho", "aquela materia", "aquela matéria",
                     "te falei", "como te falei", "minha prova", "meu trabalho", "minha meta")


def termos_memoria_pesquisa(db, owner: str, texto: str) -> str:
    """Só TERMOS de tópico da memória (nunca valores/dados pessoais).

    Ex.: 'pesquisa para aquela prova' + memória 'Prova de biologia dia 20'
    → 'biologia'. A consulta externa nunca recebe a memória inteira.
    """
    t = (texto or "").lower()
    if not any(g in t for g in _MEMORIA_GATILHOS):
        return ""
    try:
        rel = memorias_relevantes(db, texto, owner=owner)
    except Exception:
        return ""
    stop = {"para", "como", "mais", "sobre", "entre", "isso", "esse", "esta",
            "este", "qual", "quais", "onde", "quando", "porque", "pode", "ser",
            "são", "minha", "meu", "te", "foi", "tem", "dia", "prova", "trabalho"}
    toks = []
    for f in rel[:4]:
        for w in re.findall(r"[a-zà-ú]{5,}", str(f.get("value", "")).lower()):
            if w not in stop and w not in toks:
                toks.append(w)
    return " ".join(toks[:8])


def intencao_imagem(texto: str) -> str:
    """Retorna o termo da imagem pedida ou ''."""
    import re
    t = texto or ""
    m = re.search(r"(?i)(?:mostre|mostra|mande|envie|quero|gere?)?\s*(?:uma?|a)?\s*(?:imagem|foto|figura|picture|image)\s*(?:de|do|da|sobre)?\s*(.{2,80})", t)
    if m:
        termo = re.sub(r"[.?!]+$", "", m.group(1).strip())[:80]
        if len(termo) >= 2 and "imagem" not in termo.lower():
            return termo
        return termo or "paisagem"
    if re.search(r"(?i)\b(imagem|foto|figura)\b", t):
        return "paisagem"
    return ""


class JULIAPresentationEngine:
    """Decide quando a resposta merece interface declarativa JDUI (sem JS do modelo)."""

    REGRAS = [
        (("planilha", "em formato de planilha", "organize em tabela",
          "monte uma tabela", "tabela com"), "table"),
        (("tabela comparativa", "comparar lado a lado", "compare em tabela",
          "versus em tabela"), "compare"),
        (("gráfico", "grafico", "evolução", "evolucao", "em barras", "em pizza",
          "distribuição dos", "distribuicao dos", "histograma"), "chart"),
        (("dashboard", "painel de", "painel com métricas", "visão geral com números"), "dashboard"),
        (("roadmap", "roteiro de projeto", "plano de ação por etapas",
          "mapa de etapas"), "cards"),
        (("treino", "treinamento", "ficha de treino", "rotina de exercícios",
          "rotina de exercicios", "plano de exercícios", "plano de exercicios"), "table"),
        (("quiz", "quizz", "questionário", "questionario", "teste de conhecimento",
          "perguntas e respostas", "simulado"), "quiz"),
        (("checklist", "check-list", "lista de tarefas", "rotina de estudos",
          "plano de estudos", "hábitos"), "checklist"),
        (("calculadora", "calcule meu imc", "índice de massa", "indice de massa",
          "porcentagem", "juros compostos", "quanto rende", "converter",
          "conversor", "quanto é em"), "calculator"),
        (("compare", "comparação", "comparacao", "diferenças entre", "diferencas entre",
          "prós e contras", "pros e contras", "qual melhor"), "cards"),
        (("diagrama", "fluxograma", "fluxo de", "arquitetura", "como funciona o",
          "como se conecta", "etapas do", "mapa do sistema"), "diagram"),
        (("em tabela", "tabela com", "liste em colunas", "cronograma"), "table"),
        (("formulário", "formulario", "cadastro", "inscrição", "inscricao"), "form"),
        (("grade de produtos", "cards de produto", "cartões de produto",
          "galeria de produtos", "vitrine de produtos"), "productgrid"),
        (("mostre as fontes", "mostra as fontes", "quais as fontes",
          "lista de fontes", "fontes da pesquisa"), "sources"),
        (("roteiro do projeto", "roadmap do", "monte um roadmap",
          "etapas do projeto", "cronograma do projeto"), "roadmap"),
    ]

    @classmethod
    def sugerir(cls, texto: str) -> str:
        t = (texto or "").lower()
        for chaves, comp in cls.REGRAS:
            if any(k in t for k in chaves):
                return comp
        return ""


JDUI_CATALOGO = (
    "INTERFACE DECLARATIVA (use quando pedida ou muito útil; texto simples prefere texto): "
    "responda com texto normal + blocos ```jdui com JSON {version:'JULIA-ui-message/v1',"
    "blocks:[{type:'text',content},{type:'ui',component,props}]}. Componentes: "
    "quiz{title,questions[{q,options[2..6],answer(índice),explain}]}; "
    "checklist{title,items[]}; calculator{kind:basic|imc|porcentagem|juros|conversor}; "
    "cards{items[{title,desc,value,badge,url,action{chat}}]}; "
    "diagram{direction:v|h,nodes[{id,label,desc}],edges[{from,to,label}]}; "
    "table{columns[],rows[[]]}; compare{columns[2],rows[{label,a,b,melhor:a|b|=}]}; "
    "chart{type:line|bar|pie|area|scatter,title,labels[],series[{label,values[]}],source}; "
    "dashboard{title,metrics[{label,value,hint}],chart?,source}; "
    "form{title,fields[{name,label,type:text|number|select,options}],calc:imc|juros|porcentagem|soma}; "
    "progress{label,value,max}; tabs{tabs[{title,markdown}]}; accordion{items[{title,markdown}]}; "
    "productcard{produto{nome,marca,modelo,imagem,preco,loja,url,specs,avaliacao,disponibilidade,verificado_em}}; "
    "productgrid{title,items[1..6 produtos]}; productcompare{title,items[2..4 produtos]}; "
    "productdetails{produto}; productgallery{title,imagens[{url,legenda}]}; "
    "sources{title,items[{titulo,url,dominio,data,trecho,status:encontrada|aberta|utilizada}]}; "
    "video{titulo,url(somente YouTube/Vimeo),thumb,duracao,fonte}; "
    "roadmap{title,stages[{id,title,desc,status:todo|doing|done,data,marco}]}. "
    "PRODUTOS À VENDA (preço/loja/foto): NUNCA monte productcard/productgrid/productcompare/productdetails/productgallery "
    "com seu conhecimento — esses cards vêm da ferramenta de pesquisa com dados verificados. "
    "REGRAS: JSON válido e pequeno (máx 6 blocos, 12 perguntas, 30 linhas); sem JavaScript, sem CSS, "
    "sem perguntas de volta quando pedirem app; quiz/calculadora/checklist NUNCA em texto corrido. "
    "GRÁFICOS SÓ com números dados pelo usuário ou já exibidos na conversa — nunca invente séries. "
    "ATUALIZAÇÃO (update_of:id-da-mensagem): só chart|table|dashboard|compare|diagram|checklist|cards|tabs|accordion|form|calculator|sources|roadmap|productgrid; "
    "NUNCA exam|quiz|studyprogress (resultado imutável)."
)


def intencao_widget(texto: str) -> str:
    """Legado: agora redireciona para o componente JDUI equivalente."""
    comp = JULIAPresentationEngine.sugerir(texto)
    return comp or ""


PEDIDO_CODIGO_RE = re.compile(
    r"(?i)(quero|manda|mande|mostra|mostre|pode mostrar|me d[áa]|quero ver).{0,40}(c[óo]digo|fonte)"
    r"|^(sim|quero|manda|pode ser|claro|ok|yes)\W*$")

_VERBO_ARQUIVO_RE = re.compile(
    r"(?i)\b(cri[ae]r?|ger[ae]r?|salv[ae]r?|escrev[ae]r?|sobrescrev\w*|"
    r"sobrepor|sobrepon\w*|sobrepost\w*|substitu\w*|atualiz\w*|modific\w*|"
    r"corrij\w*|refa[çc]a|fa[çc]a|mont[ae]r?|coloc\w*|transform\w*|"
    r"export\w*|baix\w*|convert\w*)\b")
_ALVO_ARQUIVO_RE = re.compile(
    r"(?i)\b(arquivos?|documentos?|projetos?|pastas?|c[óo]digo|fonte|programa|"
    r"script|html|css|json|csv|xml|yaml|markdown|readme|txt|py|js|ts|java|"
    r"cpp|csharp|sql|sh|bat|pdf|docx|xlsx|zip|conte[uú]do|vers[ãa]o)\b|"
    r"\.[a-z0-9]{1,8}\b")


def quer_criar_arquivo(texto: str, doc_id: str = "") -> bool:
    """Detecta pedido explícito de criar/versionar um arquivo no PC."""
    t = (texto or "").lower()
    if re.search(r"(?i)\b(n[aã]o (crie|gere|salve|escreva|sobrescreva)|sem (criar|gerar|salvar))\b", t):
        return False
    if re.search(r"(?i)\b(nova|outra|segunda|pr[oó]xima)\s+vers[ãa]o\b|"
                 r"\bvers[ãa]o\s+(?:dele|dela|do arquivo|atualizada|corrigida|final)\b|"
                 r"\bsobrescrev\w*|\bsobrepor\b|\bsubstitu\w*\b", t):
        return True
    if _VERBO_ARQUIVO_RE.search(t) and _ALVO_ARQUIVO_RE.search(t):
        return True
    if doc_id and re.search(r"(?i)\b(cri\w*|ger\w*|salv\w*|escrev\w*|"
                            r"sobrepon\w*|sobrepost\w*|sobrepor|"
                            r"atualiz\w*|modific\w*|corrij\w*|refa[çc]a|"
                            r"melhor\w*|edit\w*|ajust\w*|vers[ãa]o)\b", t):
        return True
    return False


REGRA_ARQUIVO = (
    "CRIAÇÃO DE ARQUIVO NO PC: quando o usuário pedir para criar, gerar, "
    "salvar, reescrever ou versionar um arquivo, entregue o conteúdo COMPLETO "
    "em UM bloco exatamente neste formato:\n"
    "<JULIAFILE name=\"nome.ext\">\n"
    "conteúdo integral do arquivo\n"
    "</JULIAFILE>\n"
    "Regras: use um nome relativo curto (sem pastas absolutas e sem '..'); se for "
    "uma nova versão de um anexo, mantenha o mesmo nome; preserve espaços, tabs e "
    "indentação; não resuma, não use reticências, placeholders ou trechos omitidos; "
    "não coloque ```jdui dentro do bloco; não invente credenciais, chaves ou dados. "
    "Para formato binário, use <JULIAFILE name=\"nome.ext\" encoding=\"base64\"> com "
    "base64 válido. O sistema grava o arquivo e mostra o cartão de download."
)


def ultimos_blocos_jdui(db, conversation_id: str, limite: int = 2, owner=DONO_PADRAO) -> list:
    """Últimos blocos JDUI válidos do assistente nesta conversa (p/ gerar código-fonte)."""
    try:
        rows = db.execute(
            """SELECT text FROM messages WHERE origin='mobile' AND owner_id=? AND conversation_id=?
               AND role='assistant' AND text LIKE '%```jdui%' ORDER BY created_at DESC LIMIT 5""",
            (dono_valido(owner), conversation_id)).fetchall()
    except Exception:
        return []
    out = []
    for (txt,) in rows:
        for corpo in jdui.extrair_fences(txt or ""):
            try:
                obj = json.loads(corpo)
            except ValueError:
                continue
            ok, norm, _ = jdui.validar_mensagem(obj)
            if ok:
                out.append(norm)
                if len(out) >= limite:
                    return out
    return out


JDUI_SINTETIZAR = {
    "quiz": ("Converta o quiz abaixo para JSON JDUI. Responda SÓ com o JSON, sem cercas e sem texto: "
             '{"version":"JULIA-ui-message/v1","blocks":[{"type":"ui","component":"quiz",'
             '"props":{"title":"...","questions":[{"q":"...","options":["...","..."],"answer":0,"explain":"..."}]}}]}. '
             "Regras: use as perguntas e opções do conteúdo (em código Python, a certa está no `if`); "
             "máximo 6 perguntas, 4 opções cada, answer é o índice; explain curta."),
    "checklist": ("Converta a lista abaixo para JSON JDUI. Responda SÓ com o JSON: "
                  '{"version":"JULIA-ui-message/v1","blocks":[{"type":"ui","component":"checklist",'
                  '"props":{"title":"...","items":["..."]}}]}. Máximo 20 itens curtos.'),
    "calculator": ("O usuário quer uma calculadora. Responda SÓ com o JSON JDUI: "
                   '{"version":"JULIA-ui-message/v1","blocks":[{"type":"ui","component":"calculator",'
                   '"props":{"kind":"basic"}}]}. kind: basic (padrão), imc (peso/altura), '
                   "porcentagem (valor/percentual) ou juros (capital/taxa/meses) conforme o pedido."),
    "table": ("Converta o conteúdo abaixo para JSON JDUI de tabela. Responda SÓ com JSON válido: "
              '{"version":"JULIA-ui-message/v1","blocks":[{"type":"ui","component":"table",'
              '"props":{"title":"...","columns":["..."],"rows":[["..."]]}}]}. '
              "Use os dados do conteúdo sem inventar valores, 1 a 8 colunas e até 30 linhas. "
              "Preserve unidades, dias, séries e repetições quando existirem."),
    "cards": ("Converta o conteúdo abaixo em cartões JDUI, na ordem cronológica/de execução. "
              "Responda SÓ com JSON válido: "
              '{"version":"JULIA-ui-message/v1","blocks":[{"type":"ui","component":"cards",'
              '"props":{"title":"...","items":[{"title":"...","desc":"...","value":"...","badge":"..."}]}}]}. '
              "Use 1 a 8 cartões e não invente datas nem fatos."),
    "roadmap": ("Converta o plano/projeto abaixo em roteiro JDUI. Responda SÓ com JSON válido: "
               '{"version":"JULIA-ui-message/v1","blocks":[{"type":"ui","component":"roadmap",'
               '"props":{"title":"...","stages":[{"id":"s1","title":"...","desc":"...","status":"todo"}]}}]}. '
               "Use 1 a 12 etapas em ordem, status todo|doing|done SOMENTE com base no conteúdo "
               "(sem progresso fictício; sem data inventada; marco:true só para marcos citados)."),
}


def _limpa_opcao(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").replace("\\n", " ").strip(" \t\"'")).strip()
    return s[:120]


def _indice_resposta(letras: list, letra) -> int:
    try:
        return letras.index((letra or "").lower())
    except ValueError:
        return -1


def _opcoes_inline(t: str) -> list:
    """Opções 'a) x  b) y' na mesma linha. Retorna [(letra, texto)]."""
    return [(l.lower(), _limpa_opcao(x))
            for l, x in re.findall(r"\b([a-dA-D])[.)]\s*(.+?)(?=\s*\b[a-dA-D][.)]\s*|\s*$)", t)]


def _fence_quiz(questions: list) -> str:
    ok, norm, _ = jdui.validar_mensagem(
        {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "quiz",
             "props": {"title": "Quiz", "questions": questions[:6]}}]})
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def extrair_quiz_codigo(texto: str) -> str:
    """Quiz em código Python terminal (print pergunta/opções + if resposta)."""
    segmentos = re.split(r"#\s*[Pp]ergunta\s*\d+", texto or "")
    questions = []
    for seg in segmentos[1:]:
        prints = re.findall(r'print\(\s*"((?:[^"\\]|\\.)*)"\s*\)', seg)
        if not prints:
            prints = re.findall(r"print\(\s*'((?:[^'\\]|\\.)*)'\s*\)", seg)
        corte = re.search(r"\bresposta\s*=\s*input|\binput\s*\(|if\s+\w+\s*==", seg)
        regiao = seg[:corte.start()] if corte else seg
        prints_reg = re.findall(r'print\(\s*"((?:[^"\\]|\\.)*)"\s*\)', regiao) or \
            re.findall(r"print\(\s*'((?:[^'\\]|\\.)*)'\s*\)", regiao)
        q, pares = "", []
        for p in prints_reg:
            p = p.replace("\\n", " ").replace('\\"', '"')
            if not q:
                m = re.match(r"\s*\d+[.)]\s*(.+)", p, re.S)
                cand = _limpa_opcao(m.group(1) if m else p)
                if len(cand) >= 8 and "===" not in cand:
                    q = cand
                    continue
            pares.extend(_opcoes_inline(p))
        if len(pares) < 2:  # opções podem estar no mesmo print da pergunta
            juntos = " ".join(prints_reg)
            pares = _opcoes_inline(juntos)
        letras = [l for l, _ in pares]
        textos = [_limpa_opcao(t) or t.strip() for _, t in pares][:6]
        m = re.search(r'if\s+\w+\s*==\s*["\']([a-dA-D])["\']', seg)
        ans = _indice_resposta(letras, m.group(1) if m else "")
        if q and len(textos) >= 2 and 0 <= ans < len(textos):
            questions.append({"q": q[:300], "options": textos,
                              "answer": ans, "explain": ""})
        if len(questions) >= 6:
            break
    return _fence_quiz(questions) if questions else ""


def extrair_quiz_texto(texto: str) -> str:
    """Quiz em texto corrido (Pergunta N + a) b) c) d) + Resposta: x)."""
    partes = re.split(r"(?im)^\s*(?:\*\*?)?\s*pergunta\s*\d+\s*[:.\-]?\s*(?:\*\*?)?", texto or "")
    questions = []
    for seg in partes[1:]:
        seg = seg.strip()
        if "print(" in seg and "input(" in seg:
            continue  # código Python: trabalho do extrair_quiz_codigo
        corpo = re.sub(r"(?s)```.*?```", " ", seg)
        pares = []
        for linha in corpo.split("\n"):
            m = re.match(r"\s*([a-dA-D])[.)]\s*(.+?)\s*$", linha)
            if m and len(_limpa_opcao(m.group(2))) >= 1:
                pares.append((m.group(1).lower(), _limpa_opcao(m.group(2))))
        if len(pares) < 2:
            pares = [(l, t) for l, t in _opcoes_inline(" " + corpo) if t]
        # pergunta = texto antes da primeira opção (sem code fence)
        mq = re.search(r"\b[a-dA-D][.)]\s", seg)
        qpart = re.sub(r"(?s)```.*?```", " ", seg[:mq.start()] if mq else seg)
        q = _limpa_opcao(re.sub(r"^[\s*#:\-–—]+", "", qpart))[:300]
        letras = [l for l, _ in pares]
        textos = [t for _, t in pares][:6]
        m = re.search(r"(?i)(?:resposta\s*(?:certa|correta)?|certa|gabarito)\s*[:\-]?\s*\(?([a-dA-D])\)?",
                      seg)
        ans = _indice_resposta(letras, m.group(1) if m else "")
        if q and len(textos) >= 2 and 0 <= ans < len(textos):
            questions.append({"q": q, "options": textos, "answer": ans, "explain": ""})
        if len(questions) >= 6:
            break
    return _fence_quiz(questions) if questions else ""


def sintetizar_calculadora(texto_usuario: str) -> str:
    """Calculadora não precisa de LLM: o kind sai do pedido. 100% confiável."""
    t = (texto_usuario or "").lower()
    if any(k in t for k in ("imc", "massa corporal", "peso", "altura")):
        kind = "imc"
    elif any(k in t for k in ("porcent", "%", "desconto", "aumento", "taxa")):
        kind = "porcentagem"
    elif any(k in t for k in ("juros", "montante", "rende", "compost")):
        kind = "juros"
    else:
        kind = "basic"
    ok, norm, _ = jdui.validar_mensagem(
        {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "calculator", "props": {"kind": kind}}]})
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def extrair_checklist(texto_resposta: str) -> str:
    """Itens em bullets da resposta viram checklist (sem LLM)."""
    itens = []
    for linha in (texto_resposta or "").split("\n"):
        if re.match(r"\s*([a-dA-D])[.)]\s", linha):
            continue  # opção de quiz, não item
        m = re.match(r"\s*(?:[-*•‣]|(?:\d+[.)]))\s+(.{3,120}?)\s*$", linha)
        if m:
            txt = _limpa_opcao(m.group(1))
            if txt and txt not in itens:
                itens.append(txt)
        if len(itens) >= 20:
            break
    if len(itens) < 2:
        return ""
    ok, norm, _ = jdui.validar_mensagem(
        {"version": jdui.VERSION, "blocks": [
            {"type": "ui", "component": "checklist",
             "props": {"title": "Checklist", "items": itens}}]})
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def sintetizar_jdui(cfg: dict, componente: str, texto_usuario: str, texto_resposta: str) -> str:
    """Garante a interface quando a IA não emitiu o fence.

    Ordem: determinístico (grátis, instantâneo) → conversão via LLM.
    Retorna o fence pronto ou ''. Nunca levanta exceção.
    """
    try:
        if componente == "calculator":
            fence = sintetizar_calculadora(texto_usuario)
            if fence:
                return fence
        elif componente == "quiz":
            fence = extrair_quiz_codigo(texto_resposta) or extrair_quiz_texto(texto_resposta)
            if fence:
                log.info("quiz extraído deterministicamente")
                return fence
        elif componente == "checklist":
            fence = extrair_checklist(texto_resposta)
            if fence:
                return fence
    except Exception as exc:
        log.warning("extração determinística falhou (%s)", type(exc).__name__)
    return _sintetizar_jdui_llm(cfg, componente, texto_usuario, texto_resposta)


def _sintetizar_jdui_llm(cfg: dict, componente: str, texto_usuario: str, texto_resposta: str) -> str:
    """Último recurso: quando a IA não emitiu o fence, converte a resposta em JDUI.

    Retorna o fence pronto (com \\n\\n) ou ''. Nunca levanta exceção.
    """
    prompt = JDUI_SINTETIZAR.get(componente or "")
    if not prompt or len(texto_resposta or "") < 50:
        return ""
    try:
        res = gerar_texto(cfg,
            [{"role": "system", "content": "Você converte conteúdo para JSON. Responda SÓ JSON válido."},
             {"role": "user", "content": prompt + "\n\nPEDIDO: " + (texto_usuario or "")[:400]
              + "\n\nCONTEÚDO:\n" + (texto_resposta or "")[:6000]}],
            max_tokens=1500)
        corpo = (res.get("texto") or "").strip()
        m = re.search(r"```(?:jdui|json)?\s*\n?([\s\S]*?)```", corpo)
        if m:
            corpo = m.group(1).strip()
        obj = json.loads(corpo)
        ok, norm, _ = jdui.validar_mensagem(obj)
        if not ok:
            return ""
        return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"
    except Exception as exc:
        log.warning("síntese JDUI falhou (%s); mantendo só texto", type(exc).__name__)
        return ""
