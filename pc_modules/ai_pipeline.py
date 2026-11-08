"""Módulo do PC Agent: Guarda de streaming, resposta direta, pipeline completo (ai_completa) e worker de stream."""
import evidence_graph as evgraph
import hermes_bridge
import jdui
import json
import re
import shopping
import threading
import time
import tool_protocol

from assistant_identity import limitar_afirmacoes_nao_suportadas
from pathlib import Path
from websockets.exceptions import ConnectionClosed

from pc_modules.db_core import (
    _SINT_POOL, _sintetizar_isolado, database_path, DONO_PADRAO, gerar_stream, gerar_texto,
    log, modelos_tentativa, open_db,
)
from pc_modules.intents_jdui import intencao_imagem, JDUI_SINTETIZAR, sintetizar_jdui
from pc_modules.context_providers import (
    _aplicar_arquivos_gerados, ai_estado, ai_marcar, ai_montar_mensagens, anexar_fontes,
    imagens_primeiro,
)
from pc_modules.research_commands import (
    _fallback_sem_inferencia, _pesquisa_sem_evidencia, _shopping_aplicar, _shopping_executar,
    _shopping_resposta_factual, _shopping_sem_ofertas, _texto_followup_sem_contexto,
    _validar_comparacoes, _validar_resposta, cmd_pesquisa, cmd_projeto, cmd_qualidade,
)
from pc_modules.memory_store import (
    _resposta_temporal_direta, cmd_identidade, interpretar_comando_memoria,
)
from pc_modules.study_lifecycle import (
    ai_guardar_resposta, ai_preparar, intencao_aula, intencao_grafico_evolucao, intencao_prova,
    intencao_reforco, sintetizar_aula, sintetizar_grafico_evolucao, sintetizar_prova,
    sintetizar_reforco,
)
from pc_modules.calendar_projects import aprender_com_conversa
from pc_modules.visual_fences import (
    cmd_dados_atuais, cmd_model3d, fence_de_evidencias, fence_de_fontes, fence_de_grafo,
    fence_transformacao_visual, intencao_transformar_pesquisa,
)

def _texto_seguro(texto: str, mid: str = "") -> str:
    """Última barreira: protocolo de ferramenta + fatos de identidade.

    A barreira principal fica no adaptador (bridge/providers); esta garante
    que caminhos alternativos, testes e respostas antigas não publiquem uma
    chamada interna nem uma afirmação corporativa inventada sobre a Vexx AI.
    """
    limpo, erros = tool_protocol.sanitizar_texto(texto or "")
    for erro in erros:
        log.warning("TOOL_PROTOCOL_FINAL %s %s: %s", mid[-8:] if mid else "-",
                    erro.get("codigo"), erro.get("ferramenta") or "?")
    return limitar_afirmacoes_nao_suportadas(limpo)


class _GuardaStreamResposta:
    """Evita que identidade/comparação erradas apareçam antes da correção final.

    Texto sem marcadores de risco continua fluindo imediatamente (TTFT). Se o
    delta contém "vex"/autoidentificação ou um termo comparativo, a frase é
    segurada até a pontuação, validada e só então enviada. No fim, o restante
    passa pela mesma barreira. Assim o cliente nunca vê "Vexxia" ou uma
    comparação não sustentada e depois um texto diferente em `ai_done`.
    """

    _TOKENS_RISCO = (
        "vexx", "vexxia", "vex", "meu nome", "eu sou", "pode me chamar",
        "mais", "menos", "maior", "menor", "melhor", "pior", "superior",
        "inferior", "rápido", "rapido", "lento", "eficiente", "caro", "barato",
        "<tool_call",
    )
    _RX_FIM_FRASE = re.compile(r"(?<=[.!?])(?:\s+|$)")

    def __init__(self, fontes: list | None = None, produtos: list | None = None,
                 mid: str = ""):
        self.fontes = fontes or []
        self.produtos = produtos or []
        self.mid = mid
        self.buffer = ""
        self.emitido: list[str] = []

    def _tem_risco(self, texto: str) -> bool:
        baixo = (texto or "").lower()
        return any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", baixo)
                   for t in self._TOKENS_RISCO)

    def _sufixo_risco(self, texto: str) -> int:
        """Sufixo que pode ser o começo de um token de risco (ex.: "vex")."""
        baixo = (texto or "").lower()
        for n in range(min(24, len(baixo)), 0, -1):
            suf = baixo[-n:]
            if any(t.startswith(suf) for t in self._TOKENS_RISCO):
                return n
        return 0

    def _seguro(self, texto: str) -> str:
        if re.search(r'<tool_call\b',texto,re.I):return ''
        seguro = limitar_afirmacoes_nao_suportadas(texto)
        if evgraph.detectar_comparacao(seguro):
            seguro, _ = _validar_comparacoes(
                seguro, self.fontes, self.produtos, mid=self.mid)
        return seguro

    def _emitir(self, trecho: str, saida: list) -> None:
        if trecho:
            saida.append(trecho)
            self.emitido.append(trecho)

    def alimentar(self, trecho: str) -> list[str]:
        self.buffer += str(trecho or "")
        saida: list[str] = []
        while self.buffer:
            if self._tem_risco(self.buffer):
                m = self._RX_FIM_FRASE.search(self.buffer)
                if not m:
                    break
                corte = m.end()
                self._emitir(self._seguro(self.buffer[:corte]), saida)
                self.buffer = self.buffer[corte:]
                continue
            n = self._sufixo_risco(self.buffer)
            if n:
                self._emitir(self.buffer[:-n], saida)
                self.buffer = self.buffer[-n:]
                break
            self._emitir(self.buffer, saida)
            self.buffer = ""
        return saida

    def finalizar(self) -> list[str]:
        saida: list[str] = []
        if self.buffer:
            self._emitir(self._seguro(self.buffer), saida)
            self.buffer = ""
        return saida

    @property
    def texto_emitido(self) -> str:
        return "".join(self.emitido)


def _complemento_stream(final: str, exibido: str) -> str:
    """Delta que completa o que já foi exibido, sem repetir o prefixo comum.

    Normalmente `final` começa por `exibido`. Quando o backend acrescenta
    cards/fontes no início, o trecho novo é anexado ao fim (o `ai_done`
    continua sendo a fonte autoritativa para persistência).
    """
    final, exibido = final or "", exibido or ""
    if not exibido:
        return final
    if final.startswith(exibido):
        return final[len(exibido):]
    pos = final.find(exibido)
    if pos >= 0:
        return final[:pos] + final[pos + len(exibido):]
    i = 0
    while i < len(final) and i < len(exibido) and final[i] == exibido[i]:
        i += 1
    return final[i:]


def ai_resposta_direta(db, mid, conv, modelo, reply_id, texto, owner=DONO_PADRAO) -> dict:
    """Resposta sem LLM (comandos de memória). Salva e marca como completa."""
    texto = _texto_seguro(texto, mid)
    ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
    ai_guardar_resposta(db, mid, conv, modelo, reply_id, texto, owner)
    return {"reply_id": reply_id, "response_text": texto, "model": modelo}


def ai_completa(db, payload: dict, cfg: dict) -> dict:
    prep = ai_preparar(db, payload, cfg)
    if "error" in prep or "replay" in prep or "busy" in prep:
        return prep
    mid, conv, modelo = payload["message_id"], prep["conversation_id"], prep["model"]
    owner = prep.get("owner", DONO_PADRAO)
    atual = cmd_dados_atuais(db, prep.get('user_text',''), owner, conv, prep.get('contexto_local',{}), payload.get('message_id'))
    if atual:
        return ai_resposta_direta(db, mid, conv, modelo, prep['reply_id'], atual, owner)
    model_response = cmd_model3d(db, prep.get("user_text", ""), owner, conv, payload.get('scene_state',''),
                                 pesquisa_web=bool(cfg.get("pesquisa_web", True)))
    if model_response:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], model_response, owner)
    cmd = interpretar_comando_memoria(db, prep.get("user_text", ""), owner)
    if cmd:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cmd[0], owner)
    rp = cmd_pesquisa(db, prep.get("user_text", ""), owner, conv,
                     model=payload.get('model') or ('' if cfg.get('model_implicit') else modelo))
    if rp:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], rp, owner)
    cp = cmd_projeto(db, prep.get("user_text", ""), owner, conv)
    if cp:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cp, owner)
    # Follow-up de shopping: reusa ofertas verificadas; sem contexto, admite
    # honestamente em vez de cair na web/LLM e misturar fontes sem relação.
    if shopping.eh_followup(prep.get("user_text", "")) or \
            shopping.quer_fotos(prep.get("user_text", "")):
        fup = shopping.responder_followup(
            db, owner, conv, prep.get("user_text", ""))
        if fup:
            texto_fup = imagens_primeiro(fup.get("fence"), fup["texto"])
            return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"],
                                      texto_fup, owner)
        if shopping.followup_sem_contexto(prep.get("user_text", "")):
            return ai_resposta_direta(
                db, mid, conv, modelo, prep["reply_id"],
                _texto_followup_sem_contexto(prep.get("user_text", "")), owner)
    rq = cmd_qualidade(db, prep.get("user_text", ""), owner)
    if rq:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], rq, owner)
    cmd_id = cmd_identidade(prep.get("user_text", ""))
    if cmd_id:
        return ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cmd_id[0], owner)
    resposta_tempo = _resposta_temporal_direta(
        prep.get("user_text", ""), prep.get("contexto_local", {}))
    if resposta_tempo:
        return ai_resposta_direta(
            db, mid, conv, modelo, prep["reply_id"], resposta_tempo, owner)
    ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
    cfg_eff = dict(cfg, memoria_global=prep.get("memoria_global", cfg.get("memoria_global", True)))
    messages, extras = ai_montar_mensagens(
        db, conv, cfg_eff, prep.get("user_text", ""), owner,
        prep.get("contexto_local"))
    # V5.7: o fallback sem streaming também executa a busca de produtos
    # (antes respondia de memória com preços/produtos inventados).
    shop_res = _shopping_executar(db, owner, conv, prep.get("user_text", ""),
                                  extras, messages)
    without_evidence=_shopping_resposta_factual(shop_res,prep.get('user_text','')) or _shopping_sem_ofertas(shop_res) or _pesquisa_sem_evidencia(extras,shop_res,prep.get('user_text',''))
    if without_evidence:
        return {**ai_resposta_direta(db,mid,conv,modelo,prep['reply_id'],without_evidence,owner),'digest':True}
    try:
        res = gerar_texto(cfg, messages, preferido=modelo)
    except hermes_bridge.BridgeErro as exc:
        extras["inference_error_code"] = exc.codigo
        texto_fb = _fallback_sem_inferencia(
            prep.get("user_text", ""), extras, shop_res)
        if texto_fb:
            texto_fb, _b, _e = jdui.normalizar(texto_fb)
            texto_fb = _validar_resposta(
                extras.get("intent") or {}, texto_fb,
                usadas=extras.get("ferramentas_usadas", []),
                produtos=(shop_res or {}).get("produtos", []), mid=mid)
            ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"],
                                texto_fb, owner)
            log.info("IA sem inferência: fallback determinístico (%s, ofertas=%s)",
                     mid, bool((shop_res or {}).get("produtos")))
            return {"reply_id": prep["reply_id"], "response_text": texto_fb,
                    "model": modelo, "digest": True,
                    "shopping": bool((shop_res or {}).get("produtos"))}
        ai_marcar(db, mid, conv, modelo, "failed", error=str(exc), owner=owner)
        return {"error": str(exc), "codigo": exc.codigo}
    modelo = res.get("model_usado", modelo)
    texto = _texto_seguro(res["texto"], mid)
    texto = anexar_fontes(texto, extras["fontes"], intencao_imagem(prep.get("user_text", "")), extras.get('midia'), extras.get('pesquisa_executada',False), consulta=prep.get('user_text',''))
    if prep.get("pergunta_memoria") and prep["pergunta_memoria"] not in (texto or ""):
        texto = (texto or "") + "\n\n" + prep["pergunta_memoria"]
    # V5.7: cards reais (ou nota honesta) + banimento de fence de produto do modelo.
    texto = _shopping_aplicar(texto, shop_res, extras)
    # V5.7.3: comparação sem evidência não vira fato (com laudo por afirmação).
    texto, extras["afirmacoes"] = _validar_comparacoes(
        texto, extras.get("fontes"), (shop_res or {}).get("produtos"), mid=mid)
    texto = _aplicar_arquivos_gerados(db, conv, owner, texto, extras)
    texto, blocos_jdui, erros_jdui = jdui.normalizar(texto)
    if erros_jdui:
        log.warning("JDUI descartado na msg %s: %s", mid, "; ".join(erros_jdui[:3]))
    if not blocos_jdui and intencao_transformar_pesquisa(prep.get("user_text", "")):
        fence = fence_transformacao_visual(db, owner, conv, prep.get("user_text", ""))
        if fence:
            texto += fence
            log.info("transform visual sintetizado para %s", mid)
    elif "mostre as evid" in (prep.get("user_text", "") or "").lower() or \
            "mostra as evid" in (prep.get("user_text", "") or "").lower():
        fence = fence_de_evidencias(db, owner, conv)
        if fence:
            texto += fence
            log.info("evidências sintetizadas para %s", mid)
    elif "mostre as fontes" in (prep.get("user_text", "") or "").lower() or \
            "mostra as fontes" in (prep.get("user_text", "") or "").lower() or \
            "quais as fontes" in (prep.get("user_text", "") or "").lower():
        fence = '' if extras.get('pesquisa_executada') else fence_de_fontes(db, owner, conv=conv)
        if fence:
            texto += fence
            log.info("fontes sintetizadas para %s", mid)
    elif "grafo de evid" in (prep.get("user_text", "") or "").lower() or \
            "mapa de evid" in (prep.get("user_text", "") or "").lower():
        fence = fence_de_grafo(db, owner)
        if fence:
            texto += fence
            log.info("grafo de evidências sintetizado para %s", mid)
    elif not blocos_jdui and intencao_reforco(prep.get("user_text", "")):
        fence = sintetizar_reforco(db, owner, prep.get("user_text", ""))
        if fence:
            texto += fence
            log.info("reforço sintetizado para %s", mid)
    elif not blocos_jdui and intencao_aula(prep.get("user_text", "")):
        fence = sintetizar_aula(db, cfg_eff, owner, prep.get("user_text", ""))
        if fence:
            texto += fence
            log.info("aula sintetizada para %s", mid)
    elif not blocos_jdui and intencao_grafico_evolucao(prep.get("user_text", "")):
        fence = sintetizar_grafico_evolucao(db, owner)
        if fence:
            texto += fence
            log.info("gráfico de evolução sintetizado para %s", mid)
    elif not blocos_jdui and intencao_prova(prep.get("user_text", "")):
        fence = sintetizar_prova(db, cfg_eff, owner, prep.get("user_text", ""))
        if fence:
            texto += fence
            log.info("prova sintetizada para %s", mid)
    if not blocos_jdui and "```jdui" not in texto and extras.get("comp_sugerido") in JDUI_SINTETIZAR:
        fence = sintetizar_jdui(cfg_eff, extras["comp_sugerido"], prep.get("user_text", ""), texto)
        if fence:
            texto += fence
            log.info("JDUI sintetizado para %s (%s)", mid, extras["comp_sugerido"])
    # V5.1/V5.7: validador determinístico + nota honesta no próprio texto.
    texto = _validar_resposta(
        extras.get("intent") or {}, texto,
        usadas=extras.get("ferramentas_usadas", []),
        produtos=(shop_res or {}).get("produtos", []), mid=mid)
    ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], texto, owner)
    if len(prep.get("user_text", "")) >= 20:
        threading.Thread(target=aprender_com_conversa,
                         args=(database_path(), dict(cfg), prep["user_text"], texto, owner),
                         daemon=True).start()
    log.info("IA %s respondeu em %ss (msg %s, memoria=%s, fontes=%d)", modelo, res["latencia_s"], mid,
             extras["memoria_usada"], len(extras["fontes"]))
    return {"reply_id": prep["reply_id"], "response_text": texto,
            "model": modelo, "truncada": res.get("truncada", False)}


# TODOS os envios no WebSocket passam por este lock global. O cliente
# websockets síncrono NÃO é thread-safe: streams paralelas + loop principal
# enviando juntos corrompem frames e derrubam a conexão (1006).
ENVIO_LOCK = threading.Lock()


def enviar_ws(websocket, obj) -> None:
    """Envio serializado (único ponto de escrita no socket)."""
    with ENVIO_LOCK:
        websocket.send(json.dumps(obj, ensure_ascii=False))


class SessaoStream:
    def __init__(self):
        self.parar = threading.Event()
        self.lock_envio = ENVIO_LOCK  # compat: aponta para o lock global


def ai_stream_worker(db_path: Path, cfg: dict, payload: dict, request_id: str,
                     websocket, sessao: SessaoStream, cancelados: dict) -> None:
    """Roda em thread: deltas saem pelo lock; a thread principal só recebe."""
    worker_started = time.monotonic()
    db = open_db(db_path)
    claimed = False
    try:
        prep_started = time.monotonic()
        prep = ai_preparar(db, payload, cfg)
        prep_finished = time.monotonic()
        if "error" in prep or "replay" in prep or "busy" in prep:
            try:
                enviar_ws(websocket, {"request_id": request_id,
                                      "type": "ai_done" if prep.get("replay") else "ai_error",
                                      **({"codigo": "ocupado", "error": "Resposta em andamento. Aguarde a sincronização."}
                                         if prep.get("busy") else {}),
                                      **{k: prep[k] for k in ("error", "codigo", "reply_id",
                                                              "response_text", "model", "busy")
                                          if k in prep}})
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        mid, conv, modelo = payload["message_id"], prep["conversation_id"], prep["model"]
        owner = prep.get("owner", DONO_PADRAO)
        claimed = True
        atual = cmd_dados_atuais(db, prep.get('user_text',''), owner, conv, prep.get('contexto_local',{}), payload.get('message_id'))
        if atual:
            if sessao.parar.is_set():
                ai_marcar(db, mid, conv, modelo, 'cancelled', reply_id=prep['reply_id'], response_text='', owner=owner)
                enviar_ws(websocket, {'request_id':request_id,'type':'ai_cancelled','reply_id':prep['reply_id'],'partial':''})
                return
            direct = ai_resposta_direta(db, mid, conv, modelo, prep['reply_id'], atual, owner)
            enviar_ws(websocket, {'request_id':request_id,'type':'ai_done',**direct})
            return
        model_response = cmd_model3d(db, prep.get("user_text", ""), owner, conv, payload.get('scene_state',''),
                                     pesquisa_web=bool(cfg.get("pesquisa_web", True)))
        if model_response:
            direct = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], model_response, owner)
            enviar_ws(websocket, {"request_id": request_id, "type": "ai_done", **direct})
            return
        cmd = interpretar_comando_memoria(db, prep.get("user_text", ""), owner)
        if cmd:
            direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cmd[0], owner)
            try:
                enviar_ws(websocket, {"request_id": request_id, "type": "ai_done",
                                      "reply_id": direta["reply_id"],
                                      "response_text": direta["response_text"],
                                      "model": modelo})
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        rp = cmd_pesquisa(db, prep.get("user_text", ""), owner, conv,
                         model=payload.get('model') or ('' if cfg.get('model_implicit') else modelo))
        if rp:
            direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], rp, owner)
            try:
                enviar_ws(websocket, {"request_id": request_id, "type": "ai_done",
                                      "reply_id": direta["reply_id"],
                                      "response_text": direta["response_text"],
                                      "model": modelo})
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        # V5.0: continuidade de projetos/tarefas (determinístico, sem LLM).
        cp = cmd_projeto(db, prep.get("user_text", ""), owner, conv)
        if cp:
            direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"], cp, owner)
            try:
                enviar_ws(websocket, {"request_id": request_id, "type": "ai_done",
                                      "reply_id": direta["reply_id"],
                                      "response_text": direta["response_text"],
                                      "model": modelo})
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        # V4.9.1: follow-ups de shopping (inclui "tem fotos?") reusam a
        # última consulta — sem LLM/rede; as imagens vêm dos cards verificados.
        if shopping.eh_followup(prep.get("user_text", "")) or \
                shopping.quer_fotos(prep.get("user_text", "")):
            fup = shopping.responder_followup(db, owner, conv, prep.get("user_text", ""))
            if fup:
                # Imagens primeiro: os cards visuais abrem; o texto vem abaixo.
                texto_fup = imagens_primeiro(fup.get("fence"), fup["texto"])
                direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"],
                                            texto_fup, owner)
                try:
                    enviar_ws(websocket, {"request_id": request_id, "type": "ai_done",
                                          "reply_id": direta["reply_id"],
                                          "response_text": direta["response_text"],
                                          "model": modelo})
                except (ConnectionClosed, OSError, RuntimeError, ValueError):
                    pass
                return
            if shopping.followup_sem_contexto(prep.get("user_text", "")):
                direta = ai_resposta_direta(
                    db, mid, conv, modelo, prep["reply_id"],
                    _texto_followup_sem_contexto(prep.get("user_text", "")), owner)
                try:
                    enviar_ws(websocket, {"request_id": request_id, "type": "ai_done",
                                          "reply_id": direta["reply_id"],
                                          "response_text": direta["response_text"],
                                          "model": modelo})
                except (ConnectionClosed, OSError, RuntimeError, ValueError):
                    pass
                return
        # V5.0: identidade determinística (nome/correção; funciona sem LLM).
        cmd_id = cmd_identidade(prep.get("user_text", ""))
        if cmd_id:
            direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"],
                                        cmd_id[0], owner)
            try:
                enviar_ws(websocket, {"request_id": request_id, "type": "ai_done",
                                      "reply_id": direta["reply_id"],
                                      "response_text": direta["response_text"],
                                      "model": modelo})
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        resposta_tempo = _resposta_temporal_direta(
            prep.get("user_text", ""), prep.get("contexto_local", {}))
        if resposta_tempo:
            direta = ai_resposta_direta(db, mid, conv, modelo, prep["reply_id"],
                                        resposta_tempo, owner)
            try:
                enviar_ws(websocket, {"request_id": request_id, "type": "ai_done",
                                      "reply_id": direta["reply_id"],
                                      "response_text": direta["response_text"],
                                      "model": modelo})
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            return
        ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
        cfg_eff = dict(cfg, memoria_global=prep.get("memoria_global", cfg.get("memoria_global", True)))
        context_started = time.monotonic()
        messages, extras = ai_montar_mensagens(
            db, conv, cfg_eff, prep.get("user_text", ""), owner,
            prep.get("contexto_local"))
        context_finished = time.monotonic()

        def enviar(obj):
            try:
                enviar_ws(websocket, obj)
            except (ConnectionClosed, OSError, RuntimeError, ValueError) as exc:
                raise hermes_bridge.BridgeErro(
                    "Conexão com o relay caiu no meio da resposta.", "desconectado") from exc

        first_delta_at = [0.0]
        last_delta_seq = [0]
        partial_chunks = []
        partial_saved_at = [0.0]

        def emitir(seq, trecho):
            last_delta_seq[0] = seq
            partial_chunks.append(trecho)
            if time.monotonic() - partial_saved_at[0] >= 1.0:
                ai_marcar(db, mid, conv, modelo, "processing", reply_id=prep["reply_id"],
                          response_text="".join(partial_chunks), owner=owner)
                partial_saved_at[0] = time.monotonic()
            if not first_delta_at[0]:
                first_delta_at[0] = time.monotonic()
                log.info(
                    "AI_AGENT_TTFT msg=%s prep_ms=%d context_ms=%d first_delta_ms=%d",
                    mid[-8:], round((prep_finished - prep_started) * 1000),
                    round((context_finished - context_started) * 1000),
                    round((first_delta_at[0] - worker_started) * 1000))
            enviar({"request_id": request_id, "type": "ai_delta",
                    "seq": seq, "trecho": trecho})

        # Síntese de prova/aula roda EM PARALELO com o stream (usa só o pedido;
        # o resultado é coletado no fim). Ganho: total ≈ max(stream, síntese).
        fut_sintese, quer_aula = None, False
        _tu = prep.get("user_text", "")
        if intencao_prova(_tu) and not intencao_reforco(_tu) and not intencao_aula(_tu) \
                and not intencao_grafico_evolucao(_tu) and not intencao_transformar_pesquisa(_tu):
            fut_sintese = _SINT_POOL.submit(_sintetizar_isolado, sintetizar_prova,
                                            owner, cfg_eff, owner, _tu)
        elif intencao_aula(_tu) and not intencao_reforco(_tu):
            quer_aula = True
            fut_sintese = _SINT_POOL.submit(_sintetizar_isolado, sintetizar_aula,
                                            owner, cfg_eff, owner, _tu)
        provider_started = time.monotonic()
        # V4.9.1 Shopping Intelligence: busca real ANTES do LLM (operações
        # reais emitidas como progresso; cards determinísticos no fim).
        shop_res = None
        if extras.get("shop"):
            if sessao.parar.is_set():
                ai_marcar(db, mid, conv, modelo, "cancelled",
                          reply_id=prep["reply_id"], response_text="", owner=owner)
                try:
                    enviar({"request_id": request_id, "type": "ai_cancelled",
                            "reply_id": prep["reply_id"], "partial": ""})
                except hermes_bridge.BridgeErro:
                    pass
                return

            def _prog_shop(fase, detalhe=""):
                try:
                    emitir(last_delta_seq[0] + 1, f"🔎 {fase}… {detalhe}\n".strip() + "\n")
                except Exception:
                    pass

            shop_res = _shopping_executar(db, owner, conv,
                                          prep.get("user_text", ""), extras,
                                          messages, progresso=_prog_shop)
        without_evidence=_shopping_resposta_factual(shop_res,prep.get('user_text','')) or _shopping_sem_ofertas(shop_res) or _pesquisa_sem_evidencia(extras,shop_res,prep.get('user_text',''))
        if without_evidence:
            if sessao.parar.is_set():
                partial=''.join(partial_chunks)
                ai_marcar(db,mid,conv,modelo,'cancelled',reply_id=prep['reply_id'],response_text=partial,owner=owner)
                enviar({'request_id':request_id,'type':'ai_cancelled','reply_id':prep['reply_id'],'partial':partial})
                return
            direct=ai_resposta_direta(db,mid,conv,modelo,prep['reply_id'],without_evidence,owner)
            enviar({'request_id':request_id,'type':'ai_done',**direct,'digest':True})
            return
        guarda_stream = _GuardaStreamResposta(
            extras.get("fontes"), (shop_res or {}).get("produtos"), mid)

        def emitir_modelo(_seq, trecho):
            for seguro in guarda_stream.alimentar(trecho):
                emitir(last_delta_seq[0] + 1, seguro)

        try:
            res = gerar_stream(cfg, modelos_tentativa(cfg, modelo), messages,
                               emitir_modelo, deve_parar=sessao.parar.is_set,
                               max_tokens=cfg["max_tokens"])
            modelo = res.get("model_usado", modelo)
            for seguro in guarda_stream.finalizar():
                emitir(last_delta_seq[0] + 1, seguro)
        except hermes_bridge.BridgeErro as exc:
            # O que estava retido por segurança também precisa ser liberado
            # (já sanitizado) antes de qualquer fallback/erro.
            try:
                for seguro in guarda_stream.finalizar():
                    emitir(last_delta_seq[0] + 1, seguro)
            except hermes_bridge.BridgeErro:
                pass
            log.warning(
                "AI_AGENT_ERROR msg=%s prep_ms=%d context_ms=%d provider_ms=%d "
                "first_delta_ms=%d code=%s",
                mid[-8:], round((prep_finished - prep_started) * 1000),
                round((context_finished - context_started) * 1000),
                round((time.monotonic() - provider_started) * 1000),
                round((first_delta_at[0] - provider_started) * 1000)
                if first_delta_at[0] else -1, exc.codigo)
            if fut_sintese is not None:
                fut_sintese.cancel()
            # V5.0.1/V5.7.3: sem inferência, fontes reais (digest) e/ou
            # ofertas verificadas continuam disponíveis em vez de erro vazio.
            extras["inference_error_code"] = exc.codigo
            texto_fb = _fallback_sem_inferencia(
                prep.get("user_text", ""), extras, shop_res)
            if texto_fb:
                texto_fb, _b, _e = jdui.normalizar(texto_fb)
                texto_fb = _validar_resposta(
                    extras.get("intent") or {}, texto_fb,
                    usadas=extras.get("ferramentas_usadas", []),
                    produtos=(shop_res or {}).get("produtos", []), mid=mid)
                ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"],
                                    texto_fb, owner)
                ja_enviado = "".join(partial_chunks)
                complemento = texto_fb
                if ja_enviado and texto_fb.startswith(ja_enviado):
                    complemento = texto_fb[len(ja_enviado):]
                try:
                    if complemento:
                        emitir(last_delta_seq[0] + 1, complemento)
                    enviar({"request_id": request_id, "type": "ai_done",
                            "reply_id": prep["reply_id"],
                            "response_text": texto_fb, "model": modelo,
                            "digest": True})
                except hermes_bridge.BridgeErro:
                    pass
                return
            ai_marcar(db, mid, conv, modelo, "failed", error=str(exc), owner=owner,
                      reply_id=prep["reply_id"], response_text="".join(partial_chunks))
            try:
                enviar({"request_id": request_id, "type": "ai_error",
                        "error": str(exc), "codigo": exc.codigo})
            except hermes_bridge.BridgeErro:
                pass  # relay fora do ar: celular verá timeout + retry
            return
        if res.get("cancelada"):
            if fut_sintese is not None:
                fut_sintese.cancel()
            ai_marcar(db, mid, conv, modelo, "cancelled",
                      reply_id=prep["reply_id"], response_text=res["texto"], owner=owner)
            try:
                enviar({"request_id": request_id, "type": "ai_cancelled",
                        "reply_id": prep["reply_id"], "partial": res["texto"]})
            except hermes_bridge.BridgeErro:
                pass
            return
        resposta_modelo = _texto_seguro(res["texto"], mid)
        texto_final = anexar_fontes(resposta_modelo, extras["fontes"], intencao_imagem(prep.get("user_text", "")), extras.get('midia'), extras.get('pesquisa_executada',False), consulta=prep.get('user_text',''))
        if prep.get("pergunta_memoria") and prep["pergunta_memoria"] not in (texto_final or ""):
            texto_final = (texto_final or "") + "\n\n" + prep["pergunta_memoria"]
        texto_final = _shopping_aplicar(texto_final, shop_res, extras)
        texto_final, extras["afirmacoes"] = _validar_comparacoes(
            texto_final, extras.get("fontes"),
            (shop_res or {}).get("produtos"), mid=mid)
        texto_final = _aplicar_arquivos_gerados(db, conv, owner, texto_final, extras)
        texto_final, blocos_jdui, erros_jdui = jdui.normalizar(texto_final)
        if erros_jdui:
            log.warning("JDUI descartado no stream %s: %s", mid, "; ".join(erros_jdui[:3]))
        if blocos_jdui and fut_sintese is not None:
            fut_sintese.cancel()  # modelo já entregou interface: dispensa a síntese
        if not blocos_jdui and intencao_transformar_pesquisa(prep.get("user_text", "")):
            fence = fence_transformacao_visual(db, owner, conv, prep.get("user_text", ""))
            if fence:
                texto_final += fence
                log.info("transform visual sintetizado no stream %s", mid)
        elif "mostre as fontes" in (prep.get("user_text", "") or "").lower() or \
                "mostra as fontes" in (prep.get("user_text", "") or "").lower() or \
                "quais as fontes" in (prep.get("user_text", "") or "").lower():
            fence = '' if extras.get('pesquisa_executada') else fence_de_fontes(db, owner, conv=conv)
            if fence:
                texto_final += fence
                log.info("fontes sintetizadas no stream %s", mid)
        elif not blocos_jdui and intencao_reforco(prep.get("user_text", "")):
            fence = sintetizar_reforco(db, owner, prep.get("user_text", ""))
            if fence:
                texto_final += fence
                log.info("reforço sintetizado no stream %s", mid)
        elif not blocos_jdui and intencao_aula(prep.get("user_text", "")):
            fence = ""
            if fut_sintese is not None and quer_aula:
                try:
                    fence = fut_sintese.result(timeout=120) or ""
                except Exception:
                    fence = ""
            if not fence:
                fence = sintetizar_aula(db, cfg_eff, owner, prep.get("user_text", ""))
            if fence:
                texto_final += fence
                log.info("aula sintetizada no stream %s", mid)
        elif not blocos_jdui and intencao_grafico_evolucao(prep.get("user_text", "")):
            fence = sintetizar_grafico_evolucao(db, owner)
            if fence:
                texto_final += fence
                log.info("gráfico de evolução sintetizado no stream %s", mid)
        elif not blocos_jdui and intencao_prova(prep.get("user_text", "")):
            fence = ""
            if fut_sintese is not None and not quer_aula:
                try:
                    fence = fut_sintese.result(timeout=120) or ""
                except Exception:
                    fence = ""
            if not fence:
                fence = sintetizar_prova(db, cfg_eff, owner, prep.get("user_text", ""))
            if fence:
                texto_final += fence
                log.info("prova sintetizada no stream %s", mid)
        if not blocos_jdui and "```jdui" not in texto_final and extras.get("comp_sugerido") in JDUI_SINTETIZAR:
            fence = sintetizar_jdui(cfg_eff, extras["comp_sugerido"], prep.get("user_text", ""), texto_final)
            if fence:
                texto_final += fence  # o tail-emit abaixo entrega como deltas finais
                log.info("JDUI sintetizado no stream %s (%s)", mid, extras["comp_sugerido"])
        # V5.1/V5.7: validador de relevância (determinístico; sem regeneração)
        # ANTES do tail-emit — a nota honesta precisa entrar no stream.
        texto_final = _validar_resposta(
            extras.get("intent") or {}, texto_final,
            usadas=extras.get("ferramentas_usadas", []),
            produtos=(shop_res or {}).get("produtos", []), mid=mid)
        complemento = _complemento_stream(texto_final, guarda_stream.texto_emitido)
        if complemento:
            # envia fontes/imagem/correção como deltas finais para TTFT não
            # degradar; o que já saiu sanitizado não é repetido.
            try:
                emitir(last_delta_seq[0] + 1, complemento)
            except Exception:
                pass
        ai_guardar_resposta(db, mid, conv, modelo, prep["reply_id"], texto_final, owner)
        if len(prep.get("user_text", "")) >= 20:
            threading.Thread(target=aprender_com_conversa,
                             args=(db_path, dict(cfg_eff), prep["user_text"], texto_final, owner),
                             daemon=True).start()
        log.info(
            "AI_AGENT_DONE msg=%s model=%s prep_ms=%d context_ms=%d provider_ms=%d "
            "first_delta_ms=%d total_ms=%d sources=%d",
            mid[-8:], modelo, round((prep_finished - prep_started) * 1000),
            round((context_finished - context_started) * 1000),
            round((time.monotonic() - provider_started) * 1000),
            round((first_delta_at[0] - provider_started) * 1000) if first_delta_at[0] else -1,
            round((time.monotonic() - worker_started) * 1000), len(extras["fontes"]))
        enviar({"request_id": request_id, "type": "ai_done",
                "reply_id": prep["reply_id"],
                "response_text": texto_final, "model": modelo})
    except Exception:
        log.exception("Falha inesperada no stream %s", request_id)
        if claimed:
            state = ai_estado(db, mid, owner)
            if state and state["state"] != "completed":
                ai_marcar(db, mid, conv, modelo, "failed", owner=owner,
                          reply_id=prep["reply_id"], response_text=state.get("response_text") or "",
                          error="Geração interrompida. Tente novamente.")
        try:
            enviar_ws(websocket, {"request_id": request_id, "type": "ai_error",
                                  "codigo": "interno", "error": "Geração interrompida. Tente novamente."})
        except (ConnectionClosed, OSError, RuntimeError, ValueError):
            pass
    finally:
        cancelados.pop(request_id, None)
        db.close()
