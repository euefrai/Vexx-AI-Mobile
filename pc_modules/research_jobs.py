"""Módulo do PC Agent: Jobs de pesquisa profunda em background, tailer de eventos, persistência e recuperação."""
import hermes_bridge
import jdui
import json
import os
import re
import research_agents
import threading
import workspace_store

from assistant_identity import system_with_identity
from pathlib import Path

from pc_modules.db_core import agora_iso, ai_config, database_path, gerar_texto, open_db
from pc_modules.ai_pipeline import enviar_ws

# ── Research jobs em background (V4.5 FASE 8: live telemetry real) ───
JOBS_BG: dict = {}
JOBS_BG_LOCK = threading.Lock()
MAX_JOBS_SIMULTANEOS = 2


def _db_job(path):
    return open_db(Path(path))


def iniciar_job_bg(db_path, job_id: str, owner: str, websocket=None) -> bool:
    """Dispara worker em thread (1 por dono, teto global anti-monopólio)."""
    with JOBS_BG_LOCK:
        if any(v.get("owner") == owner for v in JOBS_BG.values()):
            return False
        if len(JOBS_BG) >= MAX_JOBS_SIMULTANEOS:
            return False
        parar = threading.Event()
        pronto = threading.Event()
        cfg = ai_config()
        config_db = open_db(Path(db_path))
        try:
            saved = research_agents.carregar_job(config_db, owner, job_id)
        finally:
            config_db.close()
        chosen = (saved.get("ajustes") or {}).get("model", "")
        if chosen:
            cfg = dict(cfg, model=chosen, model_implicit=False, fallbacks=[])
        t = threading.Thread(target=_job_worker,
                             args=(str(db_path), job_id, owner, cfg, parar, pronto,
                                   websocket),
                             daemon=True)
        JOBS_BG[job_id] = {"owner": owner, "parar": parar, "pronto": pronto, "thread": t}
        t.start()
        return True


def _job_tailer(db_path: str, job_id: str, owner: str, websocket, parar, pronto) -> None:
    """Encaminha eventos novos ao relay (push real; polling continua valendo)."""
    import sqlite3 as _sq
    ultimo = 0
    try:
        db = _sq.connect(db_path)
        while not parar.is_set():
            try:
                rows = db.execute("SELECT seq, ts, agente, tipo, status, descricao, meta"
                                  " FROM research_events WHERE job_id=? AND owner_id=?"
                                  " AND seq>? ORDER BY seq LIMIT 50",
                                  (job_id, owner, ultimo)).fetchall()
            except Exception:
                break
            for seq, ts, agente, tipo, status, descricao, meta in rows:
                ultimo = max(ultimo, seq)
                try:
                    enviar_ws(websocket, {"type": "research_event_push", "job_id": job_id,
                                          "owner": owner,
                                          "event": {"seq": seq, "ts": ts, "agente": agente,
                                                    "tipo": tipo, "status": status,
                                                    "descricao": descricao,
                                                    "meta": __import__("json").loads(meta or "{}")}})
                except Exception:
                    return  # relay caiu: polling cobre
            try:
                row = db.execute("SELECT status FROM research_jobs WHERE id=? AND owner_id=?",
                                 (job_id, owner)).fetchone()
            except Exception:
                break
            # Interrupted/paused workers have also stopped. A later resume
            # creates its own tailer; retaining this one blocks runtime drain.
            if row and row[0] in ("concluida", "cancelada", "falhou", "interrompida", "pausada"):
                break
            parar.wait(1.0)
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _research_writer(cfg: dict, parar):
    """One configured model/request per phase; no tools or chat/memory prompt."""
    import research_synthesis
    def write(messages, timeout):
        if parar.is_set():
            return ''
        bounded = dict(cfg, fallbacks=[])
        import research_output
        schema = research_output.response_format(messages)
        if schema:bounded['_research_response_format'] = schema
        messages = [dict(m) for m in messages]
        messages[0]['content'] = system_with_identity(messages[0]['content'])
        try:
            result = gerar_texto(bounded, messages, max_tokens=1800, timeout=min(25, timeout))
        except hermes_bridge.BridgeErro as exc:
            write.last_metadata=getattr(exc,'response_metadata',{})
            if write.last_metadata.get('finish_reason')=='length':
                raise research_synthesis.ModelOutputError('model_truncated') from exc
            if write.last_metadata.get('finish_reason')=='content_filter':
                raise research_synthesis.ModelOutputError('model_filtered') from exc
            raise
        write.last_metadata = {k:result[k] for k in ('finish_reason','usage','truncada','latencia_s','structured_output_requested','structured_output_fallback') if k in result}
        if result.get('truncada') or result.get('finish_reason') == 'length':
            raise research_synthesis.ModelOutputError('model_truncated')
        if result.get('finish_reason') == 'content_filter':
            raise research_synthesis.ModelOutputError('model_filtered')
        return '' if parar.is_set() else result.get('texto', '')
    write.last_metadata = {}
    write.literal_quote_ids = True
    write.semantic_coverage = True
    return write


def _job_worker(db_path: str, job_id: str, owner: str, cfg: dict, parar, pronto,
                websocket=None) -> None:
    db = open_db(Path(db_path))
    cauda = None
    try:
        db.execute("UPDATE research_jobs SET status='em_andamento' WHERE id=? AND owner_id=?",
                   (job_id, owner))
        db.commit()
        if websocket is not None:
            cauda = threading.Thread(target=_job_tailer,
                                     args=(db_path, job_id, owner, websocket, parar, pronto),
                                     daemon=True)
            cauda.start()
        research_agents.executar(db, job_id, owner,
                                 research_agents.provedores_reais(
                                     orquestrado=bool(cfg.get("pesquisa_web", True))),
                                 research_agents.recuperar_real(),
                                 deve_parar=parar.is_set,
                                 sintetizar_fn=(_research_writer(cfg, parar) if
                                     os.getenv('VEXX_RESEARCH_SYNTHESIS', '1') != '0' else None))
        _persistir_resultado_pesquisa(db, research_agents.carregar_job(db, owner, job_id), owner)
    except Exception as exc:
        try:
            job = research_agents.carregar_job(db, owner, job_id)
            job["status"] = "falhou"
            job["erros"].append(f"worker: {type(exc).__name__}"[:200])
            research_agents.salvar_job(db, job)
            if job["status"] not in ("cancelada", "pausada"):
                research_agents.emitir(db, job_id, owner, "orchestrator", "research_failed",
                                       "falha", f"Worker falhou ({type(exc).__name__}).", {})
        except Exception:
            pass
    finally:
        with JOBS_BG_LOCK:
            JOBS_BG.pop(job_id, None)
        try:
            db.close()
        except Exception:
            pass


def rjob_start(db, req: dict, dono: str, websocket=None) -> dict:
    """Cria job + plano + dispara worker. 1 ativa por dono (409 honesto)."""
    if research_agents.job_ativo(db, dono) or \
            any(v.get("owner") == dono for v in JOBS_BG.values()):
        return {"type": "learn_error", "error": "Já há pesquisa em andamento.",
                "codigo": "ocupado"}
    chosen = req.get("model") or ""
    if not isinstance(chosen, str) or (chosen and not re.fullmatch(r"[A-Za-z0-9_~.][A-Za-z0-9_~.:/-]{0,119}", chosen)):
        return {"type": "learn_error", "codigo": "invalido", "error": "Modelo inválido."}
    try:
        job = research_agents.criar_job(db, dono, str(req.get("objetivo", ""))[:500],
                                        str(req.get("conv", ""))[:100],
                                        manual=str(req.get("modo", ""))[:20])
        research_agents.montar_plano(db, job)
        if chosen:
            job.setdefault("ajustes", {})["model"] = chosen
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}
    job["status"] = "em_andamento"
    research_agents.salvar_job(db, job)
    if not iniciar_job_bg(database_path(), job["id"], dono, websocket):
        job["status"] = "criada"
        research_agents.salvar_job(db, job)
        return {"type": "learn_error", "error": "Já há pesquisa em andamento.",
                "codigo": "ocupado"}
    return {"type": "research_job", "job_id": job["id"], "modo": job["modo"],
            "etapas": len(job["plano"])}


def _persistir_resultado_pesquisa(db, job, owner):
    """Deliver a terminal research view once; never turn a cancelled job into chat."""
    partial = (job.get('status')=='interrompida' and job.get('usados',{}).get('partial_delivery_ready')
               and job.get('usados',{}).get('research_outcome',{}).get('state') in ('blocked','partial'))
    if job.get('owner')!=owner or (job.get('status')!='concluida' and not partial) or not job.get('conv'):
        return ''
    reply_id=job['id']+'-result'
    if workspace_store.chat_deleted(db, owner, job['conv']):
        return ''
    import research_view
    summary=research_agents._resumo(db,job)
    evidence=research_agents.listar_evidencias(db,owner,job['id'])
    view=research_view.build_view(summary,evidence)
    media_intent = bool(re.search(r'\b(imagens?|fotos?|v[ií]deos?)\b',job.get('objetivo',''),re.I))
    blocks=research_view.chat_blocks(view, media_intent)
    while blocks:
        message={'version':jdui.VERSION,'blocks':blocks}
        valid,normalized,_=jdui.validar_mensagem(message)
        if not valid:return ''
        text='Resultado da pesquisa\n\n```jdui\n'+json.dumps(normalized,ensure_ascii=False)+'\n```'
        if len(text)<=10000:break
        # Full evidence remains in the job; never truncate a JSON fence or facts.
        removable=next((i for i in range(len(blocks)-1,-1,-1) if blocks[i].get('type')=='ui'),None)
        if removable is None:return ''
        blocks.pop(removable)
    if not blocks:return ''
    with db:
        if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
        if workspace_store.chat_deleted(db,owner,job['conv']):return ''
        db.execute("""INSERT OR IGNORE INTO messages
            (id,conversation_id,origin,role,text,created_at,received_at,model,owner_id)
            VALUES (?,?,'mobile','assistant',?,?,?,?,?)""",
            (reply_id,job['conv'],text,agora_iso(),agora_iso(),'Pesquisa',owner))
        # Explicit resume can improve a partial result, keeping one message ID.
        db.execute("UPDATE messages SET text=?,received_at=? WHERE id=? AND owner_id=? "
                   "AND origin='mobile' AND role='assistant' AND text<>?",
                   (text,agora_iso(),reply_id,owner,text))
    import retrieval_trace
    retrieval_trace.record(job['id'],'',{},'JDUI_DELIVERED',reason_code='SQLITE_PERSISTED_FOR_SYNC')
    return reply_id


def rjob_status(db, req: dict, dono: str) -> dict:
    try:
        job = research_agents.carregar_job(db, dono, str(req.get("job_id", ""))[:64])
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}
    try:
        apos = int(req.get("apos_seq", 0) or 0)
    except (TypeError, ValueError):
        apos = 0
    evs = research_agents.eventos_desde(db, dono, job["id"], apos)
    with JOBS_BG_LOCK:
        viva = job["id"] in JOBS_BG
    resumo = research_agents._resumo(db, job)
    resumo['chat_result_id']=_persistir_resultado_pesquisa(db,job,dono)
    resumo["viva"] = viva
    return {"type": "research_status", "resumo": resumo, "eventos": evs}


def rjob_cancel(db, req: dict, dono: str) -> dict:
    try:
        job = research_agents.carregar_job(db, dono, str(req.get("job_id", ""))[:64])
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}
    with JOBS_BG_LOCK:
        slot = JOBS_BG.get(job["id"])
        if slot is not None:
            slot["parar"].set()
    return {"type": "research_cancelled",
            **research_agents.cancelar(db, dono, job["id"])}


def rjob_list(db, dono: str) -> dict:
    return {"type": "research_jobs", "jobs": research_agents.listar_jobs(db, dono)}


def rjob_intervene(db, req: dict, dono: str) -> dict:
    try:
        out = research_agents.intervir(db, dono, str(req.get("job_id", ""))[:64],
                                       str(req.get("op", ""))[:30],
                                       req.get("params", {}) if isinstance(req.get("params"), dict) else {})
        return {"type": "research_intervened", **out}
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}


def rjob_pause(db, req: dict, dono: str) -> dict:
    try:
        pausar = str(req.get("pausar", "1")).lower() not in ("0", "false", "nao", "não")
        return {"type": "research_paused",
                **research_agents.pausar(db, dono, str(req.get("job_id", ""))[:64], pausar)}
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}


def rjob_evidence(db, req: dict, dono: str) -> dict:
    try:
        job = research_agents.carregar_job(db, dono, str(req.get("job_id", ""))[:64])
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}
    evs = research_agents.listar_evidencias(db, dono, job["id"])
    return {"type": "research_evidence",
            "evidencias": [{k: e[k] for k in ("id", "titulo", "url", "dominio", "status")}
                           for e in evs][:100]}


def rjob_report(db, req: dict, dono: str) -> dict:
    try:
        report = research_agents.gerar_relatorio(
            db, dono, str(req.get("job_id", ""))[:64],
            str(req.get("report_type", "executive_summary"))[:40],
        )
        return {"type": "research_report", **report}
    except (research_agents.AgentErro, ValueError) as exc:
        return {"type": "learn_error", "error": str(exc),
                "codigo": getattr(exc, "codigo", "report")}


def rjob_hypotheses(db, req: dict, dono: str) -> dict:
    try:
        job = research_agents.carregar_job(db, dono, str(req.get("job_id", ""))[:64])
        items = research_agents.hypothesis_engine.HypothesisStore(db).list_for_job(
            dono, job["id"])
        return {"type": "research_hypotheses",
                "hypotheses": [vars(item) for item in items]}
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}


def rjob_delete(db, req: dict, dono: str) -> dict:
    job_id = str(req.get("job_id", ""))[:64]
    with JOBS_BG_LOCK:
        if job_id in JOBS_BG:
            return {"type": "learn_error", "error": "Pesquisa em andamento.",
                    "codigo": "ocupado"}
    try:
        return {"type": "research_deleted",
                **research_agents.excluir_job(db, dono, job_id)}
    except research_agents.AgentErro as exc:
        return {"type": "learn_error", "error": str(exc), "codigo": exc.codigo}


def recover_interrupted_ai(db):
    """Only on agent process startup; preserve partial text for interrupted work."""
    with db:
        db.execute("UPDATE ai_requests SET state='failed', error=?, updated_at=? "
                   "WHERE state IN ('queued','processing')",
                   ("Agente reiniciado durante a geração. Tente novamente.", agora_iso()))


def recover_interrupted_research(db) -> int:
    """Marca jobs órfãos após reinício; nunca apaga plano/evidências.

    `em_andamento`/`criada` não têm worker após o boot. Sem isso, o job
    ficaria "vivo" para sempre e bloquearia novas pesquisas do dono.
    """
    rows = db.execute("SELECT id, owner_id FROM research_jobs "
                      "WHERE status IN ('em_andamento','criada')").fetchall()
    recuperados = 0
    for job_id, owner in rows:
        try:
            job = research_agents.carregar_job(db, owner, job_id)
        except Exception:
            continue
        if job["status"] not in ("em_andamento", "criada"):
            continue
        job["status"] = "interrompida"
        job["pendencias"].append("Agente reiniciado; pesquisa retomável.")
        job["pendencias"] = job["pendencias"][-20:]
        try:
            research_agents.salvar_job(db, job)
            research_agents.emitir(db, job_id, owner, "orchestrator",
                                   "research_cancelled", "alerta",
                                   "Interrompida pelo reinício do agente; retomável.", {})
            recuperados += 1
        except Exception:
            continue
    return recuperados
