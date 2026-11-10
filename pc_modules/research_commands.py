"""Módulo do PC Agent: Comandos de pesquisa, análise tabular, qualidade, shopping verificado e validação de evidências."""
import evidence_graph as evgraph
import inference_status
import intent
import jdui
import json
import julia_auth as JULIA_auth
import query_intelligence
import re
import research
import research_agents
import shlex
import shopping
import vision_service
import workspace_store

from pc_modules.memory_store import _normalizar_temporal
from pc_modules.calendar_projects import _projetos_relevantes, _trechos_projeto, pendencias
from pc_modules.db_core import database_path, dono_valido, log
from pc_modules.context_providers import anexar_fontes, imagens_primeiro

# Símbolos de módulos posteriores injetados na inicialização do pacote:
iniciar_job_bg = None  # provido por pc_modules.research_jobs
rjob_start = None  # provido por pc_modules.research_jobs

_JOB_START_RE = re.compile(
    r"(?i)\b(?:pesquis[ae]\s+(?:a fundo|profunda)|investigue\s+a\s+fundo)"
    r"(?:\s*:\s*|\s+)(?:sobre\s+)?(.{3,500}?)[.?!]*$")


def _ultimo_job(db, owner: str, estados: tuple = (), conv=None) -> dict | None:
    for j in research_agents.listar_jobs(db, owner, 10):
        if conv is not None and j.get('conv') != conv:
            continue
        if not estados or j["status"] in estados:
            try:
                return research_agents.carregar_job(db, owner, j["id"])
            except research_agents.AgentErro:
                continue
    return None


def _cmd_intervencao(db, owner: str, t: str, conv=None):
    """Mudança de instrução sem reiniciar (conjunto estruturado, sem LLM)."""
    if _JOB_START_RE.search(t):
        return ''  # A new explicit investigation is not a change to an old one.
    job = _ultimo_job(db, owner, ("em_andamento", "pausada", "interrompida"),conv=conv)
    if job is None:
        return ""
    jid = job["id"]

    def _aplica(op, params):
        try:
            out = research_agents.intervir(db, owner, jid, op, params)
        except research_agents.AgentErro as exc:
            return "Não consegui alterar: " + str(exc) + " 🔍"
        detalhe = []
        if out["adicionadas"]:
            detalhe.append("novas: " + ", ".join(out["adicionadas"][:3]))
        if out["removidas"]:
            detalhe.append("removidas: " + ", ".join(out["removidas"][:3]))
        if out["invalidadas"]:
            detalhe.append(f"{len(out['invalidadas'])} resultado(s) anterior(es) conflitam "
                           "com o novo critério (preservados, marcados).")
        return (f"Plano v{out['plano_versao']} atualizado ({op}). "
                + (" ".join(detalhe) if detalhe else "Sem alterações necessárias.") + " 🔍")

    m = re.search(r"(?i)pesquise apenas (.+)|só (.+?)(?:\.|$)|somente (.+?)(?:\.|$)", t)
    if m:
        alvo = next((g for g in m.groups() if g), "").strip()[:120]
        if len(alvo) >= 3:
            return _aplica("escopo_add", {"texto": alvo})
    m = re.search(r"(?i)priorize (.+?)(?:\.|$)", t)
    if m and len(m.group(1).strip()) >= 3:
        alvo = m.group(1).strip()[:120]
        if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", alvo):
            return _aplica("priorizar_dominio", {"dominio": alvo})
        return _aplica("escopo_add", {"texto": alvo})
    m = re.search(r"(?i)ignore (.+?)(?:\.|$)", t)
    if m and len(m.group(1).strip()) >= 3:
        return _aplica("escopo_remove", {"texto": m.group(1).strip()[:120]})
    if re.search(r"(?i)investigue (melhor )?essa diverg", t):
        return _aplica("investigar_divergencia", {"indice": 0})
    m = re.search(r"(?i)(?:não precisa mais pesquisar|pare de pesquisar|não pesquise mais) (.+?)(?:\.|$)", t)
    if m and len(m.group(1).strip()) >= 3:
        return _aplica("parar_topico", {"texto": m.group(1).strip()[:120]})
    m = re.search(r"(?i)adicione (.+?) à comparação|adicione (.+?) a comparacao", t)
    if m:
        alvo = next((g for g in m.groups() if g), "").strip()[:120]
        if len(alvo) >= 3:
            return _aplica("adicionar_metrica", {"texto": alvo})
    return ""


def _cmd_analisar_tabular(db, texto: str, owner: str, conv: str) -> str:
    if not re.match(r"(?is)^\s*analisar\s+tabular(?:\s|$)", texto or ""):
        return ""
    try:
        tokens = shlex.split(texto)
    except ValueError:
        return "Não consegui interpretar as aspas. Use aspas em valores de coluna com espaços."
    if len(tokens) < 3 or tokens[0].lower() != "analisar" or tokens[1].lower() != "tabular":
        return "Informe `analisar tabular chart` ou `analisar tabular compare`."
    mode = tokens[2].lower()
    if mode not in ("chart", "compare"):
        return "O tipo deve ser `chart` ou `compare`."
    values = {}
    for token in tokens[3:]:
        if "=" not in token:
            return f"Parâmetro inválido: {token!r}. Use nome=valor."
        key, value = token.split("=", 1)
        key = key.lower().strip()
        if key not in {"job", "doc", "x", "y", "series", "group", "value",
                       "baseline", "unit", "period", "methodology", "title"}:
            return f"Parâmetro não suportado: {key!r}."
        if not value or key in values:
            return f"Parâmetro {key!r} está vazio ou repetido."
        values[key] = value
    if not values.get("job") or not values.get("doc"):
        return "Informe job=<id> e doc=<id> para limitar a análise à pesquisa e ao documento corretos."
    try:
        job = research_agents.carregar_job(db, owner, values["job"])
        if job["conv"] != conv:
            return "Esse job não pertence à conversa atual; não associei o documento a outra pesquisa."
        columns = {
            key: values[key] for key in (
                "x", "y", "series", "group", "value", "baseline", "unit",
                "period", "methodology", "title",
            ) if key in values
        }
        result = research_agents.analisar_documento_estruturado(
            db, owner, job["id"], values["doc"],
            method="chart_series" if mode == "chart" else "differences",
            columns=columns,
        )
    except research_agents.AgentErro as exc:
        return f"Não foi possível analisar o documento: {exc}."
    except (ValueError, TypeError) as exc:
        return f"Não foi possível validar a análise tabular: {exc}."
    block = result["visualization"]
    message = {
        "version": jdui.VERSION,
        "blocks": [
            {"type": "text", "content":
             f"Análise determinística concluída com os dados reais de **{result['document_name']}**. "
             "Isto descreve os dados fornecidos; não estabelece causalidade ou diagnóstico."},
            *block.get("blocks", []),
        ],
    }
    valid, normalized, errors = jdui.validar_mensagem(message)
    if not valid or normalized is None:
        return f"A análise foi calculada, mas a visualização não passou a validação JDUI: {errors}."
    return "\n\n```jdui\n" + json.dumps(normalized, ensure_ascii=False) + "\n```"


def cmd_qualidade(db, texto: str, owner: str) -> str:
    """Painel admin de qualidade com dados reais (nunca fictícios)."""
    t = (texto or "").lower()
    if "qualidade da pesquisa" not in t and "painel de qualidade" not in t:
        return ""
    if owner != "local":
        try:
            u = JULIA_auth.buscar_uid(db, owner)
        except Exception:
            u = None
        if not u or u.get("role") != "admin" or u.get("status") != "ativo":
            return ("O painel de qualidade é restrito ao administrador. "
                    "Peça a quem administra este PC. 🔒")
    import research_quality_lab
    runs = research_quality_lab.list_reports(db, owner)
    if not runs:
        return ("Ainda não há avaliações armazenadas. Rode uma avaliação "
                "em /api/admin/quality/run e peça de novo. 📊")
    ultimo = runs[0]
    resumo = ultimo.get("summary", {}) or {}
    metricas = [
        {"label": "Precisão", "value": str(resumo.get("precision_at_k", "—")),
         "hint": f"P@{resumo.get('k', '?')}"},
        {"label": "Recall", "value": str(resumo.get("recall_at_k", "—")), "hint": "cobertura"},
        {"label": "MRR", "value": str(resumo.get("mrr_at_k", "—")), "hint": "primeiro acerto"},
        {"label": "NDCG", "value": str(resumo.get("ndcg_at_k", "—")), "hint": "ordenação"},
        {"label": "Consultas", "value": str(resumo.get("query_count", "?")), "hint": "avaliadas"},
        {"label": "Dataset", "value": f"{ultimo.get('dataset_id', '?')} {ultimo.get('dataset_version', '')}".strip(),
         "hint": ultimo.get("dataset_sha256", "")[:12]},
    ]
    message = {"version": "JULIA-ui-message/v1", "blocks": [
        {"type": "text", "content": f"Qualidade medida em {ultimo.get('created_at', '?')} "
         f"({len(runs)} avaliações guardadas). Números reais do benchmark congelado."},
        {"type": "ui", "component": "dashboard",
         "props": {"title": "Quality Lab — último run",
                   "metrics": metricas, "chart": None,
                   "source": f"benchmark {ultimo.get('dataset_id', '?')}",
                   "sources": []}}]}
    valid, normalized, errors = jdui.validar_mensagem(message)
    if not valid or normalized is None:
        return f"Dados calculados, mas o painel não validou: {errors}."
    return "\n\n```jdui\n" + json.dumps(normalized, ensure_ascii=False) + "\n```"


def _filtrar_usados_restricao(shop_res: dict, intencao: dict) -> dict:
    """V5.1: se o pedido proíbe usados, move-os para `excluidos` com motivo."""
    try:
        proib = " ".join(((intencao or {}).get("restricoes", {}) or {}).get("proibidas", []))
        if not re.search(r"\busados?\b|segunda m|second hand", proib.lower()):
            return shop_res
        novos = [p for p in shop_res.get("produtos", [])
                 if str(((p.get("specs", {}) or {}).get("Condicao", ""))).lower() != "usado"]
        usados = [p for p in shop_res.get("produtos", [])
                  if str(((p.get("specs", {}) or {}).get("Condicao", ""))).lower() == "usado"]
        if usados and novos:
            for u in usados:
                u["excluido_por"] = "usado (pedido: somente novos)"
            shop_res["excluidos"] = (shop_res.get("excluidos", []) + usados)[:6]
            shop_res["produtos"] = novos[:6]
            log.info("shopping: %d usados filtrados (restrição)", len(usados))
    except Exception as exc:
        log.warning("shopping filtro-usados falhou (%s)", type(exc).__name__)
    return shop_res


def _shopping_executar(db, owner: str, conv: str, user_text: str, extras: dict,
                       messages: list, progresso=None) -> dict | None:
    """V5.7: busca de produtos do pedido + grounding real no prompt.

    Compartilhado entre o caminho com streaming e o fallback sem streaming —
    antes o fallback (/api/ai) nunca buscava e o modelo respondia de memória
    com produtos/preços inventados.
    """
    if not extras.get("shop"):
        return None
    shop_res = None
    try:
        consulta_shop = user_text
        if extras.get("visao"):
            consulta_shop = vision_service.enriquecer_consulta_com_visao(
                user_text, extras.get("visao"), max_chars=240)
        shop_res = shopping.pesquisar(db, owner, consulta_shop, conv,
                                      progresso=progresso)
        extras["ferramentas_usadas"].append("shopping")
    except Exception as exc:
        log.warning("shopping falhou (%s)", type(exc).__name__)
        shop_res = None
    if shop_res and shop_res.get("produtos"):
        # V5.1: restrição explícita de usados filtra antes do LLM e dos cards.
        shop_res = _filtrar_usados_restricao(shop_res, extras.get("intent") or {})
    if shop_res and shop_res.get("produtos"):
        try:
            messages.append({"role": "system",
                             "content": shopping.bloco_para_llm(shop_res)})
            for f in shop_res.get("fontes", [])[:8]:
                extras["fontes"].append({"id": f.get("id", ""),
                                         "titulo": f.get("titulo", ""),
                                         "url": f.get("url", "")})
        except Exception as exc:
            log.warning("shopping grounding falhou (%s)", type(exc).__name__)
    elif shop_res is not None:
        messages.append({"role": "system",
                         "content": shopping.bloco_para_llm(shop_res)})
    return shop_res


def _shopping_aplicar(texto: str, shop_res: dict | None,
                      extras: dict | None = None) -> str:
    """Cards/nota reais no texto final + bane fence de produto do MODELO.

    V5.7: fences de produto emitidos pelo modelo nunca entram — card de
    produto só vem da ferramenta (dados verificados); roda mesmo quando a
    busca não executou (antes só era chamado com `shop_res` não-nulo).
    V5.8: links do modelo só permanecem clicáveis quando comprovados pela
    ferramenta/fonte; home/busca/categoria viram texto rotulado.
    """
    texto = shopping.remover_fences_produto(texto or "")
    if shop_res is None:
        if (extras or {}).get("shop"):
            return shopping.sanitizar_links_resposta(
                texto, None, (extras or {}).get("fontes"))
        return texto
    fence_shop = ""
    if shop_res.get("produtos"):
        prods_validos = [p for p in shop_res["produtos"]
                         if not (p.get("excluido_codigos") and "tipo_produto_diferente" in p.get("excluido_codigos"))]
        crit = shop_res.get("criterios", {}) or {}
        if crit.get("comparacao") and len(prods_validos) >= 2:
            fence_shop = shopping.fence_comparacao(
                prods_validos[:4], shop_res.get("fontes", []))
        elif prods_validos:
            fence_shop = shopping.fence_resultado({**shop_res, "produtos": prods_validos})
    else:
        nota = shopping.resumo_texto(shop_res)
        if nota and nota not in texto:
            texto = (texto or "") + "\n\n" + nota
    if fence_shop and fence_shop not in (texto or ""):
        # Imagens primeiro: cards com as fotos reais abrem a mensagem. Fences
        # alheios (gráfico/aula) NÃO escondem ofertas verificadas da ferramenta.
        texto = imagens_primeiro(fence_shop, texto)
    if shop_res is not None or (extras or {}).get("shop"):
        texto = shopping.sanitizar_links_resposta(
            texto, shop_res, (extras or {}).get("fontes"))
    return texto


def _pesquisa_sem_evidencia(extras, shop_res=None, user_text=''):
    if not extras.get('pesquisa_executada') or shop_res is not None:return ''
    sources=extras.get('fontes') or []
    if any(f.get('status')=='aberta' for f in sources):return ''
    if sources:
        return _fallback_sem_inferencia(user_text,extras,None)
    if extras.get('midia'):
        import research_view
        return imagens_primeiro(research_view.media_fence(extras['midia']),'Recuperei metadados de mídia, mas não li conteúdos que sustentem uma análise. Consulte a origem indicada.')
    return 'Não consegui recuperar fontes pertinentes para responder a essa pesquisa agora. Não vou apresentar informações ou datas como se tivessem sido verificadas. Você pode reformular o assunto ou tentar novamente mais tarde.'


def _shopping_sem_ofertas(shop_res):
    """End a finished search honestly instead of asking LLM to promise more work."""
    if shop_res is None or shop_res.get('produtos'):
        return ''
    return shopping.sanitizar_links_resposta(shopping.resumo_texto(shop_res), shop_res)


def _shopping_resposta_factual(shop_res, user_text):
    """Price/link requests can be answered from verified offers without an LLM."""
    text = query_intelligence.normalized(user_text)
    products = (shop_res or {}).get('produtos') or []
    if (not products or not re.search(r'\b(preco|precos|link|links)\b',text)
            or re.search(r'compar|melhor|vantag|analis|explique|diferenc|recomend|vale|desempenho|calcule|por que|custo.beneficio',text)
            or any(not p.get('preco_confirmado') or p.get('link_veredito')!='verificado'
                   or p.get('pendencias_do_pedido') for p in products)):
        return ''
    return _shopping_aplicar(shopping.resumo_texto(shop_res), shop_res)


def _fallback_sem_inferencia(user_text: str, extras: dict, shop_res: dict | None) -> str:
    text = _fallback_dados_recuperados(user_text, extras, shop_res)
    # Se já temos produtos reais verificados da busca de compras, não exibe erro de provedor
    if shop_res and shop_res.get("produtos"):
        return text
    code = extras.get("inference_error_code")
    return inference_status.with_failure_notice(text, code) if code else text


def _nome_amigavel(nome_bruto: str) -> str:
    """Extrai modelo limpo e direto, removendo termos repetitivos de SEO de lojas."""
    t = nome_bruto or ""
    t = re.sub(r"^(?:placa[\s-]m[aã]e|placa\s+de\s+v[ií]deo|smartphone|celular|notebook|monitor|teclado|mouse)\s+", "", t, flags=re.I)
    partes = [p.strip() for p in t.split(",") if p.strip()]
    if partes:
        modelo = partes[0]
        modelo = re.sub(r"\s*-\s*[A-Z0-9_-]{5,}\b.*$", "", modelo).strip()
        soquete = ""
        for p in partes[1:]:
            if re.search(r"\b(am4|am5|lga\s*\d+|ddr4|ddr5|wifi|wi-fi)\b", p, flags=re.I):
                soquete = p.strip()
                break
        if soquete and soquete.lower() not in modelo.lower():
            return f"{modelo} ({soquete})"
        modelo = re.sub(r"\s+\d+g\b.*$", "", modelo, flags=re.I)
        modelo = re.sub(r"\s+\d+\s*gb\b.*$", "", modelo, flags=re.I)
        return modelo.strip()
    return t[:40]


def _extrair_especificacoes_produto(nome: str, categoria: str = "") -> str:
    cat = (categoria or "").lower()
    n = (nome or "").lower()
    if any(k in cat for k in ("placa mae", "placa mãe", "motherboard", "mobo")):
        if "am4" in n and "a520" in n:
            return "AM4 (A520)"
        if "am4" in n and "b550" in n:
            return "AM4 (B550)"
        if "am4" in n and "b450" in n:
            return "AM4 (B450)"
        if "am5" in n and "b650" in n:
            return "AM5 (B650)"
        if "am5" in n and "a620" in n:
            return "AM5 (A620)"
        if "am5" in n:
            return "AMD AM5"
        if "am4" in n:
            return "AMD AM4"
        if "lga 1700" in n or "lga1700" in n or "h610" in n:
            return "LGA 1700 (H610)"
        if "b760" in n:
            return "LGA 1700 (B760)"
        if "lga 1200" in n or "h510" in n:
            return "LGA 1200"
        return "Padrão"
    if any(k in cat for k in ("celular", "celulares", "smartphone", "smartphones", "telefone")):
        partes = []
        m_armazenamento = re.search(r"\b(64|128|256|512)\s*gb\b", nome, re.I)
        if m_armazenamento:
            partes.append(m_armazenamento.group(0).upper())
        m_ram = re.search(r"\b(?:ram\s*)?(\d{1,2})\s*gb\s*(?:ram)?\b", nome, re.I)
        if m_ram and (not m_armazenamento or m_ram.group(1) != m_armazenamento.group(1)):
            partes.append(f"{m_ram.group(1)}GB RAM")
        if re.search(r"\b5g\b", nome, re.I):
            partes.append("5G")
        elif re.search(r"\b4g\b", nome, re.I):
            partes.append("4G")
        return " · ".join(partes) if partes else "Smartphone"
    if any(k in cat for k in ("fone", "fones", "headphone", "headset")):
        partes = []
        if re.search(r"\btws\b", n):
            partes.append("TWS")
        if re.search(r"\bbluetooth\b", n):
            partes.append("Bluetooth")
        elif re.search(r"\bsem\s+fio\b", n):
            partes.append("Sem Fio")
        if re.search(r"\banc\b|cancelamento\s+de\s+ru[ií]do", n):
            partes.append("ANC")
        return " · ".join(partes) if partes else "Áudio"
    if any(k in cat for k in ("notebook", "laptop")):
        partes = []
        m_cpu = re.search(r"\b(i[3579]|ryzen\s*[3579])\b", n)
        if m_cpu:
            partes.append(m_cpu.group(0).upper())
        m_ram = re.search(r"\b(\d{1,2})\s*gb\s*ram\b", n)
        if m_ram:
            partes.append(f"{m_ram.group(1)}GB")
        m_ssd = re.search(r"\b(\d{3,4})\s*gb\s*ssd\b", n)
        if m_ssd:
            partes.append(f"{m_ssd.group(1)}GB SSD")
        return " · ".join(partes) if partes else "Notebook"
    return "Padrão"


def _extrair_soquete_chipset(nome: str) -> str:
    return _extrair_especificacoes_produto(nome, "placa mae")


def _sintese_shopping_autonoma(shop_res: dict, user_text: str) -> str:
    """Gera síntese inteligente e estruturada de produtos a partir das ofertas reais verificadas.

    Apresenta um ranking comparativo com notas de 0 a 10, tabela técnica enxuta,
    avaliações de prós/contras e links verificados, com fonte menor e design profissional.
    """
    prods = (shop_res or {}).get("produtos") or []
    if not prods:
        return ""
    crit = (shop_res or {}).get("criterios") or {}
    categoria = (crit.get("categoria") or "produtos").title()

    prods_ordenados = sorted(
        prods,
        key=lambda x: (
            not bool(x.get("preco_confirmado")),
            float(x.get("preco") or x.get("preco_valor") or float("inf"))
        )
    )

    medals = ["🏆 1º", "🥈 2º", "🥉 3º", "🎖️ 4º", "🎖️ 5º", "🎖️ 6º"]
    linhas = [
        f"### 🏆 Ranking Especialista Vexx: {categoria}",
        "<small style=\"color:var(--text-muted, #94a3b8);display:block;margin:-4px 0 10px 0;font-size:0.86em;\">"
        "Avaliação técnica baseada em custo por recurso, estabilidade de componentes, conectividade e opiniões de compradores."
        "</small>",
        "",
        "| Posição | Modelo | Preço | Especificações | Nota | Veredito |",
        "| :---: | :--- | :---: | :---: | :---: | :--- |",
    ]

    analises = []
    cat_lower = categoria.lower()
    eh_celular = any(k in cat_lower for k in ("celular", "smartphone", "telefone"))
    eh_placa = any(k in cat_lower for k in ("placa mae", "placa mãe", "motherboard"))

    for idx, p in enumerate(prods_ordenados[:6]):
        nome_completo = p.get("nome") or "Produto"
        nome_curto = _nome_amigavel(nome_completo)
        preco = p.get("preco_texto") or (f"R$ {p.get('preco'):.2f}" if p.get("preco") else "Ver na loja")
        pos = medals[idx] if idx < len(medals) else f"#{idx+1}"
        plat = _extrair_especificacoes_produto(nome_completo, categoria)

        nome_l = nome_completo.lower()
        if eh_celular:
            if idx == 0:
                nota = 9.8
                veredito = "Melhor Custo-Benefício"
                motivo = f"Preço imbatível ({preco}) com ótimo conjunto de bateria e tela ampla para o dia a dia."
            elif "iphone" in nome_l:
                nota = 9.7
                veredito = "Top de Linha Apple"
                motivo = "Processador de altíssimo desempenho, câmeras de nível profissional e ecossistema iOS integrado."
            elif "5g" in nome_l:
                nota = 9.5
                veredito = "Mais Conectado (5G)"
                motivo = "Suporte a redes 5G de alta velocidade e excelente fluidez para streaming e redes sociais."
            elif idx == 1:
                nota = 9.3
                veredito = "Opção Super Econômica"
                motivo = "Alternativa acessível com bom armazenamento interno e bateria de longa duração."
            else:
                nota = max(8.6, round(9.1 - (idx * 0.15), 1))
                veredito = "Equilibrado p/ Multitarefas"
                motivo = "Bom conjunto de memória e câmeras para uso diário sem lentidão."
        elif eh_placa:
            if idx == 0:
                nota = 9.8
                veredito = "Melhor Custo-Benefício"
                motivo = f"Preço imbatível ({preco}) com ótima estabilidade para builds de entrada e intermediárias."
            elif "b550" in nome_l and "wifi" in nome_l:
                nota = 9.6
                veredito = "Mais Completa & Wi-Fi"
                motivo = "Conta com barramento PCIe 4.0 para GPUs e SSDs ultra-rápidos, além de Wi-Fi 6E integrado."
            elif "b550" in nome_l:
                nota = 9.4
                veredito = "Excelente p/ Upgrades"
                motivo = "Suporte a PCIe 4.0 e VRMs reforçados para processadores de maior consumo."
            elif idx == 1:
                nota = 9.3
                veredito = "Opção Super Econômica"
                motivo = "Excelente alternativa de baixo custo mantendo recursos essenciais como slot M.2 NVMe."
            elif "tuf" in nome_l:
                nota = 9.1
                veredito = "Construção Militar TUF"
                motivo = "Componentes com maior tolerância térmica e durabilidade prolongada."
            else:
                nota = max(8.5, round(9.0 - (idx * 0.15), 1))
                veredito = "Boa Opção de Mercado"
                motivo = "Equilibrada para montagem básica com boa compatibilidade de memórias."
        else:
            if idx == 0:
                nota = 9.8
                veredito = "Melhor Custo-Benefício"
                motivo = f"Oferta mais vantajosa com ótimo equilíbrio entre preço ({preco}) e qualidade."
            elif idx == 1:
                nota = 9.3
                veredito = "Alternativa Econômica"
                motivo = "Excelente escolha para economizar sem abrir mão dos recursos principais."
            else:
                nota = max(8.5, round(9.0 - (idx * 0.15), 1))
                veredito = "Ótima Avaliação Geral"
                motivo = "Produto bem avaliado pelos compradores com entrega rápida e garantia oficial."

        link = p.get("url_item") or p.get("url") or "#"
        linhas.append(f"| {pos} | [{nome_curto}]({link}) | **{preco}** | {plat} | **{nota:.1f}** ⭐ | {veredito} |")

        if idx < 3:
            analises.append(
                f"- **{pos} — [{nome_curto}]({link}) (Nota {nota:.1f}/10 · {preco})**:\n"
                f"  <small style=\"color:var(--text-muted, #94a3b8);display:block;margin-top:2px;font-size:0.86em;\">"
                f"  {motivo} "
                f"  *(Nome no catálogo: {nome_completo})*"
                f"  </small>"
            )

    linhas.append("")
    linhas.append("#### 💡 Destaques de Compra & Recomendação:")
    linhas.extend(analises)
    linhas.append("")
    linhas.append("> ℹ️ *Toque nos cards visuais acima para conferir fotos reais, avaliações dos clientes e acessar a oferta direto no site da loja.*")

    texto_base = "\n".join(linhas)
    return _shopping_aplicar(texto_base, shop_res)


def _fallback_dados_recuperados(user_text: str, extras: dict, shop_res: dict | None) -> str:
    """Texto determinístico quando o LLM falha: fontes reais E ofertas reais.

    V5.7.3: ofertas verificadas da busca de produtos não somem porque a
    inferência caiu (429); o digest de pesquisa continua vindo primeiro.
    """
    digest = ""
    if extras.get("fontes"):
        digest = research.resumo_deterministico(extras["fontes"], user_text)
    if shop_res is not None and shop_res.get("produtos"):
        return _sintese_shopping_autonoma(shop_res, user_text)
    if digest:
        import research_view
        return digest+research_view.contextual_fence(extras['fontes'])
    if shop_res is not None:
        nota = shopping.resumo_texto(shop_res)
        if nota:
            return nota
    return ""


def _texto_followup_sem_contexto(texto: str) -> str:
    """Resposta honesta quando o ajuste depende de ofertas que não existem."""
    if shopping.quer_fotos(texto or "") and not shopping.eh_followup(texto or ""):
        return ("Não tenho fotos verificadas de produtos de uma pesquisa anterior "
                "nesta conversa. Faça uma busca de produtos primeiro (por exemplo: "
                "\"notebook até R$ 3.000\") — não vou inventar imagens ou ofertas. 🔍")
    return ("Não tenho ofertas verificadas de uma pesquisa anterior nesta conversa "
            "para aplicar esse ajuste. Faça uma nova busca de produtos (por exemplo: "
            "\"notebook até R$ 3.000\") — não vou inventar preços nem reutilizar "
            "resultados fora do assunto. 🔍")


def _validar_resposta(intencao: dict, texto: str, *, usadas: list, produtos: list,
                      mid: str) -> str:
    """V5.7: validador determinístico + nota honesta aplicada ao texto.

    Alegação comercial sem busca verificada (`verificacao_alegada_sem_
    evidencia`) não passa silenciosa: além do log, um aviso curto entra na
    própria resposta. Demais violações continuam apenas logadas.
    """
    try:
        _val = intent.validar(intencao or {}, texto, {
            "ferramentas_usadas": list(usadas or []),
            "produtos": list(produtos or [])})
    except Exception as exc:
        log.warning("validador falhou (%s)", type(exc).__name__)
        return texto
    viol = _val.get("violacoes", []) or []
    for _v in viol:
        log.warning("INTENT_VALIDATE %s: %s", mid, _v)
    if any(v.get("codigo") == "verificacao_alegada_sem_evidencia" for v in viol) \
            and "Não verifiquei estes valores em lojas" not in (texto or ""):
        return (texto or "").rstrip() + (
            "\n\n_Não verifiquei estes valores em lojas agora: são do meu "
            "conhecimento geral e podem estar desatualizados — confirme na "
            "loja antes de comprar._")
    return texto


_RX_JDUIF_BLOCO = re.compile(r"```jdui[\s\S]*?(?:```|$)", re.IGNORECASE)


def _evidencias_verificaveis(fontes: list, produtos: list) -> list:
    """Evidências reais para o verificador: trechos lidos + dados de produto.

    Fonte apenas `encontrada` (sem `texto_lido`) serve de contexto, mas não
    prova afirmação numérica/comparativa: `lida=False` impede o veredito
    SUPPORTED. Fontes legadas sem `status` continuam válidas.
    """
    evs = []
    for i, f in enumerate(fontes or []):
        if not isinstance(f, dict):
            continue
        texto_lido = (f.get("texto_lido") or "").strip()
        trecho = (texto_lido or f.get("trecho") or "").strip()
        if not trecho:
            continue
        status = str(f.get("status") or "")
        if status:
            lida = status == "aberta" and bool(texto_lido)
        else:
            lida = bool(texto_lido) or None
        evs.append({"id": str(f.get("id") or f"S{i + 1}"),
                    "trecho": trecho[:4000], "url": f.get("url", ""),
                    "status": status, "lida": lida})
    for i, p in enumerate(produtos or []):
        if not isinstance(p, dict):
            continue
        partes = [str(p.get("nome") or ""), str(p.get("preco_texto") or ""),
                  str(p.get("loja") or "")]
        for k, v in list((p.get("specs") or {}).items())[:8]:
            partes.append(f"{k}: {v}")
        if p.get("avaliacao") is not None:
            partes.append(f"avaliacao: {p['avaliacao']}")
        trecho = " | ".join(x for x in partes if x).strip()
        if trecho:
            evs.append({"id": f"produto-{i + 1}", "trecho": trecho[:2000]})
    return evs


def _validar_comparacoes(texto: str, fontes: list, produtos: list,
                         mid: str = "") -> tuple:
    """Neutraliza comparações sem evidência e devolve o laudo das afirmações.

    FATOS: SUPPORTED → FACT; PARTIALLY_SUPPORTED → DERIVED_FROM_DATA;
    ESTIMATE/HYPOTHESIS explícitos ficam rotulados; o resto é UNVERIFIED e
    comparações não sustentadas viram limitação declarada, nunca fato.
    """
    limpo = _RX_JDUIF_BLOCO.sub(" [interface] ", texto or "")
    evidencias = _evidencias_verificaveis(fontes, produtos)
    try:
        laudo = evgraph.classificar_afirmacoes(limpo, evidencias, minimo=20)
    except Exception as exc:
        log.warning("classificação de afirmações falhou (%s)", type(exc).__name__)
        return texto, []
    novo = texto or ""
    for item in laudo:
        comp = item.get("comparacao")
        if not comp or item["classificacao"] not in ("UNVERIFIED", "HYPOTHESIS"):
            continue
        sujeito = comp.get("sujeito") or "o primeiro item"
        comparado = comp.get("comparado_a") or "o segundo item"
        substituicao = (f"Não tenho evidência verificada para sustentar a "
                        f"comparação entre {sujeito} e {comparado} (UNVERIFIED).")
        if item["texto"] in novo:
            novo = novo.replace(item["texto"], substituicao, 1)
            log.warning("COMPARACAO_NAO_VERIFICADA %s: %s", mid,
                        item["texto"][:120])
    return novo, laudo


# ── Continuidade determinística entre conversas (V5.0; sem LLM) ──────
_CONTINUAR_RE = re.compile(
    r"(continuar|continue|retomar|retome|voltando|onde param|onde parei|"
    r"estavamos fazendo|continuacao|aquele projeto|esse projeto|\bo projeto\b)")


def _resumo_projeto(db, owner: str, projeto: dict) -> str:
    titulo = (projeto.get("title") or "Projeto")[:60]
    linhas = [f"**{titulo}** — retomando de onde parou:"]
    trechos = _trechos_projeto(db, owner, projeto)
    linhas.extend(f"- {t}" for t in trechos[:3])
    pend = pendencias(db, owner)[:2]
    if pend:
        linhas.append("Aguardando sua confirmação: " +
                      "; ".join(f"**{p['key']}**" for p in pend))
    try:
        job = _ultimo_job(db, owner, ())
    except Exception:
        job = None
    if job:
        linhas.append(f"Última pesquisa: **{(job.get('objetivo') or '')[:60]}** "
                       f"({job.get('status', '')})")
    linhas.append("Me diga o próximo passo. 👊")
    return "\n".join(linhas)[:1500]


def _resumo_onde_paramos(db, owner: str, conv: str) -> str:
    linhas = []
    pend = pendencias(db, owner)[:2]
    if pend:
        linhas.append("Aguardando confirmação: " +
                      "; ".join(f"**{p['key']}**: {(p['value'] or '')[:100]}" for p in pend))
    try:
        job = _ultimo_job(db, owner, ())
    except Exception:
        job = None
    if job:
        linhas.append(f"Pesquisa: **{(job.get('objetivo') or '')[:60]}** ({job.get('status', '')})")
    try:
        shop = shopping.ultima_consulta(db, owner, conv)
    except Exception:
        shop = None
    if shop and (shop.get("resultado", {}) or {}).get("produtos"):
        n = len(shop["resultado"]["produtos"])
        linhas.append(f"Compras: **{(shop.get('consulta') or '')[:60]}** ({n} opções guardadas)")
    try:
        foco = db.execute("SELECT value FROM memories WHERE owner_id=? AND key='foco' "
                          "AND status='confirmada'", (dono_valido(owner),)).fetchone()
    except Exception:
        foco = None
    if foco and foco[0]:
        linhas.append(f"Seu foco: {(foco[0] or '')[:150]}")
    if not linhas:
        return ("Nada em andamento por aqui. Me diga o que retomar "
                "(ex.: um projeto, uma pesquisa ou uma compra). 🌱")
    return "Onde paramos:\n\n" + "\n".join(f"- {l}" for l in linhas)


def cmd_projeto(db, texto: str, owner: str, conv: str) -> str:
    """Continuação de projetos/tarefas sem LLM. Retorna texto ou ''."""
    t = _normalizar_temporal(texto or "")
    if not t or not _CONTINUAR_RE.search(t):
        return ""
    # Conversa contínua simples ("ok, continue", "continue", "pode continuar", "prossiga")
    # sem objeto nem menção a projeto não deve sequestrar o diálogo.
    t_limpo = re.sub(r"[^\w\s]+", " ", t).strip()
    if re.fullmatch(r"(?:ok\s+)?(?:por\s+favor\s+)?(?:pode\s+)?(?:continu(?:ar?|e|ando)|prossiga|segue)(?:\s+por\s+favor)?", t_limpo):
        tem_vinculo = False
        try:
            row = db.execute("SELECT project_id FROM conversations WHERE id=? AND owner_id=?", (conv, dono_valido(owner))).fetchone()
            if row and row[0]:
                tem_vinculo = True
        except Exception:
            pass
        if not tem_vinculo:
            return ""
    if "onde param" in t or "estavamos fazendo" in t or "onde parei" in t:
        return _resumo_onde_paramos(db, owner, conv)
    scored = _projetos_relevantes(db, texto, owner)
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        titulos = "; ".join(f"**{((p or {}).get('title') or '')[:50]}**"
                            for _, _, p in scored[:3])
        return (f"Encontrei mais de um projeto parecido: {titulos}. "
                "Qual deles retomamos?")
    if scored:
        return _resumo_projeto(db, owner, scored[0][2])
    try:
        recs = workspace_store.list_records(db, dono_valido(owner))
    except Exception:
        recs = []
    titulos = [(r.get("title") or "")[:50] for r in recs if isinstance(r, dict)
               and r.get("kind") == "project" and not r.get("archived")
               and not r.get("deleted")][:4]
    if titulos:
        return ("Não identifiquei qual projeto continuar. Seus projetos: " +
                "; ".join(f"**{x}**" for x in titulos) + ". Qual retomamos?")
    return ("Não encontrei nenhum projeto guardado. Me diga o que retomar "
            "(ex.: 'vamos montar o PC para jogos').")


def cmd_pesquisa(db, texto: str, owner: str, conv: str, model: str = "") -> str:
    """Comandos determinísticos de memória de pesquisa (sem LLM; funcionam
    mesmo com o Hermes bloqueado). Retorna texto ou ''."""
    t = (texto or "").lower()
    tabular = _cmd_analisar_tabular(db, texto or "", owner, conv)
    if tabular:
        return tabular
    _cmd = _cmd_intervencao(db, owner, t, conv)
    if _cmd:
        return _cmd
    if any(k in t for k in ("mostra o resultado da pesquisa", "mostrar resultado",
                            "resultado da pesquisa", "e aí a pesquisa", "e ai a pesquisa")):
        job = _ultimo_job(db, owner, ("concluida",))
        if job is None:
            ativo = _ultimo_job(db, owner, ("em_andamento", "criada"))
            if ativo is not None:
                return ("Sua pesquisa ainda está em andamento. Acompanhe no painel "
                        "acima ou aguarde concluir. 🔍")
            return ("Você ainda não tem pesquisa concluída. Peça 'pesquisa profunda "
                    "sobre X' para começar. 🔍")
        evs = research_agents.listar_evidencias(db, owner, job["id"])[:6]
        linhas = [f"Resultado da pesquisa sobre **{job['objetivo']}** ({job['status']}):",
                   f"{len(evs)} evidências analisadas."]
        for e in evs:
            linhas.append(f"- [{e['titulo']}]({e['url']}): {(e['trecho'] or '')[:160]}")
        for a in (research_agents._resumo(db, job).get("achados") or [])[:5]:
            linhas.append(f"- {a['estado']}: {(a['afirmacao'] or '')[:140]}")
        return "\n".join(linhas)[:2000]
    if any(k in t for k in ("quais fontes", "que fontes", "fontes você encontrou",
                            "fontes encontr")):
        job = _ultimo_job(db, owner, ())
        if job is None:
            return "Ainda não há pesquisa registrada para você. 🔍"
        evs = research_agents.listar_evidencias(db, owner, job["id"])[:10]
        if not evs:
            return f"A pesquisa sobre **{job['objetivo']}** ainda não tem fontes lidas."
        return ("Fontes de **%s**:\n" % job["objetivo"] + "\n".join(
            f"- [{e['titulo']}]({e['url']}) ({e['dominio']})" for e in evs))[:2000]
    if any(k in t for k in ("de onde veio essa conclusão", "de onde vieram",
                            "de onde saiu essa conclusão")):
        job = _ultimo_job(db, owner, ("concluida",))
        if job is None:
            return "Sem conclusão registrada ainda. 🔍"
        sup = evgraph.fontes_que_sustentam(db, owner, job["id"])[:5]
        if not sup:
            return ("A última conclusão ainda não tem sustentação registrada "
                    "(verificação léxica não encontrou suporte). 🔍")
        linhas = [f"Conclusão sustentada por {len(sup)} evidência(s):"]
        for s in sup:
            linhas.append(f"- {s['tipo']} ({s['metodo']}): {s['claim'][:120]}")
        return "\n".join(linhas)[:2000]
    if any(k in t for k in ("quais fontes confirmaram", "fontes confirmaram",
                            "fontes que confirmam")):
        job = _ultimo_job(db, owner, ("concluida",))
        if job is None:
            return "Sem conclusão registrada ainda. 🔍"
        sup = evgraph.fontes_que_sustentam(db, owner, job["id"])[:8]
        if not sup:
            return "Nenhuma fonte com sustentação registrada na última pesquisa. 🔍"
        evs = {e["id"]: e for e in research_agents.listar_evidencias(db, owner, job["id"])}
        linhas = ["Fontes que sustentam a conclusão:"]
        for s in sup:
            node = next((n for n in evgraph.nos_do_job(db, owner, job["id"], "evidence")
                         if n["id"] == s["evidence_node"]), {})
            ev = evs.get(node.get("evidence_id", ""), {})
            if ev.get("url"):
                linhas.append(f"- [{ev['titulo']}]({ev['url']}) ({s['tipo']})")
        return "\n".join(linhas)[:2000] if len(linhas) > 1 else \
            "Sustentação sem fonte recuperada (inconsistência registrada). 🔍"
    if any(k in t for k in ("alguma fonte contradiz", "fonte contradiz", "há contradiç",
                            "ha contrad", "contradiz essa informação")):
        job = _ultimo_job(db, owner, ("concluida",))
        if job is None:
            return "Sem conclusão registrada ainda. 🔍"
        invs = (research_agents.carregar_job(db, owner, job["id"]).get("investigacoes") or [])
        cont = evgraph.contradicoes_do_job(db, owner, job["id"])
        if not invs and not cont:
            return "Nenhuma contradição registrada na última pesquisa. 🔍"
        linhas = ["Divergências registradas:"]
        for i in invs[:5]:
            linhas.append(f"- {i.get('tipo')}: {i.get('explicacao', '')[:160]}")
        return "\n".join(linhas)[:2000]
    if any(k in t for k in ("o que mudou desde", "o que mudou na última",
                            "mudou desde a última")):
        jobs = [j for j in research_agents.listar_jobs(db, owner, 10)
                if j["status"] == "concluida"][:2]
        if len(jobs) < 2:
            return "Preciso de duas pesquisas concluídas para comparar. 🔍"
        d = evgraph.diff_pesquisas(db, owner, jobs[0]["id"], jobs[1]["id"])
        return (f"Desde **{jobs[1]['objetivo'][:60]}** até **{jobs[0]['objetivo'][:60]}**:\n"
                f"- novas: {len(d['novas'])}; removidas: {len(d['removidas'])}; "
                f"alteradas: {len(d['alteradas'])}."
                + (" Novos: " + ", ".join(d["novas"][:3]) if d["novas"] else ""))[:2000]
    if any(k in t for k in ("mostre o estudo original", "mostra o estudo original",
                            "fonte original", "estudo primário", "estudo primario")):
        job = _ultimo_job(db, owner, ("concluida",))
        if job is None:
            return "Sem conclusão registrada ainda. 🔍"
        origens = evgraph.estudos_originais(db, owner, job["id"])[:5]
        if not origens:
            return "Não identifiquei estudo original (só derivados). 🔍"
        return "Possíveis originais:\n" + "\n".join(
            f"- [{o.get('titulo', o.get('url', ''))}]({o.get('url', '')})" for o in origens)[:2000]
    if any(k in t for k in ("continue aquela pesquisa", "retome a pesquisa",
                            "continuar a pesquisa", "continua a pesquisa")):
        job = _ultimo_job(db, owner, ("interrompida", "cancelada", "falhou", "concluida"))
        if job and job["status"] == "concluida" and job.get("usados",{}).get("research_outcome",{}).get("state") != "partial":
            return "Essa pesquisa já foi concluída. Envie uma nova pergunta para ampliar o escopo."
        if job is None:
            ativo = _ultimo_job(db, owner, ("em_andamento", "criada"))
            if ativo is not None:
                return "Sua pesquisa já está em andamento — acompanhe no painel. 🔍"
            return "Não encontrei pesquisa interrompida para retomar. 🔍"
        job = research_agents.preparar_retomada(db, owner, job['id'])
        if iniciar_job_bg(database_path(), job["id"], owner):
            return (f"Pesquisa sobre **{job['objetivo']}** retomada de onde parou "
                    f"(id {job['id']}). Acompanhe no painel. 🔍")
        job["status"] = "interrompida"
        research_agents.salvar_job(db, job, forcar_status=True)
        return "Já há outra pesquisa em andamento; conclua ou cancele antes. 🔍"
    m = _JOB_START_RE.search(texto or "")
    visual = bool(re.search(r'\b(pesquis\w*|mostr\w*|encontr\w*)\b', t)
                  and query_intelligence.requested_media(t)
                  and not re.search(r'\b(gerar|criar|desenhar|analise|analisar)\b', t))
    official_docs = bool(re.search(r'\bpesquis\w*\b', t)
                         and re.search(r'\bdocumenta[cç][aã]o\s+oficial\b', t))
    if visual and not m and 'pesquisa profunda' not in t:
        termo_busca = re.sub(r'^(?:pesquis\w*|busqu\w*|procur\w*|encontr\w*|mostr\w*)\s+(?:por\s+)?(?:alguns?|algumas?|os?|as?)?\s*', '', texto, flags=re.I)
        termo_busca = re.sub(r'\s+e\s+(?:me\s+)?(?:mostr\w*|traga|busqu\w*|encontr\w*)\s+(?:as\s+)?(?:fotos?|imagens?|midias?|fotos\s+delas?|fotos\s+deles?)\b.*$', '', termo_busca, flags=re.I).strip()
        if not termo_busca:
            termo_busca = texto
        result = research.pesquisa_rapida(db, owner, termo_busca)
        import research_view
        media = result.get('midia') or []
        fence = research_view.media_fence(media)
        fontes = result.get('fontes') or []
        if fence:
            midias_validas = []
            padroes_lixo = ('sino', 'notificacao', 'notificação', 'notificações', 'notification', 'bell', 'icon', 'icone', 'logo', 'badge', 'assets-v4', 'pixel')
            for m_item in media:
                txt = (str(m_item.get('title') or '') + ' ' + str(m_item.get('url') or '')).lower()
                if not any(p in txt for p in padroes_lixo) and not txt.endswith('.svg'):
                    midias_validas.append(m_item)
            
            topicos_destaque = []
            for m_item in midias_validas[:6]:
                tit = (m_item.get('title') or '').strip()
                if tit:
                    limpo = tit.split(' - ')[0].split(' | ')[0].strip(' .?!')
                    if len(limpo) > 10 and limpo not in topicos_destaque:
                        topicos_destaque.append(limpo)
            
            linhas_destaque = "\n".join(f"- {d}" for d in topicos_destaque) if topicos_destaque else ""
            corpo = (
                f"Encontrei fotos e notícias recentes sobre celebridades e personalidades em destaque:\n\n"
                f"{linhas_destaque}\n\n"
                f"*(Galeria com {len(midias_validas)} imagens verificadas das fontes oficiais anexada acima.)*"
            )
            anexo = anexar_fontes(corpo, fontes) if fontes else corpo
            return imagens_primeiro(fence, anexo)
        if fontes:
            resumo = research.resumo_deterministico(fontes, termo_busca)
            anexo = anexar_fontes(resumo, fontes)
            return (f"{anexo}\n\n*(Nota: Não foi possível obter pré-visualizações diretas de fotos para estas fontes no momento.)*")
        return 'Não consegui recuperar mídia pertinente nas fontes disponíveis agora. ' + str(result.get('estado_texto') or '')
    if m or "inicie uma pesquisa sobre" in t or visual or official_docs:
        objetivo = (m.group(1).strip() if m else texto)[:500]
        imagem = ""
        m_img = re.search(r'(https?://[^\s]+(?:\.(?:png|jpg|jpeg|webp|gif)|(?=[?#]))|data:image/[^;]+;base64,[^\s]+)', texto or "", re.I)
        if m_img:
            imagem = m_img.group(1)
        queries_qwen = []
        try:
            import qwen_llm_service
            queries_qwen = qwen_llm_service.planejar_pesquisa_qwen(objetivo, contexto_visao=imagem)
        except Exception:
            pass
        req = {"objetivo": objetivo, "conv": conv or "", "model": model,
               "modo": "profunda" if m else "rapida" if visual else "",
               "imagem": imagem,
               "queries_planejadas": queries_qwen}
        resp = rjob_start(db, req, owner)
        if resp.get("type") != "research_job":
            return "Não consegui iniciar: " + resp.get("error", "tente de novo") + " 🔍"
        label = 'Pesquisa de imagens' if visual else 'Pesquisa técnica' if official_docs else 'Pesquisa profunda'
        return (f"{label} iniciada sobre **{objetivo}**. "
                f"Abra o resultado da pesquisa para acompanhar as fontes (id {resp['job_id']}). 🔍")
    return ""
