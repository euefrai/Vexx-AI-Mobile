"""Router: Acesso remoto ao PC: consentimento, tela, quadros e entrada."""
import base64

from fastapi import APIRouter, HTTPException, Request, Response

from relay_core import _rate_limit, InputBatch, InputBody, relay, require_csrf, revogacao_ok

router = APIRouter()

async def _remote_access_exchange(request: Request, action: str):
    require_csrf(request)
    owner = await revogacao_ok(request)
    _rate_limit(request, 'remote_request' if action == 'remote_request' else 'remote_status', owner)
    result = await relay.exchange({'type': action, 'owner': owner}, timeout=8.0)
    if result.get('type') != 'remote_status':
        code = result.get('codigo')
        raise HTTPException(403 if code == 'sem_permissao' else 429 if code == 'ritmo' else 503,
                            result.get('error', 'Atualize e reinicie o PC Agent para preparar o acesso.'))
    return {key: value for key, value in result.items() if key not in ('type', 'request_id')}


@router.get('/api/remote/status')
async def remote_access_status(request: Request):
    return await _remote_access_exchange(request, 'remote_status')


@router.post('/api/remote/request')
async def remote_access_request(request: Request):
    # No owner/approved/device flag is accepted from the browser.
    return await _remote_access_exchange(request, 'remote_request')


@router.post('/api/remote/revoke')
async def remote_access_revoke(request: Request):
    return await _remote_access_exchange(request, 'remote_revoke')


@router.get("/api/screen")
async def screen(request: Request, max_w: int = 800, q: int = 55):
    """Foto atual da tela do PC (JPEG base64). Exige login + CSRF + grant remoto."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "screen", dono)
    result = await relay.exchange({"type": "screen", "owner": dono,
                                   "max_w": max(320, min(max_w, 1920)),
                                   "q": max(30, min(q, 85))}, timeout=20.0)
    if result.get("type") != "screen":
        if result.get("codigo") == "sem_permissao":
            raise HTTPException(403, result.get("error", "Sem autorização."))
        raise HTTPException(503, result.get("error", "Tela indisponível"))
    return {"imagem": result["imagem"], "largura": result.get("largura", 0),
            "altura": result.get("altura", 0), "ms": result.get("ms", 0),
            "cursor": result.get("cursor"),
            "remote_enabled": result.get("remote_enabled", False)}


@router.get("/api/remote/frame")
async def remote_frame(request: Request, max_w: int = 1280, q: int = 72):
    # Reuse every HTTP/session/grant gate, returning only the transport as JPEG.
    result = await screen(request, max_w, q)
    try:
        raw = base64.b64decode(result['imagem'], validate=True)
    except (ValueError, TypeError):
        raise HTTPException(503, 'Quadro inválido do computador') from None
    if len(raw) > 4_000_000 or not raw.startswith(b'\xff\xd8'):
        raise HTTPException(503, 'Quadro inválido do computador')
    headers = {'Cache-Control':'no-store, private', 'X-Content-Type-Options':'nosniff',
        'X-Frame-Width':str(result['largura']), 'X-Frame-Height':str(result['altura']),
        'X-Remote-Control':'1' if result['remote_enabled'] else '0'}
    cursor = result.get('cursor')
    if isinstance(cursor, dict):
        import math
        x, y = cursor.get('x'), cursor.get('y')
        if all(type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1 for n in (x,y)):
            headers.update({'X-Cursor-X':str(x), 'X-Cursor-Y':str(y)})
    return Response(raw, media_type='image/jpeg', headers=headers)


@router.post("/api/input")
async def remote_input(request: Request, body: InputBody):
    """Executa mouse/teclado no PC. Exige login + CSRF + grant remoto (além de JULIA_REMOTE=1)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    _rate_limit(request, "input", dono)
    result = await relay.exchange({"type": "input", "owner": dono,
                                   "cmd": body.model_dump()}, timeout=15.0)
    if result.get("type") != "input_done":
        if result.get("codigo") == "sem_permissao":
            raise HTTPException(403, result.get("error", "Sem autorização."))
        raise HTTPException(503, result.get("error", "Comando recusado"))
    return {"ok": True, "kind": result.get("kind", "")}


@router.post('/api/input/batch')
async def remote_input_batch(request: Request, body: InputBatch):
    require_csrf(request)
    owner = await revogacao_ok(request)
    for _ in body.commands: _rate_limit(request, 'input', owner)
    if sum(len(c.text) for c in body.commands) > 400 or any(c.kind == 'drag' for c in body.commands):
        raise HTTPException(422, 'Lote excede os limites')
    result = await relay.exchange({'type':'input','owner':owner,
        'cmd':{'kind':'batch','commands':[c.model_dump() for c in body.commands]}}, timeout=15)
    if result.get('type') != 'input_done':
        raise HTTPException(403 if result.get('codigo') == 'sem_permissao' else 503,
                            result.get('error', 'Lote não confirmado; não repita automaticamente.'))
    return {'ok':True,'kind':'batch'}
