"""Arquivos gerados pelo Vexx AI no PC.

O modelo entrega o conteúdo em um bloco ``<JULIAFILE name="...">``. Este
módulo valida o nome, grava uma nova versão no workspace do dono e devolve
metadados para o ``filecard`` do JDUI. Nada é gravado fora de
``JULIA_FILES_PATH`` (padrão ``~/.JULIA-mobile/files``).

O conteúdo é texto/código por padrão. ``encoding="base64"`` permite que o
modelo entregue bytes de um formato binário sem inventar caminhos no PC.
"""
import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("JULIA-files")

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_BLOCKS = 8
MAX_NAME_CHARS = 180
DONO_PADRAO = "local"
FILE_ID_RE = re.compile(r"^file-[a-f0-9]{12}$")

_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".tex", ".bib",
    ".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xml", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".properties", ".env",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".svg",
}
_CODE_EXTS = {
    ".py", ".pyw", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue",
    ".svelte", ".astro", ".java", ".kt", ".kts", ".scala", ".groovy",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".cs", ".go", ".rs",
    ".rb", ".php", ".swift", ".m", ".mm", ".lua", ".r", ".dart",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd", ".sql",
    ".pl", ".pm", ".ex", ".exs", ".erl", ".hrl", ".clj", ".cljs",
    ".gradle", ".mk", ".cmake", ".dockerfile",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff"}


class FileErro(ValueError):
    def __init__(self, mensagem, codigo="erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def files_dir() -> Path:
    base = os.environ.get("JULIA_FILES_PATH", "")
    return Path(base) if base else (Path.home() / ".JULIA-mobile" / "files")


def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS generated_files (
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL DEFAULT 'local',
        conversation_id TEXT NOT NULL,
        name TEXT NOT NULL,
        root_name TEXT NOT NULL,
        ext TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'other',
        size INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        disk_path TEXT NOT NULL,
        source_doc_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_generated_files_owner
                  ON generated_files(owner_id, conversation_id, created_at)""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_generated_files_name
                  ON generated_files(owner_id, conversation_id, name, version)""")
    db.commit()


def _owner_key(owner: str) -> str:
    return hashlib.sha256(str(owner or DONO_PADRAO).encode("utf-8")).hexdigest()[:20]


def _safe_name(nome: str):
    raw = str(nome or "").strip().replace("\\", "/")
    raw = re.sub(r"[\x00-\x1f\x7f]", "", raw)
    if not raw:
        raise FileErro("Nome de arquivo vazio.", "nome")
    if raw.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", raw):
        raise FileErro("Use um nome relativo, sem caminho absoluto.", "nome")
    parts = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise FileErro("O nome do arquivo não pode conter '..'.", "nome")
        part = re.sub(r'[<>:"|?*]', "_", part).strip().rstrip(". ")
        if not part:
            continue
        if len(part) > 120:
            stem, dot, suffix = part.rpartition(".")
            if dot and len(suffix) <= 12:
                part = (stem[:110] + "." + suffix)[:120]
            else:
                part = part[:120]
        parts.append(part)
    if not parts or len(parts) > 6:
        raise FileErro("Nome de arquivo inválido.", "nome")
    name = "/".join(parts)
    if len(name) > MAX_NAME_CHARS:
        raise FileErro("Nome de arquivo muito longo.", "nome")
    root = parts[-1]
    ext = ""
    match = re.search(r"(\.[A-Za-z0-9]{1,12})$", root)
    if match and not (root.startswith(".") and root.count(".") == 1):
        ext = match.group(1).lower()
    return name, root, ext


def _kind(name: str, ext: str) -> str:
    ext = (ext or "").lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in (".pdf", ".docx", ".xlsx", ".csv", ".md", ".txt", ".json", ".zip"):
        return ext[1:]
    if ext in (".html", ".htm"):
        return "html"
    if ext in (".xml", ".svg"):
        return "xml"
    if ext in (".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties", ".env"):
        return "yaml"
    if ext in _CODE_EXTS:
        return "code"
    if ext in _TEXT_EXTS or ext == "":
        base = name.lower().rsplit("/", 1)[-1]
        if base in ("dockerfile", "makefile", "procfile", "gemfile", "rakefile") or ext in _TEXT_EXTS:
            return "code" if base in ("dockerfile", "makefile") else "txt"
        return "other"
    return "other"


def _size_label(n: int) -> str:
    n = max(0, int(n))
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f}".replace(".", ",") + " MB"
    if n >= 1024:
        return str(round(n / 1024)) + " KB"
    return str(n) + " B"


def _mime(name: str) -> str:
    mime, _ = mimetypes.guess_type(name)
    if mime:
        return mime
    if _kind(name, "".join(Path(name).suffixes[-1:])).lower() in ("code", "txt", "md", "json", "csv", "html", "xml", "yaml"):
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def _meta(row, *, include_size_label=True) -> dict:
    (file_id, owner, conv, name, root, ext, kind, size, digest, version,
     disk_path, source_doc_id, created_at) = row
    meta = {
        "file_id": file_id,
        "id": file_id,
        "owner_id": owner,
        "conversation_id": conv,
        "name": name,
        "root_name": root,
        "ext": ext,
        "kind": kind,
        "size": int(size),
        "sha256": digest,
        "version": int(version),
        "source_doc_id": source_doc_id or "",
        "created_at": created_at,
        "download_url": f"/api/files/{file_id}/download",
        "mime": _mime(name),
    }
    if include_size_label:
        meta["size_label"] = _size_label(size)
    return meta


def salvar_arquivo(db, nome: str, conteudo, conversation_id: str,
                   owner=DONO_PADRAO, source_doc_id: str = "",
                   *, binario: bool = False) -> dict:
    owner = (str(owner or "").strip().lower() or DONO_PADRAO)[:40]
    conversation_id = str(conversation_id or "geral")[:100] or "geral"
    if isinstance(conteudo, str):
        data = conteudo.encode("utf-8")
    elif isinstance(conteudo, (bytes, bytearray)):
        data = bytes(conteudo)
    else:
        raise FileErro("Conteúdo do arquivo inválido.", "conteudo")
    if len(data) > MAX_FILE_BYTES:
        raise FileErro("Arquivo gerado grande demais (limite 4MB).", "grande")
    if not binario and b"\x00" in data:
        raise FileErro("O conteúdo textual contém bytes nulos.", "conteudo")
    name, root, ext = _safe_name(nome)
    with db:
        row = db.execute(
            """SELECT COALESCE(MAX(version), 0) FROM generated_files
               WHERE owner_id=? AND conversation_id=? AND name=?""",
            (owner, conversation_id, name)).fetchone()
    version = int(row[0] or 0) + 1
    file_id = "file-" + uuid.uuid4().hex[:12]
    base = (files_dir() / _owner_key(owner)).resolve()
    parts = name.split("/")
    dest = base.joinpath(*parts[:-1], f"{file_id}__{parts[-1]}").resolve()
    try:
        if base not in dest.parents and dest.parent != base:
            raise FileErro("Caminho de arquivo inválido.", "nome")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + f".{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    except FileErro:
        raise
    except OSError as exc:
        raise FileErro("Não consegui gravar o arquivo no PC.", "io") from exc
    digest = hashlib.sha256(data).hexdigest()
    created_at = agora_iso()
    kind = _kind(name, ext)
    try:
        with db:
            db.execute(
                """INSERT INTO generated_files
                   (id, owner_id, conversation_id, name, root_name, ext, kind,
                    size, sha256, version, disk_path, source_doc_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (file_id, owner, conversation_id, name, root, ext, kind,
                 len(data), digest, version, str(dest), str(source_doc_id or ""),
                 created_at))
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    log.info("arquivo gerado %s (%s v%d, %d bytes)", file_id, name, version, len(data))
    return _meta((file_id, owner, conversation_id, name, root, ext, kind, len(data),
                  digest, version, str(dest), str(source_doc_id or ""), created_at))


def listar_arquivos(db, limite: int = 50, owner=DONO_PADRAO,
                    conversation_id=None) -> list:
    owner = (str(owner or "").strip().lower() or DONO_PADRAO)[:40]
    scope = " AND conversation_id=?" if conversation_id is not None else ""
    params = [owner] + ([str(conversation_id)[:100]] if conversation_id is not None else [])
    rows = db.execute(
        """SELECT id, owner_id, conversation_id, name, root_name, ext, kind,
                  size, sha256, version, disk_path, source_doc_id, created_at
           FROM generated_files WHERE owner_id=?""" + scope +
        " ORDER BY created_at DESC LIMIT ?",
        (*params, min(max(int(limite), 1), 200))).fetchall()
    return [_meta(row) for row in rows]


def _row_arquivo(db, file_id: str, owner: str):
    if not FILE_ID_RE.fullmatch(str(file_id or "")):
        return None
    return db.execute(
        """SELECT id, owner_id, conversation_id, name, root_name, ext, kind,
                  size, sha256, version, disk_path, source_doc_id, created_at
           FROM generated_files WHERE id=? AND owner_id=?""",
        (file_id, owner)).fetchone()


def obter_arquivo(db, file_id: str, owner=DONO_PADRAO):
    owner = (str(owner or "").strip().lower() or DONO_PADRAO)[:40]
    row = _row_arquivo(db, file_id, owner)
    if not row:
        raise FileErro("Arquivo não encontrado.", "nao_encontrado")
    meta = _meta(row)
    path = Path(row[10])
    base = (files_dir() / _owner_key(owner)).resolve()
    try:
        path = path.resolve()
        if base not in path.parents and path.parent != base:
            raise FileErro("Caminho de arquivo inválido.", "nao_encontrado")
        data = path.read_bytes()
    except FileErro:
        raise
    except OSError:
        raise FileErro("Arquivo não encontrado no disco.", "nao_encontrado") from None
    if len(data) != int(row[7]):
        raise FileErro("Arquivo corrompido no disco.", "corrompido")
    meta["data_b64"] = base64.b64encode(data).decode("ascii")
    return meta


def excluir_arquivo(db, file_id: str, owner=DONO_PADRAO) -> bool:
    owner = (str(owner or "").strip().lower() or DONO_PADRAO)[:40]
    row = _row_arquivo(db, file_id, owner)
    if not row:
        return False
    path = Path(row[10])
    with db:
        db.execute("DELETE FROM generated_files WHERE id=? AND owner_id=?", (file_id, owner))
    base = (files_dir() / _owner_key(owner)).resolve()
    try:
        path = path.resolve()
        if base in path.parents or path.parent == base:
            path.unlink(missing_ok=True)
    except OSError:
        log.warning("não consegui remover o arquivo gerado %s", file_id)
    return True


# ── Protocolo de criação ─────────────────────────────────────────────
TAG_RE = re.compile(
    r"(?is)<JULIAFILE\b([^>\n]{0,500})>\s*\n?(.*?)\n?\s*</JULIAFILE\s*>")
FENCE_RE = re.compile(
    r"(?ms)^[ \t]*(`{3,}|~{3,})[ \t]*juliafile\b([^\n]*)\n(.*?)^[ \t]*\1[ \t]*$")
_BLOCK_HINT_RE = re.compile(r"(?is)(<JULIAFILE\b|```[ \t]*juliafile\b|~~~[ \t]*juliafile\b)")


def _attrs(raw: str) -> dict:
    out = {}
    for key in ("name", "nome", "encoding", "codificacao", "codificação"):
        match = re.search(
            r"\b" + re.escape(key) + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
            raw or "", re.I)
        if match:
            out[key] = (match.group(1) or match.group(2) or match.group(3) or "").strip()
    if "name" not in out and "nome" in out:
        out["name"] = out["nome"]
    if "encoding" not in out and "codificacao" in out:
        out["encoding"] = out["codificacao"]
    if "encoding" not in out and "codificação" in out:
        out["encoding"] = out["codificação"]
    return out


def possui_bloco(texto: str) -> bool:
    return bool(_BLOCK_HINT_RE.search(texto or ""))


def remover_blocos(texto: str) -> str:
    limpo = TAG_RE.sub("", texto or "")
    limpo = FENCE_RE.sub("", limpo)
    return re.sub(r"\n{3,}", "\n\n", limpo).strip()


def extrair_blocos(texto: str) -> list:
    matches = []
    for match in TAG_RE.finditer(texto or ""):
        matches.append((match.start(), match.end(), match.group(1), match.group(2)))
    for match in FENCE_RE.finditer(texto or ""):
        overlap = any(not (match.end() <= start or match.start() >= end)
                      for start, end, _, _ in matches)
        if not overlap:
            matches.append((match.start(), match.end(), match.group(2), match.group(3)))
    matches.sort(key=lambda item: item[0])
    return matches


def _conteudo_bloco(corpo: str, attrs: dict):
    encoding = str(attrs.get("encoding") or "").strip().lower()
    if encoding in ("base64", "b64"):
        compact = re.sub(r"\s+", "", corpo or "")
        try:
            return base64.b64decode(compact, validate=True), True
        except (ValueError, TypeError):
            raise FileErro("Conteúdo base64 inválido no bloco de arquivo.", "base64") from None
    return (corpo or "").encode("utf-8"), False


def processar_texto(db, texto: str, conversation_id: str, owner=DONO_PADRAO,
                    source_doc_id: str = "") -> dict:
    """Extrai blocos, grava os arquivos e devolve texto limpo + metadados."""
    matches = extrair_blocos(texto or "")
    if not matches:
        return {"texto": texto or "", "arquivos": [], "erros": []}
    pedacos, arquivos, erros = [], [], []
    pos = 0
    for start, end, raw_attrs, corpo in matches:
        pedacos.append((texto or "")[pos:start])
        pos = end
        if len(arquivos) >= MAX_BLOCKS:
            erros.append("limite de 8 arquivos por resposta")
            continue
        attrs = _attrs(raw_attrs)
        nome = attrs.get("name", "")
        if not nome:
            erros.append("bloco sem atributo name")
            continue
        try:
            data, binario = _conteudo_bloco(corpo, attrs)
            arquivos.append(salvar_arquivo(
                db, nome, data, conversation_id, owner, source_doc_id,
                binario=binario))
        except FileErro as exc:
            erros.append(f"{nome}: {exc}")
        except Exception as exc:
            log.warning("falha ao salvar arquivo gerado: %s", exc)
            erros.append(f"{nome}: falha ao salvar")
    pedacos.append((texto or "")[pos:])
    limpo = re.sub(r"\n{3,}", "\n\n", "".join(pedacos)).strip()
    return {"texto": limpo, "arquivos": arquivos, "erros": erros}


def filecard_fence(arquivos: list, titulo: str = "Arquivo criado") -> str:
    files = []
    for meta in (arquivos or [])[:MAX_BLOCKS]:
        files.append({
            "name": meta.get("name", "arquivo"),
            "url": meta.get("download_url", ""),
            "kind": meta.get("kind", "other"),
            "size": meta.get("size_label", ""),
            "source": "gerado pelo Vexx AI",
            "status": "generated",
        })
    if not files:
        return ""
    payload = {
        "version": "JULIA-ui-message/v1",
        "blocks": [{
            "type": "ui",
            "component": "filecard",
            "props": {"title": titulo, "files": files},
        }],
    }
    return "\n\n```jdui\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
