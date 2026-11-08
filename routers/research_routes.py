"""Router: Pesquisa profunda: jobs, evidências, relatórios, exportação e SSE."""
import asyncio
import json
import re
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from relay_core import (
    _rate_limit, erro_relay, relay, require_csrf, ResearchSSECursor, revogacao_ok,
    verify_session,
)

router = APIRouter()

class ResearchStartIn(BaseModel):
    model: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9_~.:/-]*$")
    objetivo: str = Field(min_length=3, max_length=500)
    conv: str = Field(default="", max_length=100)
    modo: str = Field(default="", max_length=20)


class ResearchJobIn(BaseModel):
    job_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


def _research_erro(result: dict) -> HTTPException:
    codigo = result.get("codigo", "erro")
    if codigo == "bloqueada":
        return erro_relay(result, "Conta indisponível.")
    if codigo == "ausente":
        raise HTTPException(404, result.get("error", "Pesquisa não encontrada"))
    if codigo == "ocupado":
        raise HTTPException(409, result.get("error", "Pesquisa em andamento"))
    return HTTPException(503, result.get("error", "Pesquisa indisponível"))


@router.post("/api/research/start")
async def research_start(request: Request, body: ResearchStartIn):
    """Inicia pesquisa agêntica em background (1 ativa por dono)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "research_start", dono)
    result = await relay.exchange({"type": "research_job_start", "owner": dono,
                                   "objetivo": body.objetivo, "conv": body.conv,
                                   "modo": body.modo, "model": body.model}, timeout=20.0)
    if result.get("type") != "research_job":
        raise _research_erro(result)
    return {"job_id": result["job_id"], "modo": result.get("modo", ""),
            "etapas": result.get("etapas", 0)}


@router.get("/api/research/status")
async def research_status(request: Request, job_id: str, apos_seq: int = 0):
    """Estado + eventos desde apos_seq (polling; dedupe por seq no cliente)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_status", "owner": dono,
                                   "job_id": job_id, "apos_seq": apos_seq}, timeout=20.0)
    if result.get("type") != "research_status":
        raise _research_erro(result)
    return {"resumo": result.get("resumo", {}), "eventos": result.get("eventos", [])}


@router.post("/api/research/cancel")
async def research_cancel(request: Request, body: ResearchJobIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_job_cancel", "owner": dono,
                                   "job_id": body.job_id}, timeout=20.0)
    if result.get("type") != "research_cancelled":
        raise _research_erro(result)
    result.pop("type", None)
    return result


@router.get("/api/research/jobs")
async def research_jobs(request: Request):
    """Histórico de pesquisas do dono (memória de investigações)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_jobs_list", "owner": dono},
                                  timeout=20.0)
    if result.get("type") != "research_jobs":
        raise _research_erro(result)
    return {"jobs": result.get("jobs", [])}


@router.get("/api/research/evidence")
async def research_evidence(request: Request, job_id: str):
    """Evidências do job (links reais para o painel)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_evidence", "owner": dono,
                                   "job_id": job_id}, timeout=20.0)
    if result.get("type") != "research_evidence":
        raise _research_erro(result)
    return {"evidencias": result.get("evidencias", [])}


@router.get("/api/research/hypotheses")
async def research_hypotheses(request: Request, job_id: str):
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_hypotheses", "owner": dono,
                                   "job_id": job_id}, timeout=20.0)
    if result.get("type") != "research_hypotheses":
        raise _research_erro(result)
    return {"hypotheses": result.get("hypotheses", [])}


@router.get("/api/research/report")
async def research_report(request: Request, job_id: str,
                          report_type: str = "executive_summary"):
    from research_reports import REPORT_TYPES

    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    if report_type not in REPORT_TYPES:
        raise HTTPException(422, "Tipo de relatório inválido")
    result = await relay.exchange({"type": "research_job_report", "owner": dono,
                                   "job_id": job_id, "report_type": report_type},
                                  timeout=20.0)
    if result.get("type") != "research_report":
        raise _research_erro(result)
    return {k: v for k, v in result.items() if k != "type"}


@router.get("/api/research/view")
async def research_view(request: Request, job_id: str):
    """JDUI 4.0 a partir de registros reais (componentes validados no backend)."""
    import research_view

    verify_session(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", job_id or ""):
        raise HTTPException(422, "Identificador inválido")
    status = await relay.exchange({"type": "research_job_status", "owner": dono,
                                   "job_id": job_id, "apos_seq": 0}, timeout=20.0)
    if status.get("type") != "research_status":
        raise _research_erro(status)
    evidence = await relay.exchange({"type": "research_job_evidence", "owner": dono,
                                     "job_id": job_id}, timeout=20.0)
    if evidence.get("type") != "research_evidence":
        raise _research_erro(evidence)
    hypotheses = await relay.exchange({"type": "research_job_hypotheses", "owner": dono,
                                       "job_id": job_id}, timeout=20.0)
    if hypotheses.get("type") != "research_hypotheses":
        raise _research_erro(hypotheses)
    message = research_view.build_view(
        status.get("resumo", {}), evidence.get("evidencias", []),
        hypotheses.get("hypotheses", []))
    return {"message": message}


@router.get("/api/research/export")
async def research_export(request: Request, job_id: str, formato: str = "md"):
    """Gera bytes reais no servidor a partir dos registros owner-scoped.

    Nada é persistido/rehospedado no Render.  O conteúdo vem do PC via relay;
    se o job não pertence ao dono autenticado, o PC responde ``ausente``.
    """
    import research_exports

    verify_session(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", job_id or ""):
        raise HTTPException(422, "Identificador inválido")
    if formato not in research_exports.FORMATS:
        raise HTTPException(422, "Formato inválido; use md, csv ou json")
    status = await relay.exchange({"type": "research_job_status", "owner": dono,
                                   "job_id": job_id, "apos_seq": 0}, timeout=20.0)
    if status.get("type") != "research_status":
        raise _research_erro(status)
    evidence = await relay.exchange({"type": "research_job_evidence", "owner": dono,
                                     "job_id": job_id}, timeout=20.0)
    if evidence.get("type") != "research_evidence":
        raise _research_erro(evidence)
    hypotheses = await relay.exchange({"type": "research_job_hypotheses", "owner": dono,
                                       "job_id": job_id}, timeout=20.0)
    if hypotheses.get("type") != "research_hypotheses":
        raise _research_erro(hypotheses)
    try:
        payload, media_type, filename = research_exports.build_export(
            status.get("resumo", {}), evidence.get("evidencias", []),
            hypotheses.get("hypotheses", []), formato)
    except research_exports.ExportError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(payload, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.delete("/api/research/{job_id}")
async def research_delete(request: Request, job_id: str):
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", job_id):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "research_job_delete", "owner": dono,
                                   "job_id": job_id}, timeout=20.0)
    if result.get("type") != "research_deleted":
        raise _research_erro(result)
    return {"ok": True, "job_id": job_id}


class ResearchInterveneIn(BaseModel):
    job_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    op: str = Field(min_length=3, max_length=30, pattern=r"^[a-z_]+$")
    params: dict = Field(default_factory=dict, max_length=10)

    @field_validator("params")
    @classmethod
    def _params_limitados(cls, valor: dict) -> dict:
        for chave, item in valor.items():
            if not isinstance(chave, str) or not (1 <= len(chave) <= 40):
                raise ValueError("parâmetro inválido")
            if isinstance(item, bool) or isinstance(item, (int, float)):
                continue
            if isinstance(item, str) and len(item) <= 500:
                continue
            raise ValueError("parâmetro inválido")
        if len(json.dumps(valor, ensure_ascii=False)) > 4000:
            raise ValueError("parâmetros grandes demais")
        return valor


class ResearchPauseIn(BaseModel):
    job_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    pausar: bool = True


@router.post("/api/research/intervene")
async def research_intervene(request: Request, body: ResearchInterveneIn):
    """Alteração estruturada do plano (sem LLM; feita preservada)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_job_intervene", "owner": dono,
                                   "job_id": body.job_id, "op": body.op,
                                   "params": body.params}, timeout=20.0)
    if result.get("type") != "research_intervened":
        raise _research_erro(result)
    result.pop("type", None)
    return result


@router.post("/api/research/pause")
async def research_pause(request: Request, body: ResearchPauseIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "research_job_pause", "owner": dono,
                                   "job_id": body.job_id,
                                   "pausar": "1" if body.pausar else "0"}, timeout=20.0)
    if result.get("type") != "research_paused":
        raise _research_erro(result)
    result.pop("type", None)
    return result


@router.get("/api/research/stream")
async def research_stream(request: Request, job_id: str, apos_seq: int = 0):
    """SSE de telemetria real: backlog autoritativo + push ao vivo.

    Polling continua válido como fallback (mesmo contrato, mesmos seqs).
    """
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(job_id) <= 64):
        raise HTTPException(422, "Identificador inválido")
    _rate_limit(request, "research_stream", dono)
    if relay.ws is None:
        raise HTTPException(503, "Computador desconectado; use o painel com polling")
    if sum(1 for sub in relay.research_subs.values()
           if sub.get("owner") == dono) >= 4:
        raise HTTPException(429, "Muitos acompanhamentos; tente de novo",
                            headers={"Retry-After": "15"})
    if len(relay.research_subs) >= 20:
        raise HTTPException(429, "Muitos acompanhamentos; tente de novo",
                            headers={"Retry-After": "15"})
    from fastapi.responses import StreamingResponse
    fila: asyncio.Queue = asyncio.Queue(maxsize=200)
    sub_id = uuid.uuid4().hex
    relay.research_subs[sub_id] = {"job_id": job_id, "owner": dono, "fila": fila,
                                   "perdidos": 0}
    backlog = await relay.exchange({"type": "research_job_status", "owner": dono,
                                    "job_id": job_id, "apos_seq": apos_seq}, timeout=20.0)
    if backlog.get("type") != "research_status":
        relay.research_subs.pop(sub_id, None)
        raise _research_erro(backlog)

    async def gerar():
        cursor = ResearchSSECursor(apos_seq)
        try:
            eventos_backlog = [e for e in backlog.get("eventos", [])
                               if isinstance(e, dict)]
            terminal_backlog = any(ResearchSSECursor.terminal(e)
                                   for e in eventos_backlog)
            for ev in eventos_backlog:
                for pronto in cursor.oferecer(ev):
                    yield ("event: research\n"
                           f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
            if terminal_backlog:
                for pronto in cursor.liberar_tudo():
                    yield ("event: research\n"
                           f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                return
            espera = 0.0
            while True:
                try:
                    ev = await asyncio.wait_for(fila.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    espera += 15.0
                    if espera >= 360.0:
                        return
                    # Lacuna não preenchida: libera o que chegou em ordem para
                    # não deixar a interface parada; o polling continua válido.
                    for pronto in cursor.liberar_tudo():
                        yield ("event: research\n"
                               f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                    yield ": ping\n\n"
                    continue
                if not isinstance(ev, dict):
                    continue
                if ev.get("seq", 0) == -1:
                    for pronto in cursor.liberar_tudo():
                        yield ("event: research\n"
                               f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                    yield ("event: error\n"
                           f"data: {json.dumps({'error': 'Agente desconectado'}, ensure_ascii=False)}\n\n")
                    return
                terminal = ResearchSSECursor.terminal(ev)
                for pronto in cursor.oferecer(ev):
                    yield ("event: research\n"
                           f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                if terminal:
                    for pronto in cursor.liberar_tudo():
                        yield ("event: research\n"
                               f"data: {json.dumps(pronto, ensure_ascii=False)}\n\n")
                    return
        finally:
            relay.research_subs.pop(sub_id, None)

    return StreamingResponse(gerar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


class AgenticResearchWebhookIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    mode: str = Field(default="deep_investigate", pattern=r"^(deep_investigate|compare_products)$")
    webhook_url: str = Field(default="", max_length=1000)
    max_retries: int = Field(default=3, ge=1, le=3)
    min_deep_links: int = Field(default=3, ge=1, le=8)
    max_sites: int = Field(default=5, ge=1, le=10)
    async_dispatch: bool = Field(default=True)


def _authorize_webhook_or_session(request: Request) -> str:
    """Autentica via token de webhook (`X-Vexx-Webhook-Token`) ou sessão autenticada."""
    import hmac
    import os
    expected_token = os.environ.get("JULIA_WEBHOOK_SECRET", "").strip()
    provided_token = (request.headers.get("x-vexx-webhook-token") or "").strip()
    if expected_token and provided_token and hmac.compare_digest(expected_token, provided_token):
        return "webhook"
    require_csrf(request)
    verify_session(request)
    return "session"


@router.post("/api/research/deep-investigate")
async def research_deep_investigate_endpoint(request: Request, body: AgenticResearchWebhookIn):
    """Executa `deep_investigate_topic` com Loop Agêntico de Auto-Correção."""
    _authorize_webhook_or_session(request)
    import agentic_deep_research
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: agentic_deep_research.deep_investigate_topic(
            body.query,
            min_deep_links=body.min_deep_links,
            max_retries=body.max_retries,
        ),
    )
    if body.webhook_url:
        dispatch = agentic_deep_research.handle_webhook_response(
            result, webhook_url=body.webhook_url, background=body.async_dispatch
        )
        result["webhook_dispatch"] = dispatch
    return result


@router.post("/api/research/compare-products")
async def research_compare_products_endpoint(request: Request, body: AgenticResearchWebhookIn):
    """Executa `search_and_compare_products` extraindo preços, tamanhos, estilos e cores."""
    _authorize_webhook_or_session(request)
    import agentic_deep_research
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: agentic_deep_research.search_and_compare_products(
            body.query,
            max_retries=body.max_retries,
            max_sites=body.max_sites,
        ),
    )
    if body.webhook_url:
        dispatch = agentic_deep_research.handle_webhook_response(
            result, webhook_url=body.webhook_url, background=body.async_dispatch
        )
        result["webhook_dispatch"] = dispatch
    return result


@router.post("/api/research/webhook")
async def research_webhook_endpoint(request: Request, body: AgenticResearchWebhookIn):
    """Endpoint de Webhook assíncrono do VEXX-AI: responde rápido sem timeout e entrega via callback."""
    _authorize_webhook_or_session(request)
    import agentic_deep_research

    request_id = f"vexx-wh-{uuid.uuid4().hex[:12]}"
    if body.async_dispatch and body.webhook_url:
        agentic_deep_research.research.url_segura(body.webhook_url)

        def _bg_job():
            if body.mode == "compare_products":
                data = agentic_deep_research.search_and_compare_products(
                    body.query, max_retries=body.max_retries, max_sites=body.max_sites
                )
            else:
                data = agentic_deep_research.deep_investigate_topic(
                    body.query, min_deep_links=body.min_deep_links, max_retries=body.max_retries
                )
            data["request_id"] = request_id
            agentic_deep_research.handle_webhook_response(
                data, webhook_url=body.webhook_url, background=False
            )

        asyncio.get_running_loop().run_in_executor(None, _bg_job)
        return {
            "accepted": True,
            "request_id": request_id,
            "status": "processing",
            "mode": body.mode,
            "webhook_url": body.webhook_url,
        }

    loop = asyncio.get_running_loop()
    if body.mode == "compare_products":
        data = await loop.run_in_executor(
            None,
            lambda: agentic_deep_research.search_and_compare_products(
                body.query, max_retries=body.max_retries, max_sites=body.max_sites
            ),
        )
    else:
        data = await loop.run_in_executor(
            None,
            lambda: agentic_deep_research.deep_investigate_topic(
                body.query, min_deep_links=body.min_deep_links, max_retries=body.max_retries
            ),
        )
    data["request_id"] = request_id
    return agentic_deep_research.handle_webhook_response(
        data, webhook_url=body.webhook_url or None, background=body.async_dispatch
    )
