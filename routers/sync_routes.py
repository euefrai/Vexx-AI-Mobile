"""Router: Status, sincronização de mensagens, workspace, exportação e estado de UI."""
import base64
import json
import re

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from workspace_store import WorkspaceBatch, WorkspaceRecord

from relay_core import (
    drift_agente, erro_relay, relay, require_csrf, revogacao_ok, SyncBody, verify_session,
    XlsxExport,
)

router = APIRouter()

@router.get("/api/status")
def status(request: Request):
    verify_session(request)
    drift = drift_agente()
    return {"pc_online": relay.ws is not None, "agente_ha": relay.ha(),
            "drift": drift["drift"], "stale": relay.ws is None or drift["drift"],
            "messages_stored_on": "computer"}


@router.post("/api/export/xlsx")
async def export_xlsx(request: Request, body: XlsxExport):
    """Gera planilha de uma conversa já carregada no dispositivo autenticado."""
    require_csrf(request)
    await revogacao_ok(request)
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    def cell_text(value: str) -> str:
        text = str(value or "")
        return "'" + text if text.startswith(("=", "+", "-", "@")) else text

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversa"
    sheet.append(["Conversa", cell_text(body.title)])
    sheet.append(["Autor", "Data e hora", "Mensagem"])
    for cell in sheet[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4F46E5")
    for message in body.messages:
        sheet.append([
            "Júlia" if message.role == "assistant" else "Você",
            cell_text(message.created_at),
            cell_text(message.text),
        ])
    sheet.freeze_panes = "A3"
    sheet.auto_filter.ref = f"A2:C{sheet.max_row}"
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 25
    sheet.column_dimensions["C"].width = 80
    for row in sheet.iter_rows(min_row=3, min_col=3, max_col=3):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    output = BytesIO()
    workbook.save(output)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="conversa.xlsx"'},
    )


@router.post("/api/sync")
async def sync_messages(request: Request, body: SyncBody):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "sync", "owner": dono,
                                   "messages": [m.model_dump() for m in body.messages]})
    if result.get("type") == "op_error":
        raise erro_relay(result, "Confirmação do PC não recebida")
    if result.get("type") != "ack":
        raise HTTPException(503, "Confirmação do PC não recebida")
    confirmed = set(result.get("confirmed_ids", []))
    submitted = {m.id for m in body.messages}
    return {"confirmed_ids": sorted(confirmed & submitted)}


@router.get("/api/messages")
async def messages(request: Request, conversation_id: str = "", cursor: str = ""):
    verify_session(request)
    dono = await revogacao_ok(request)
    before = None
    if cursor:
        try:
            if len(cursor) > 400:
                raise ValueError()
            before = json.loads(base64.urlsafe_b64decode(cursor).decode())
            if not (isinstance(before, list) and len(before) == 2 and
                    all(isinstance(v, str) for v in before) and len(before[0]) <= 48 and len(before[1]) <= 100):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise HTTPException(422, "Cursor inválido") from None
    result = await relay.exchange({"type": "list", "owner": dono, "limit": 200,
                                   "conversation_id": conversation_id, "before": before})
    if result.get("type") != "history":
        raise HTTPException(503, "Histórico não disponível")
    msgs = result.get("messages", [])[:200]
    if conversation_id:
        msgs = [m for m in msgs if m.get("conversation_id") == conversation_id]
    next_cursor = ""
    if len(msgs) == 200:
        first = msgs[0]
        next_cursor = base64.urlsafe_b64encode(json.dumps(
            [first["created_at"], first["id"]]).encode()).decode()
    return {"messages": msgs, "next_cursor": next_cursor}


@router.post("/api/workspace/sync")
async def workspace_sync(request: Request, body: WorkspaceBatch):
    require_csrf(request)
    owner = await revogacao_ok(request)
    result = await relay.exchange({"type": "workspace_sync", "owner": owner,
                                   "records": [r.model_dump() for r in body.records]}, timeout=20.0)
    if result.get("type") == "op_error":
        raise erro_relay(result, "Não foi possível sincronizar os projetos")
    if result.get("type") != "workspace_synced":
        raise HTTPException(503, "O PC não confirmou a organização dos chats")
    return {"records": result.get("records", [])}


@router.get("/api/conversations")
async def conversations(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "conversations", "owner": dono,
                                   "limit": 100}, timeout=20.0)
    if result.get("type") != "conversations":
        raise HTTPException(503, "Sessões indisponíveis")
    return {"conversations": result.get("conversations", [])[:100]}

class UiStateItem(BaseModel):
    k: str = Field(min_length=3, max_length=200, pattern=r"^[\w#:.\-]{3,200}$")
    message_id: str = Field(min_length=8, max_length=100)
    slot: str = Field(min_length=1, max_length=40)
    state: dict = Field(default_factory=dict)
    updated_at: str = Field(min_length=10, max_length=48)

    @field_validator("updated_at")
    @classmethod
    def timestamp(cls, value):
        return WorkspaceRecord.timestamp(value)


class UiStateBody(BaseModel):
    states: list[UiStateItem] = Field(min_length=1, max_length=300)


@router.post("/api/ui-state")
async def ui_state_save(request: Request, body: UiStateBody):
    """Persiste estados de interfaces JDUI no SQLite do PC (idempotente por k)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    import json as _json
    itens = []
    for s in body.states:
        try:
            bruto = _json.dumps(s.state, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        if len(bruto) > 8000:
            continue
        itens.append({"k": s.k, "message_id": s.message_id, "slot": s.slot,
                      "state": bruto, "updated_at": s.updated_at})
    if not itens:
        raise HTTPException(422, "Nenhum estado válido")
    result = await relay.exchange({"type": "ui_state_save", "owner": dono,
                                   "states": itens}, timeout=20.0)
    if result.get("type") != "ui_state_saved":
        raise HTTPException(503, "PC não confirmou os estados")
    return {"saved": result.get("saved", 0)}


@router.get("/api/ui-state")
async def ui_state_list(request: Request, cursor: str = ""):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "ui_state_list", "owner": dono, "cursor": cursor[:200]},
                                  timeout=20.0)
    if result.get("type") != "ui_state_list":
        raise HTTPException(503, "Estados indisponíveis")
    import json as _json
    out = []
    for r in result.get("states", [])[:500]:
        try:
            out.append({"k": r["k"], "message_id": r.get("message_id", ""),
                        "slot": r.get("slot", ""),
                        "state": _json.loads(r.get("state", "{}")),
                        "updated_at": r.get("updated_at", "")})
        except (ValueError, KeyError, TypeError):
            continue
    return {"states": out, "next_cursor": result.get("next_cursor", "")}


@router.delete("/api/conversations/{conversation_id}")
async def conversation_forget(request: Request, conversation_id: str):
    """Apaga conversa do SQLite do PC (mensagens + pedidos de IA). Tombstone fica no celular."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", conversation_id):
        raise HTTPException(422, "Conversa inválida")
    result = await relay.exchange({"type": "conv_forget", "owner": dono,
                                   "conversation_id": conversation_id}, timeout=20.0)
    if result.get("type") != "conv_forgotten":
        raise HTTPException(503, "PC não confirmou a exclusão")
    return {"ok": True, "deleted": result.get("deleted", 0)}
