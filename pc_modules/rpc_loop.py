"""Módulo do PC Agent: Loop principal de conexão WebSocket e despacho RPC do agente do PC."""
import docs_agent
import files_agent
import hermes_bridge
import json
import julia_auth as JULIA_auth
import learning
import os
import providers
import random
import re
import remote_access
import remoto
import threading
import time
import workspace_store

from pathlib import Path
from urllib.parse import urlparse
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from pc_modules.ai_pipeline import (
    ai_completa, ai_stream_worker, enviar_ws, ENVIO_LOCK, SessaoStream,
)
from pc_modules.context_providers import (
    _apagar_todos_dados, definir_chave_provedor, dono_bloqueado, remover_chave_provedor,
    resposta_input, submit_screen,
)
from pc_modules.db_core import (
    ai_config, configurar_log_persistente, database_path, dono_valido, hello_agente,
    list_messages, log, open_db, persist_messages,
)
from pc_modules.study_lifecycle import ai_continuar, ai_resetar
from pc_modules.memory_store import aprendizado_ativo, definir_aprendizado, registrar_memoria
from pc_modules.calendar_projects import confirmar_pendencia, listar_conversas, proximos_eventos
from pc_modules.research_jobs import (
    recover_interrupted_ai, recover_interrupted_research, rjob_cancel, rjob_delete,
    rjob_evidence, rjob_hypotheses, rjob_intervene, rjob_list, rjob_pause, rjob_report,
    rjob_start, rjob_status,
)

def run():
    configurar_log_persistente()
    relay_url = os.environ.get("JULIA_RELAY_URL", "").strip().rstrip("/")
    token = os.environ.get("JULIA_AGENT_TOKEN", "")
    if not relay_url or not token:
        raise SystemExit("Configure JULIA_RELAY_URL e JULIA_AGENT_TOKEN")
    parsed = urlparse(relay_url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise SystemExit("JULIA_RELAY_URL inválida")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("O agente exige HTTPS fora de localhost")
    ws_url = f"{'wss' if parsed.scheme == 'https' else 'ws'}://{parsed.netloc}/api/agent/ws"
    db = open_db(database_path())
    recover_interrupted_ai(db)
    recuperados = recover_interrupted_research(db)
    if recuperados:
        log.info("Pesquisas órfãs marcadas como interrompidas: %d", recuperados)
    cfg = ai_config()
    try:
        modelos = hermes_bridge.listar_modelos(cfg["proxy"])
        log.info("Hermes proxy OK: %d modelos (padrão %s)", len(modelos), cfg["model"])
    except hermes_bridge.BridgeErro as exc:
        log.warning("Hermes indisponível no boot (%s). Mensagens serão guardadas; IA tenta depois.",
                    exc)
    pause = 2
    log.info("SQLite local preparado: %s", database_path())
    if remoto.entrada_ativada():
        log.warning("CONTROLE REMOTO ATIVO (JULIA_REMOTE=1): cliques/teclas do celular serão executados. Comandos registrados no log.")
    else:
        log.info("Controle remoto desativado (somente visualização). Defina JULIA_REMOTE=1 para ativar.")
    cancelados: dict = {}
    while True:
        espera = min(60.0, pause) + random.uniform(0, min(5.0, pause * 0.25))
        try:
            with connect(ws_url, additional_headers={"Authorization": "Bearer " + token},
                          open_timeout=20, ping_interval=20, ping_timeout=20, max_size=25_000_000) as websocket:
                log.info("Conectado ao relay. Nenhuma porta de entrada foi aberta no PC.")
                pause = 2
                try:
                    enviar_ws(websocket, hello_agente(db))
                except Exception:
                    log.warning("Nao foi possivel anunciar commit/PID ao relay.")
                for raw in websocket:
                    req = json.loads(raw)
                    request_id = req.get("request_id")
                    if not isinstance(request_id, str):
                        continue
                    dono = dono_valido(req.get("owner"))
                    tipo = req.get("type")

                    def _exige_admin():
                        u = JULIA_auth.buscar_uid(db, dono)
                        approved = db.execute("SELECT aprovado FROM users WHERE uid=?", (dono,)).fetchone()
                        if not u or u.get("role") != "admin" or u.get("status") != "ativo" or not approved or not approved[0]:
                            return None
                        if dono != "local" or req.get("sid"):
                            current = JULIA_auth.sessao_valida(db, req.get("sid", ""))
                            if not current or current.get("uid") != dono:
                                return None
                        return u

                    def _resp_ok(_tipo, **campos):
                        return {"request_id": request_id, "type": _tipo, **campos}

                    def _resp_erro(msg, codigo="erro"):
                        return {"request_id": request_id, "type": "auth_error"
                                if tipo in ("auth_login", "auth_register") else "op_error",
                                "error": msg, "codigo": codigo}

                    if tipo in ("sync", "list", "conversations", "workspace_sync", "doc_upload", "doc_list",
                                "doc_resumo", "doc_topicos", "doc_search", "doc_compare", "doc_delete",
                                "file_list", "file_download", "file_delete",
                                "mem_list", "mem_list_full",
                                "mem_forget", "mem_confirm", "mem_update", "ui_state_save",
                                "ui_state_list", "conv_forget", "event_list", "ai", "ai_stream",
                                "ai_reset", "ai_continue", "provider_key") and dono_bloqueado(db, dono):
                        reply = _resp_erro("Conta indisponível.", "bloqueada")
                    elif tipo in ("admin_identity", "admin_verify_password", "admin_console_overview", "admin_console_audit"):
                        import admin_console
                        try:
                            reply = {"request_id": request_id, **admin_console.handle(db, req, __import__("sys").modules[__name__])}
                        except JULIA_auth.AuthErro as exc:
                            reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "companion_registry":
                        import companion_registry
                        reply = {"request_id": request_id, **companion_registry.handle(db, req)}
                    elif tipo == "auth_login":
                        try:
                            user = JULIA_auth.login_conta(db, req.get("username", ""),
                                                          req.get("password", ""),
                                                          str(req.get("cliente", ""))[:80])
                            sess = JULIA_auth.criar_sessao(db, user["uid"])
                            reply = _resp_ok("auth_ok", uid=user["uid"], username=user["username"],
                                             display=user["display"], role=user["role"],
                                             sid=sess["sid"], expira_em=sess["expira_em"])
                        except JULIA_auth.AuthErro as exc:
                            reply = _resp_erro(str(exc), exc.codigo)
                            if exc.retry_after:
                                reply["retry_after"] = exc.retry_after
                    elif tipo == "auth_register":
                        try:
                            reg = JULIA_auth.registrar(db, req.get("display", ""),
                                                       req.get("username", ""),
                                                       req.get("password", ""),
                                                       req.get("invite", ""))
                            out = {"uid": reg["uid"], "username": reg["username"],
                                   "display": reg["display"], "status": reg["status"]}
                            if reg["status"] == "ativo" and reg["uid"]:
                                sess = JULIA_auth.criar_sessao(db, reg["uid"])
                                out["sid"] = sess["sid"]
                                out["expira_em"] = sess["expira_em"]
                            reply = _resp_ok("auth_registered", **out)
                        except JULIA_auth.AuthErro as exc:
                            reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "auth_config":
                        reply = _resp_ok("auth_config", modo=JULIA_auth.modo_cadastro(db),
                                         exigir_aprovacao=JULIA_auth.config_get(
                                             db, "exigir_aprovacao", "1") == "1")
                    elif tipo == "auth_logout":
                        JULIA_auth.revogar_sessao(db, req.get("sid", ""))
                        reply = _resp_ok("auth_logged_out")
                    elif tipo == "auth_whoami":
                        user = JULIA_auth.sessao_valida(db, req.get("sid", ""))
                        reply = _resp_ok("auth_user", user=user) if user else \
                            _resp_erro("Sessão inválida.", "sessao")
                    elif tipo == "account_password":
                        if req.get("uid") != dono:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                JULIA_auth.trocar_senha(db, dono, req.get("atual", ""),
                                                        req.get("nova", ""))
                                reply = _resp_ok("account_ok")
                            except JULIA_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "account_delete":
                        try:
                            alvo = JULIA_auth.buscar_uid(db, dono)
                            if not alvo or not JULIA_auth.confere_senha(
                                    req.get("password", ""),
                                    (JULIA_auth.buscar_usuario(db, alvo["username"]) or {}).get("hash", "")):
                                raise JULIA_auth.AuthErro("Senha incorreta.", "senha")
                            n_admin = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' "
                                                 "AND status='ativo'").fetchone()[0]
                            if alvo["role"] == "admin" and n_admin <= 1:
                                raise JULIA_auth.AuthErro(
                                    "Último admin: transfira antes de excluir.", "ultimo_admin")
                            total = _apagar_todos_dados(db, dono)
                            JULIA_auth.auditar(db, dono, "conta_autoexcluida", alvo["username"],
                                               f"registros={total}")
                            reply = _resp_ok("account_deleted", apagados=total)
                        except JULIA_auth.AuthErro as exc:
                            reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_users":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            rows = db.execute("SELECT uid, username, display, role, status, "
                                              "aprovado, created_at, last_seen, max_ai_hora, max_ia_simult FROM users "
                                              "ORDER BY created_at").fetchall()
                            pend = db.execute("SELECT COUNT(*) FROM reg_requests "
                                              "WHERE status='pendente'").fetchone()[0]
                            reply = _resp_ok("admin_users",
                                             users=[{"uid": u, "username": n, "display": d,
                                                     "role": r, "status": s, "aprovado": bool(a),
                                                     "created_at": c, "last_seen": l, "max_ai_hora": mh, "max_ia_simult": ms}
                                                    for u, n, d, r, s, a, c, l, mh, ms in rows],
                                             pendentes=pend)
                    elif tipo == "admin_user_create":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                papel = req.get("role", "user") if req.get("role") in ("admin", "user") else "user"
                                user = JULIA_auth.criar_usuario(
                                    db, req.get("username", ""), req.get("display", ""),
                                    req.get("password", ""), papel=papel, criado_por=dono)
                                reply = _resp_ok("admin_user_created", **user)
                            except JULIA_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_user_role":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                JULIA_auth.definir_papel(db, dono, req.get("uid", ""), req.get("role", ""))
                                reply = _resp_ok("admin_ok")
                            except JULIA_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_user_status":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                JULIA_auth.definir_status(db, dono, req.get("uid", ""),
                                                          req.get("status", ""), req.get("dias", 0))
                                reply = _resp_ok("admin_ok")
                            except JULIA_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_user_delete":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                n = JULIA_auth.excluir_usuario(db, dono, req.get("uid", ""))
                                reply = _resp_ok("admin_ok", apagados=n)
                            except JULIA_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_invite_create":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            conv = JULIA_auth.gerar_convite(db, dono, req.get("max_usos", 1),
                                                           req.get("dias", 7), req.get("nota", ""))
                            reply = _resp_ok("admin_invite", **conv)
                    elif tipo == "admin_invites":
                        adm = _exige_admin()
                        reply = _resp_ok("admin_invites",
                                         invites=JULIA_auth.listar_convites(db)) if adm else \
                            _resp_erro("Sem permissão.", "permissao")
                    elif tipo == "admin_invite_revoke":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            JULIA_auth.revogar_convite(db, dono, req.get("id", 0))
                            reply = _resp_ok("admin_ok")
                    elif tipo == "admin_regs":
                        adm = _exige_admin()
                        reply = _resp_ok("admin_regs",
                                         pedidos=JULIA_auth.listar_pedidos(db)) if adm else \
                            _resp_erro("Sem permissão.", "permissao")
                    elif tipo == "admin_reg_decide":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                JULIA_auth.decidir_pedido(db, dono, req.get("id", 0),
                                                          bool(req.get("aprovar")))
                                reply = _resp_ok("admin_ok")
                            except JULIA_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "admin_config_set":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            modo = str(req.get("modo", ""))
                            if modo and modo not in JULIA_auth.MODOS:
                                reply = _resp_erro("Modo inválido.", "invalido")
                            else:
                                if modo:
                                    JULIA_auth.config_set(db, "modo_cadastro", modo)
                                if "exigir_aprovacao" in req:
                                    JULIA_auth.config_set(
                                        db, "exigir_aprovacao",
                                        "1" if req.get("exigir_aprovacao") else "0")
                                JULIA_auth.auditar(db, dono, "config_alterada", "",
                                                   f"modo={modo or '-'}")
                                reply = _resp_ok("admin_ok")
                    elif tipo == "admin_audit":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            rows = db.execute("SELECT ts, ator, acao, alvo, detalhe FROM audit_log "
                                              "ORDER BY id DESC LIMIT 200").fetchall()
                            reply = _resp_ok("admin_audit",
                                             eventos=[{"ts": t, "ator": a, "acao": c,
                                                       "alvo": al, "detalhe": d}
                                                      for t, a, c, al, d in rows])
                    elif tipo == "admin_sess_revoke":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            with db:
                                db.execute("UPDATE user_sessions SET revogada=1 WHERE uid=?",
                                           (str(req.get("uid", "")),))
                            JULIA_auth.auditar(db, dono, "sessoes_revogadas", str(req.get("uid", "")))
                            reply = _resp_ok("admin_ok")
                    elif tipo == "quality_run":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                import tempfile
                                import research_quality_lab
                                with tempfile.TemporaryDirectory(prefix="julia-quality-") as tmp:
                                    base = Path(tmp) / "run"
                                    rep = research_quality_lab.run_document_retrieval_benchmark(
                                        Path("benchmarks") / "research_quality_v1.json", base)
                                rid = research_quality_lab.store_report(db, dono, rep)
                                JULIA_auth.auditar(db, dono, "quality_run", rid)
                                reply = _resp_ok("quality_run", run_id=rid,
                                                 summary=rep.get("summary", {}),
                                                 dataset=rep.get("dataset", {}))
                            except Exception as exc:
                                reply = _resp_erro(f"Benchmark falhou: {type(exc).__name__}.",
                                                   "benchmark")
                    elif tipo == "quality_runs":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            import research_quality_lab
                            reply = _resp_ok("quality_runs",
                                             runs=research_quality_lab.list_reports(db, dono))
                    elif tipo == "admin_user_limits":
                        adm = _exige_admin()
                        if not adm:
                            reply = _resp_erro("Sem permissão.", "permissao")
                        else:
                            try:
                                JULIA_auth.update_limits(db, dono, str(req.get("uid", "")),
                                                        req.get("max_ai_hora", 0), req.get("max_ia_simult", 0),
                                                        req.get("remote_ok", None))
                                reply = _resp_ok("admin_ok")
                            except JULIA_auth.AuthErro as exc:
                                reply = _resp_erro(str(exc), exc.codigo)
                    elif tipo == "sess_revogados":
                        reply = _resp_ok("sess_revogados", sids=JULIA_auth.sids_revogados(db))
                    elif req.get("type") == "sync":
                        confirmed_ids = persist_messages(db, req.get("messages", []), dono)
                        reply = {"request_id": request_id, "type": "ack", "confirmed_ids": confirmed_ids}
                    elif req.get("type") == "list":
                        reply = {"request_id": request_id, "type": "history",
                                 "messages": list_messages(db, req.get("limit", 200), dono,
                                     str(req.get("conversation_id", "")), req.get("before"))}
                    elif req.get("type") == "workspace_sync":
                        try:
                            workspace_store.merge_records(db, req.get("records", []), dono)
                            reply = {"request_id": request_id, "type": "workspace_synced",
                                     "records": workspace_store.list_records(db, dono)}
                        except ValueError:
                            reply = _resp_erro("Organização inválida.", "invalid_workspace")
                    elif req.get("type") == "conversations":
                        reply = {"request_id": request_id, "type": "conversations",
                                 "conversations": listar_conversas(db, req.get("limit", 100), dono)}
                    elif req.get("type") == "doc_upload":
                        try:
                            import base64 as _b64
                            data_b64 = req.get("data_b64", "")
                            if not isinstance(data_b64, str) or len(data_b64) > ((docs_agent.MAX_BYTES + 2) // 3) * 4:
                                raise docs_agent.DocErro("Arquivo grande demais (limite 15MB).", "grande")
                            raw = _b64.b64decode(data_b64, validate=True)
                            meta = docs_agent.salvar_documento(
                                db, req.get("name", "arquivo"),
                                raw, req.get("conversation_id", "geral"), dono)
                            reply = {"request_id": request_id, "type": "doc_uploaded", **meta}
                        except Exception as exc:
                            codigo = getattr(exc, "codigo", "erro")
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300], "codigo": codigo}
                    elif req.get("type") == "doc_list":
                        reply = {"request_id": request_id, "type": "doc_list",
                                 "documents": docs_agent.listar_documentos(db, req.get("limit", 50), dono)}
                    elif req.get("type") == "doc_search":
                        try:
                            doc_id = str(req.get("doc_id", ""))[:64]
                            if doc_id and not db.execute(
                                    "SELECT 1 FROM documents WHERE id=? AND owner_id=?", (doc_id, dono)).fetchone():
                                raise docs_agent.DocErro("Documento não encontrado.", "nao_encontrado")
                            reply = {"request_id": request_id, "type": "doc_search",
                                     "results": docs_agent.trechos_relevantes(
                                         db, str(req.get("query", ""))[:500], doc_id,
                                         k=min(int(req.get("limit", 5)), 20), owner=dono)}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "doc_compare":
                        try:
                            reply = {"request_id": request_id, "type": "doc_compare",
                                     **docs_agent.comparar_documentos(
                                         db, str(req.get("query", ""))[:500],
                                         req.get("doc_ids", []), owner=dono)}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "doc_delete":
                        deleted = docs_agent.excluir_documento(
                            db, str(req.get("doc_id", ""))[:64], dono)
                        reply = {"request_id": request_id,
                                 "type": "doc_deleted" if deleted else "doc_error",
                                 "doc_id": str(req.get("doc_id", ""))[:64],
                                 **({} if deleted else {"error": "Documento não encontrado.",
                                                       "codigo": "nao_encontrado"})}
                    elif req.get("type") == "doc_resumo":
                        try:
                            texto = docs_agent.resumir_documento(db, cfg, req.get("doc_id", ""), dono)
                            reply = {"request_id": request_id, "type": "doc_resumo",
                                     "doc_id": req.get("doc_id", ""), "resumo": texto}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "doc_topicos":
                        try:
                            texto = docs_agent.topicos_documento(db, cfg, req.get("doc_id", ""), dono)
                            reply = {"request_id": request_id, "type": "doc_topicos",
                                     "doc_id": req.get("doc_id", ""), "topicos": texto}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "doc_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "file_list":
                        try:
                            conv = req.get("conversation_id")
                            reply = {"request_id": request_id, "type": "file_list",
                                     "files": files_agent.listar_arquivos(
                                         db, req.get("limit", 50), dono,
                                         conversation_id=str(conv)[:100] if conv else None)}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "file_error",
                                     "error": str(exc)[:300], "codigo": "erro"}
                    elif req.get("type") == "file_download":
                        try:
                            reply = {"request_id": request_id, "type": "file_download",
                                     **files_agent.obter_arquivo(
                                         db, str(req.get("file_id", ""))[:64], dono)}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "file_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "file_delete":
                        try:
                            removed = files_agent.excluir_arquivo(
                                db, str(req.get("file_id", ""))[:64], dono)
                            reply = {"request_id": request_id,
                                     "type": "file_deleted" if removed else "file_error",
                                     "file_id": str(req.get("file_id", ""))[:64],
                                     **({} if removed else {"error": "Arquivo não encontrado.",
                                                            "codigo": "nao_encontrado"})}
                        except Exception as exc:
                            reply = {"request_id": request_id, "type": "file_error",
                                     "error": str(exc)[:300],
                                     "codigo": getattr(exc, "codigo", "erro")}
                    elif (req.get("type") or "").startswith(("learn_", "research_")) \
                            and dono_bloqueado(db, dono):
                        reply = {"request_id": request_id, "type": "learn_error",
                                 "error": "Conta indisponível.", "codigo": "bloqueada"}
                    elif req.get("type") == "learn_get":
                        try:
                            reply = {"request_id": request_id, "type": "learn_assessment",
                                     **learning.obter_assessment(
                                         db, dono, str(req.get("id", ""))[:64])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_attempt":
                        try:
                            reply = {"request_id": request_id, "type": "learn_attempt",
                                     **learning.iniciar_tentativa(
                                         db, dono, str(req.get("assessment_id", ""))[:64],
                                         str(req.get("id", ""))[:64])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_answer":
                        try:
                            reply = {"request_id": request_id, "type": "learn_answer",
                                     **learning.responder(
                                         db, dono, str(req.get("attempt_id", ""))[:64],
                                         str(req.get("question_id", ""))[:64],
                                         str(req.get("resposta", ""))[:2000])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_finish":
                        try:
                            reply = {"request_id": request_id, "type": "learn_result",
                                     **learning.finalizar_tentativa(
                                         db, dono, str(req.get("attempt_id", ""))[:64])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_avulso":
                        try:
                            reply = {"request_id": request_id, "type": "learn_avulso_ok",
                                     **learning.historico_avulso(
                                         db, dono, str(req.get("titulo", ""))[:160],
                                         str(req.get("assunto", ""))[:120],
                                         int(req.get("certas", 0) or 0),
                                         int(req.get("total", 0) or 0))}
                        except (learning.LearnErro, TypeError, ValueError) as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "learn_stats":
                        reply = {"request_id": request_id, "type": "learn_stats",
                                 "resumo": learning.resumo_progresso(db, dono),
                                 "por_assunto": learning.desempenho_por_assunto(db, dono)}
                    elif req.get("type") == "learn_plan_create":
                        try:
                            itens = req.get("itens", [])
                            reply = {"request_id": request_id, "type": "learn_plan",
                                     **learning.criar_plano(
                                         db, dono, str(req.get("titulo", ""))[:160],
                                         str(req.get("objetivo", ""))[:500],
                                         str(req.get("assunto", ""))[:120],
                                         str(req.get("prazo_iso", ""))[:32],
                                         req.get("min_dia", 30),
                                         itens if isinstance(itens, list) else [],
                                         str(req.get("id", ""))[:64])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_plan_get":
                        try:
                            reply = {"request_id": request_id, "type": "learn_plan_full",
                                     **learning.obter_plano(db, dono, str(req.get("id", ""))[:64])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_plan_item":
                        try:
                            reply = {"request_id": request_id, "type": "learn_plan_progress",
                                     "progresso": learning.concluir_item(
                                         db, dono, str(req.get("plan_id", ""))[:64],
                                         int(req.get("item_id", 0) or 0),
                                         str(req.get("feito", "1")).lower() not in ("0", "false", "nao", "não"))}
                        except (learning.LearnErro, TypeError, ValueError) as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "learn_plan_update":
                        try:
                            mud = req.get("mudancas", {})
                            reply = {"request_id": request_id, "type": "learn_plan_full",
                                     **learning.atualizar_plano(
                                         db, dono, str(req.get("plan_id", ""))[:64],
                                         mud if isinstance(mud, dict) else {})}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_plans":
                        reply = {"request_id": request_id, "type": "learn_plans",
                                 "planos": learning.listar_planos(db, dono)}
                    elif req.get("type") == "learn_cards_create":
                        try:
                            cards = req.get("cards", [])
                            reply = {"request_id": request_id, "type": "learn_cards",
                                     **learning.criar_flashcards(
                                         db, dono, cards if isinstance(cards, list) else [])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_cards_due":
                        try:
                            reply = {"request_id": request_id, "type": "learn_cards_due",
                                     "cards": learning.revisoes_pendentes(
                                         db, dono, limite=int(req.get("limite", 50) or 50))}
                        except (TypeError, ValueError) as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": "erro"}
                    elif req.get("type") == "learn_cards_review":
                        try:
                            reply = {"request_id": request_id, "type": "learn_cards_review",
                                     **learning.revisar_flashcard(
                                         db, dono, str(req.get("flashcard_id", ""))[:64],
                                         str(req.get("acertou", "1")).lower() in ("1", "true", "sim"))}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_recommend":
                        reply = {"request_id": request_id, "type": "learn_recommend",
                                 **learning.recomendar(db, dono)}
                    elif req.get("type") == "learn_flag":
                        try:
                            reply = {"request_id": request_id, "type": "learn_flag_ok",
                                     **learning.sinalizar_questao(
                                         db, dono, str(req.get("question_id", ""))[:64],
                                         str(req.get("motivo", ""))[:500])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_mistakes":
                        try:
                            reply = {"request_id": request_id, "type": "learn_mistakes",
                                     "erradas": learning.questoes_erradas(
                                         db, dono, int(req.get("limite", 20) or 20))}
                        except (TypeError, ValueError) as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": "erro"}
                    elif req.get("type") == "learn_lesson_create":
                        try:
                            aula = req.get("aula", {})
                            reply = {"request_id": request_id, "type": "learn_lesson",
                                     **learning.criar_aula(
                                         db, dono, aula if isinstance(aula, dict) else {},
                                         str(req.get("origem", "ia"))[:20],
                                         str(req.get("id", ""))[:64])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_lesson_get":
                        try:
                            reply = {"request_id": request_id, "type": "learn_lesson_full",
                                     **learning.obter_aula(db, dono, str(req.get("id", ""))[:64])}
                        except learning.LearnErro as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "learn_lessons":
                        reply = {"request_id": request_id, "type": "learn_lessons",
                                 "aulas": learning.listar_aulas(db, dono)}
                    elif req.get("type") == "learn_lesson_section":
                        try:
                            reply = {"request_id": request_id, "type": "learn_lesson_progress",
                                     **learning.concluir_secao(
                                         db, dono, str(req.get("lesson_id", ""))[:64],
                                         int(req.get("ordem", 0) or 0))}
                        except (learning.LearnErro, TypeError, ValueError) as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": getattr(exc, "codigo", "erro")}
                    elif req.get("type") == "learn_history":
                        try:
                            reply = {"request_id": request_id, "type": "learn_history",
                                     "tentativas": learning.historico_tentativas(
                                         db, dono, int(req.get("limite", 50) or 50))}
                        except (TypeError, ValueError) as exc:
                            reply = {"request_id": request_id, "type": "learn_error",
                                     "error": str(exc), "codigo": "erro"}
                    elif req.get("type") == "research_job_start":
                        reply = {"request_id": request_id,
                                 **rjob_start(db, req, dono, websocket)}
                    elif req.get("type") == "research_job_status":
                        reply = {"request_id": request_id, **rjob_status(db, req, dono)}
                    elif req.get("type") == "research_job_cancel":
                        reply = {"request_id": request_id, **rjob_cancel(db, req, dono)}
                    elif req.get("type") == "research_jobs_list":
                        reply = {"request_id": request_id, **rjob_list(db, dono)}
                    elif req.get("type") == "research_job_evidence":
                        reply = {"request_id": request_id, **rjob_evidence(db, req, dono)}
                    elif req.get("type") == "research_job_report":
                        reply = {"request_id": request_id, **rjob_report(db, req, dono)}
                    elif req.get("type") == "research_job_hypotheses":
                        reply = {"request_id": request_id, **rjob_hypotheses(db, req, dono)}
                    elif req.get("type") == "research_job_delete":
                        reply = {"request_id": request_id, **rjob_delete(db, req, dono)}
                    elif req.get("type") == "research_job_intervene":
                        reply = {"request_id": request_id, **rjob_intervene(db, req, dono)}
                    elif req.get("type") == "research_job_pause":
                        reply = {"request_id": request_id, **rjob_pause(db, req, dono)}
                    elif req.get("type") == "ui_state_save":
                        salvos = workspace_store.save_ui_states(db, dono, req.get("states", []))
                        reply = {"request_id": request_id, "type": "ui_state_saved", "saved": salvos}
                    elif req.get("type") == "ui_state_list":
                        rows = workspace_store.ui_state_page(db, dono, str(req.get("cursor", ""))[:200])
                        reply = {"request_id": request_id, "type": "ui_state_list", "states": rows,
                                 "next_cursor": rows[-1]["k"] if len(rows) == 200 else ""}
                    elif req.get("type") == "conv_forget":
                        conv = req.get("conversation_id", "")
                        n = 0
                        if isinstance(conv, str) and 3 <= len(conv) <= 100:
                            n = db.execute("SELECT count(*) FROM messages WHERE origin='mobile' "
                                           "AND owner_id=? AND conversation_id=?", (dono, conv)).fetchone()[0]
                            workspace_store.forget_chat(db, dono, conv)
                        log.info("conversa esquecida no PC: %s (%d msgs)", conv, n)
                        reply = {"request_id": request_id, "type": "conv_forgotten",
                                 "deleted": n}
                    elif req.get("type") == "mem_list":
                        rows = db.execute("SELECT key, value, updated_at FROM memories WHERE owner_id=? "
                                          "ORDER BY updated_at DESC LIMIT 100", (dono,)).fetchall()
                        reply = {"request_id": request_id, "type": "mem_list",
                                 "memories": [{"key": k, "value": v, "updated_at": u}
                                              for k, v, u in rows]}
                    elif req.get("type") == "mem_forget":
                        with db:
                            db.execute("DELETE FROM memories WHERE owner_id=? AND key=?",
                                       (dono, req.get("key", "")))
                            try:
                                db.execute("DELETE FROM memories_fts WHERE owner_id=? AND key=?",
                                           (dono, req.get("key", "")))
                            except Exception:
                                pass
                        reply = {"request_id": request_id, "type": "mem_forgotten",
                                 "key": req.get("key", "")}
                    elif req.get("type") == "mem_list_full":
                        rows = db.execute("SELECT key, value, tipo, assunto, status, origem_conv, "
                                          "origem_msg, valido_ate, updated_at FROM memories "
                                          "WHERE owner_id=? ORDER BY status, updated_at DESC LIMIT 200",
                                          (dono,)).fetchall()
                        reply = {"request_id": request_id, "type": "mem_list_full",
                                 "memories": [{"key": k, "value": v, "tipo": t, "assunto": a,
                                               "status": s, "origem_conv": oc, "origem_msg": om,
                                               "valido_ate": va, "updated_at": u}
                                              for k, v, t, a, s, oc, om, va, u in rows]}
                    elif req.get("type") == "mem_confirm":
                        feito = confirmar_pendencia(db, dono)
                        reply = {"request_id": request_id, "type": "mem_confirmed", **feito}
                    elif req.get("type") == "mem_update":
                        chave = re.sub(r"\s+", "_", str(req.get("key", "")).strip().lower())[:60]
                        valor = str(req.get("value", "")).strip()[:500]
                        if chave and valor:
                            registrar_memoria(db, dono, chave, valor)
                            reply = {"request_id": request_id, "type": "mem_updated", "key": chave}
                        else:
                            reply = {"request_id": request_id, "type": "mem_error",
                                     "error": "Chave ou valor inválido"}
                    elif req.get("type") == "mem_settings":
                        if "learning" in req:
                            definir_aprendizado(db, dono, str(req.get("learning")) == "1")
                        reply = {"request_id": request_id, "type": "mem_settings",
                                 "learning": aprendizado_ativo(db, dono)}
                    elif req.get("type") == "event_list":
                        reply = {"request_id": request_id, "type": "event_list",
                                 "events": proximos_eventos(db, dono)}
                    elif req.get("type") == "ai":
                        res = ai_completa(db, req, cfg)
                        reply = {"request_id": request_id, "type": "ai_done", **res}
                    elif req.get("type") == "ai_reset":
                        res = ai_resetar(db, req)
                        reply = {"request_id": request_id,
                                 **({"type": "ai_reset_ok", **res} if "ok" in res
                                    else {"type": "ai_error", **res})}
                    elif req.get("type") == "ai_continue":
                        res = ai_continuar(db, req, cfg)
                        reply = {"request_id": request_id,
                                 **({"type": "ai_done", **res} if "response_text" in res
                                    else {"type": "ai_error", **res})}
                    elif req.get("type") == "provider_key":
                        acao = str(req.get("action") or "set").strip().lower()
                        if acao == "set":
                            res = definir_chave_provedor(req)
                        elif acao == "del":
                            res = remover_chave_provedor(req)
                        else:
                            res = {"error": "Ação inválida.", "codigo": "acao"}
                        reply = {"request_id": request_id,
                                 **({"type": "provider_key_ok", **res} if "ok" in res
                                    else {"type": "ai_error", **res})}
                    elif req.get("type") == "ai_models":
                        try:
                            cat = providers.listar_tudo(cfg["proxy"])
                            reply = {"request_id": request_id, "type": "ai_models",
                                     "models": cat["models"][:2000],
                                     "items": cat["items"][:2000],
                                     "default": cat["default"],
                                     "providers": cat["providers"]}
                        except hermes_bridge.BridgeErro as exc:
                            reply = {"request_id": request_id, "type": "ai_error",
                                     "error": str(exc), "codigo": exc.codigo}
                    elif req.get("type") == "ai_stream":
                        if len(cancelados) >= 8 or request_id in cancelados:
                            enviar_ws(websocket, {"request_id": request_id, "type": "ai_error",
                                "codigo": "ocupado", "error": "Muitas respostas simultâneas; aguarde."})
                            continue
                        sessao = SessaoStream()
                        cancelados[request_id] = sessao
                        threading.Thread(target=ai_stream_worker,
                                         args=(database_path(), cfg, req, request_id,
                                               websocket, sessao, cancelados),
                                         daemon=True).start()
                        continue
                    elif req.get("type") == "ai_cancel":
                        alvo = req.get("target") if isinstance(req.get("target"), str) else request_id
                        sessao = cancelados.get(alvo)
                        if sessao is not None:
                            sessao.parar.set()
                        continue
                    elif req.get("type") == "remote_status":
                        reply = {"request_id": request_id, **remote_access.status(db, dono)}
                    elif req.get("type") == "remote_request":
                        reply = {"request_id": request_id, **remote_access.request_access(db, dono)}
                    elif req.get("type") == "remote_revoke":
                        reply = {"request_id": request_id, **remote_access.revoke(db, dono)}
                    elif req.get("type") == "screen":
                        submit_screen(database_path(), req, dono, request_id, websocket)
                        continue
                    elif req.get("type") == "input":
                        reply = resposta_input(db, req, dono, request_id)
                    else:
                        continue
                    with ENVIO_LOCK:
                        websocket.send(json.dumps(reply, ensure_ascii=False))
        except InvalidStatus as exc:
            # HTTP 403 no handshake = bloqueio anti-robô/rate-limit na borda
            # (Cloudflare), NÃO problema no agente. Martelar piora: espera longa.
            status = getattr(exc.response, "status_code", "?") if getattr(exc, "response", None) else "?"
            pause = min(1800, max(pause * 2, 120))
            espera = pause + random.uniform(0, 30)
            log.warning("Relay recusou o handshake (HTTP %s). Provável bloqueio temporário "
                        "anti-robô/rate-limit na borda — NÃO é erro de token. "
                        "Aguardando %ss antes de tentar (não force reconexões).",
                        status, espera)
        except (ConnectionClosed, ConnectionError, OSError, TimeoutError, ValueError) as exc:
            motivo = ""
            try:
                codigo = getattr(exc, "code", None)
                razao = getattr(exc, "reason", "")
                if codigo:
                    motivo = f" (código {codigo}: {razao})"
            except Exception:
                pass
            log.warning("Conexão interrompida (%s%s). Reconectando em %ss",
                        type(exc).__name__, motivo, espera)
            pause = min(60, pause * 2)
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("Falha inesperada no loop do agente; reconectando em %.1fs",
                          espera)
            pause = min(60, pause * 2)
        time.sleep(espera)
    db.close()
