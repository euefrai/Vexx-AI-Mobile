"""Router: Recursos públicos: motor 3D pré-comprimido e páginas institucionais."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from relay_core import ROOT

router = APIRouter()

@router.get('/vendor/three-engine.js')
async def three_engine_asset(request: Request):
    # Precompressed at build time: no per-request compression and no SSE buffering.
    accepts_gzip = False
    for entry in request.headers.get('accept-encoding', '').lower().split(','):
        parts = [part.strip() for part in entry.split(';')]
        if parts[0] != 'gzip':
            continue
        quality = next((part[2:] for part in parts[1:] if part.startswith('q=')), '1')
        try:
            accepts_gzip = 0 < float(quality) <= 1
        except ValueError:
            accepts_gzip = False
        break
    base = ROOT / 'public' / 'vendor' / 'three-engine.js'
    compressed = base.with_suffix('.js.gz')
    use_gzip = accepts_gzip and compressed.is_file()
    return FileResponse(compressed if use_gzip else base, media_type='text/javascript',
                        headers={'Vary':'Accept-Encoding', **({'Content-Encoding':'gzip'} if use_gzip else {})})

# ── Transparência e reputação: páginas públicas, sem autenticação ──────
# Rotas limpas (sem .html) para os documentos institucionais. Os mesmos
# arquivos continuam disponíveis em /nome.html via StaticFiles.

def _public_file(name: str, media_type: str):
    path = ROOT / "public" / name
    if not path.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(path, media_type=media_type)


@router.get("/sobre", include_in_schema=False)
def trust_sobre():
    return _public_file("sobre.html", "text/html")


@router.get("/privacidade", include_in_schema=False)
def trust_privacidade():
    return _public_file("privacidade.html", "text/html")


@router.get("/termos", include_in_schema=False)
def trust_termos():
    return _public_file("termos.html", "text/html")


@router.get("/seguranca", include_in_schema=False)
def trust_seguranca():
    return _public_file("seguranca.html", "text/html")


@router.get("/contato", include_in_schema=False)
def trust_contato():
    return _public_file("contato.html", "text/html")


@router.get("/robots.txt", include_in_schema=False)
def trust_robots():
    return _public_file("robots.txt", "text/plain")


@router.get("/sitemap.xml", include_in_schema=False)
def trust_sitemap():
    return _public_file("sitemap.xml", "application/xml")


@router.get("/.well-known/security.txt", include_in_schema=False)
def trust_security_txt():
    return _public_file(".well-known/security.txt", "text/plain")
