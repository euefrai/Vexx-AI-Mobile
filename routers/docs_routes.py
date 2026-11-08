"""Router: Documentos e arquivos: upload, busca, comparação e downloads."""
import base64
import hashlib
import hmac
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from urllib.parse import quote

from relay_core import (
    _rate_limit, DOC_UPLOAD_MAX_BYTES, relay, require_csrf, revogacao_ok, verify_session,
)

router = APIRouter()

class DocAsk(BaseModel):
    doc_id: str = Field(min_length=4, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class DocSearch(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    doc_id: str = Field(default="", max_length=64, pattern=r"^(|[a-zA-Z0-9_-]+)$")
    limit: int = Field(default=5, ge=1, le=20)


class DocCompare(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    doc_ids: list[str] = Field(min_length=1, max_length=20)


@router.post("/api/docs/upload")
async def docs_upload(request: Request, file: UploadFile = File(...),
                      conversation_id: str = Form(default="geral", max_length=100)):
    """Recebe um documento (até 15MB) e encaminha ao PC para leitura."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "docs", dono)
    limite = DOC_UPLOAD_MAX_BYTES
    recebido = bytearray()
    try:
        while len(recebido) <= limite:
            parte = await file.read(min(64 * 1024, limite - len(recebido) + 1))
            if not parte:
                break
            recebido.extend(parte)
        if len(recebido) > limite:
            raise HTTPException(413, "Arquivo grande demais (limite 15MB)")
    finally:
        await file.close()
    raw = bytes(recebido)
    if not raw:
        raise HTTPException(422, "Arquivo vazio")
    import base64 as _b64
    conv = conversation_id if 3 <= len(conversation_id) <= 100 else "geral"
    result = await relay.exchange(
        {"type": "doc_upload", "owner": dono,
         "name": (file.filename or "arquivo")[:120],
         "conversation_id": conv,
         "data_b64": _b64.b64encode(raw).decode("ascii")}, timeout=90.0)
    if result.get("type") == "doc_error":
        raise HTTPException(422, result.get("error", "Não consegui ler o arquivo"))
    if result.get("type") != "doc_uploaded":
        raise HTTPException(503, "PC não processou o documento")
    return {k: result.get(k) for k in (
        "doc_id", "name", "title", "ext", "chars", "chunks", "paginas_aprox",
        "sections", "table_hints", "content_hash", "version")}


@router.get("/api/docs")
async def docs_list(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_list", "owner": dono,
                                   "limit": 50}, timeout=20.0)
    if result.get("type") != "doc_list":
        raise HTTPException(503, "Documentos indisponíveis")
    return {"documents": result.get("documents", [])[:50]}


@router.post("/api/docs/search")
async def docs_search(request: Request, body: DocSearch):
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "docs", dono)
    result = await relay.exchange({"type": "doc_search", "owner": dono,
                                   "query": body.query, "doc_id": body.doc_id,
                                   "limit": body.limit}, timeout=30.0)
    if result.get("type") == "doc_error":
        raise HTTPException(404 if result.get("codigo") == "nao_encontrado" else 422,
                            result.get("error", "Falha na busca documental"))
    if result.get("type") != "doc_search":
        raise HTTPException(503, "Busca documental indisponível")
    return {"results": result.get("results", [])}


@router.post("/api/docs/compare")
async def docs_compare(request: Request, body: DocCompare):
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "docs", dono)
    result = await relay.exchange({"type": "doc_compare", "owner": dono,
                                   "query": body.query, "doc_ids": body.doc_ids}, timeout=30.0)
    if result.get("type") == "doc_error":
        raise HTTPException(422, result.get("error", "Falha ao comparar documentos"))
    if result.get("type") != "doc_compare":
        raise HTTPException(503, "Comparação documental indisponível")
    return {k: v for k, v in result.items() if k != "type"}


@router.delete("/api/docs/{doc_id}")
async def docs_delete(request: Request, doc_id: str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{4,64}", doc_id):
        raise HTTPException(422, "Identificador de documento inválido")
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "doc_delete", "owner": dono,
                                   "doc_id": doc_id}, timeout=30.0)
    if result.get("type") == "doc_error":
        raise HTTPException(404, result.get("error", "Documento não encontrado"))
    if result.get("type") != "doc_deleted":
        raise HTTPException(503, "Exclusão documental indisponível")
    return {"ok": True, "doc_id": doc_id}


@router.post("/api/docs/resumo")
async def docs_resumo(request: Request, body: DocAsk):
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "docs", dono)
    result = await relay.exchange({"type": "doc_resumo", "owner": dono,
                                   "doc_id": body.doc_id}, timeout=180.0)
    if result.get("type") == "doc_error":
        raise HTTPException(503, result.get("error", "Falha ao resumir"))
    if result.get("type") != "doc_resumo":
        raise HTTPException(503, "Resumo não recebido")
    return {"doc_id": result.get("doc_id"), "resumo": result.get("resumo", "")}


@router.post("/api/docs/topicos")
async def docs_topicos(request: Request, body: DocAsk):
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "docs", dono)
    result = await relay.exchange({"type": "doc_topicos", "owner": dono,
                                   "doc_id": body.doc_id}, timeout=180.0)
    if result.get("type") == "doc_error":
        raise HTTPException(503, result.get("error", "Falha ao extrair tópicos"))
    if result.get("type") != "doc_topicos":
        raise HTTPException(503, "Tópicos não recebidos")
    return {"doc_id": result.get("doc_id"), "topicos": result.get("topicos", "")}


@router.get("/api/files")
async def files_list(request: Request):
    """Lista os arquivos gerados pelo Vexx AI no PC do dono autenticado."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "file_list", "owner": dono,
                                   "limit": 50}, timeout=20.0)
    if result.get("type") != "file_list":
        raise HTTPException(503, "Arquivos gerados indisponíveis")
    return {"files": result.get("files", [])[:50]}


@router.get("/api/files/{file_id}/download")
async def files_download(request: Request, file_id: str):
    """Baixa um arquivo gerado; os bytes vêm do PC via relay."""
    verify_session(request)
    dono = await revogacao_ok(request)
    if request.url.query:
        raise HTTPException(422, "Parâmetros extras não são permitidos")
    if not re.fullmatch(r"file-[a-f0-9]{12}", file_id or ""):
        raise HTTPException(422, "Identificador de arquivo inválido")
    result = await relay.exchange({"type": "file_download", "owner": dono,
                                   "file_id": file_id}, timeout=60.0)
    if result.get("type") == "file_error":
        codigo = result.get("codigo")
        raise HTTPException(404 if codigo == "nao_encontrado" else 422,
                            result.get("error", "Arquivo não encontrado"))
    if result.get("type") != "file_download":
        raise HTTPException(503, "Arquivo gerado indisponível")
    data_b64 = result.get("data_b64")
    if not isinstance(data_b64, str) or len(data_b64) > 8 * 1024 * 1024:
        raise HTTPException(503, "Arquivo gerado inválido")
    try:
        payload = base64.b64decode(data_b64, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(503, "Arquivo gerado inválido") from None
    sha = str(result.get("sha256") or "")
    if sha and len(sha) == 64 and not hmac.compare_digest(
            sha, hashlib.sha256(payload).hexdigest()):
        raise HTTPException(503, "Arquivo gerado corrompido")
    filename = re.sub(r"[\r\n\"\\/]", "_", str(result.get("name") or "arquivo"))[:120] or "arquivo"
    ascii_name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)[:120] or "arquivo"
    media_type = str(result.get("mime") or "application/octet-stream")[:100]
    if not re.fullmatch(r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+(?:;\s*charset=[A-Za-z0-9._-]+)?",
                        media_type):
        media_type = "application/octet-stream"
    return Response(payload, media_type=media_type, headers={
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(filename, safe='')}"),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.delete("/api/files/{file_id}")
async def files_delete(request: Request, file_id: str):
    if not re.fullmatch(r"file-[a-f0-9]{12}", file_id or ""):
        raise HTTPException(422, "Identificador de arquivo inválido")
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "file_delete", "owner": dono,
                                   "file_id": file_id}, timeout=20.0)
    if result.get("type") == "file_error":
        raise HTTPException(404, result.get("error", "Arquivo não encontrado"))
    if result.get("type") != "file_deleted":
        raise HTTPException(503, "Exclusão de arquivo indisponível")
    return {"ok": True, "file_id": file_id}
