"""Documentos no PC: upload, leitura, resumo, tópicos e Q&A sobre o conteúdo.

Formatos lidos: PDF, DOCX, TXT/Markdown, CSV/TSV, XLSX, HTML.
Outros (PPTX, ODT, EPUB…) retornam erro amigável pedindo conversão para PDF.

Tudo com imports opcionais: se a lib extratora não estiver instalada no PC,
o erro diz exatamente qual `pip install` fazer — nada quebra o agente.
"""
import csv
import io
import logging
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("fajulto-docs")

MAX_BYTES = 15 * 1024 * 1024
MAX_TEXTO_DOC = 200_000
TAM_CHUNK = 3000
OVERLAP = 300
STOP = frozenset(("que com uma para das dos por seu sua isto isso entre como mas foi ser tem são foi ela ele eles elas meu minha teu tua seu sua nosso nossa este esta esse essa aquele aquela muito mais menos sobre após depois onde quando qual quais todo toda todos todas também pode fazer faz parte vez vezes".split()))

EXT_OK = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".tsv",
          ".xlsx", ".html", ".htm"}


class DocErro(ValueError):
    def __init__(self, mensagem, codigo="erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def docs_dir() -> Path:
    base = os.environ.get("fajulto_DOCS_PATH", "")
    return Path(base) if base else (Path.home() / ".fajulto-mobile" / "docs")


DONO_PADRAO = "local"


def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, ext TEXT NOT NULL,
        size INTEGER NOT NULL, chars INTEGER NOT NULL, chunks INTEGER NOT NULL,
        summary TEXT, topics TEXT, conversation_id TEXT NOT NULL,
        created_at TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'local'
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS doc_chunks (
        doc_id TEXT NOT NULL, idx INTEGER NOT NULL, text TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local',
        PRIMARY KEY (doc_id, idx)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_docs_conv ON documents(conversation_id, created_at)")
    db.commit()


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-zà-ú0-9]{3,}", (s or "").lower()) if t not in STOP}


# ── Extração ──────────────────────────────────────────────────────────
def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("utf-8", "ignore")


def _extrair_pdf(raw: bytes) -> str:
    partes = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        for i, pg in enumerate(reader.pages[:200]):
            try:
                t = (pg.extract_text() or "").strip()
            except Exception:
                t = ""
            if t:
                partes.append(f"\n── página {i + 1} ──\n{t}")
        if partes:
            return "\n".join(partes)
    except ImportError:
        pass
    except Exception as exc:
        log.warning("pypdf falhou (%s), tentando pypdfium2", exc)
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(io.BytesIO(raw))
        for i in range(min(len(doc), 200)):
            try:
                t = (doc[i].get_textpage().get_text_range() or "").strip()
            except Exception:
                t = ""
            if t:
                partes.append(f"\n── página {i + 1} ──\n{t}")
        if partes:
            return "\n".join(partes)
    except ImportError:
        pass
    if partes:
        return "\n".join(partes)
    raise DocErro("Não consegui ler este PDF (pode ser só imagem escaneada). "
                  "Falta instalar? `pip install pypdf pypdfium2`.", "pdf_ilegivel")


def _extrair_docx(raw: bytes) -> str:
    try:
        import docx
    except ImportError:
        raise DocErro("Para DOCX instale: `pip install python-docx`.", "sem_lib") from None
    try:
        doc = docx.Document(io.BytesIO(raw))
    except Exception:
        # tenta via zip (docx corrompido leve)
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
            txt = re.sub(r"<[^>]+>", " ", xml)
            return re.sub(r"\s+", " ", txt).strip()[:MAX_TEXTO_DOC]
        except Exception:
            raise DocErro("DOCX inválido ou corrompido.", "invalido") from None
    blocos = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    for tb in doc.tables:
        for row in tb.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                blocos.append(" | ".join(cells))
    texto = "\n".join(blocos).strip()
    if not texto:
        raise DocErro("DOCX sem texto legível.", "vazio")
    return texto


def _extrair_xlsx(raw: bytes, nome: str) -> str:
    try:
        import openpyxl
    except ImportError:
        raise DocErro("Para planilhas instale: `pip install openpyxl pandas`.", "sem_lib") from None
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        raise DocErro("Planilha inválida ou corrompida.", "invalido") from None
    out = []
    for ws in wb.worksheets[:10]:
        out.append(f"\n## {ws.title}\n")
        n = 0
        for row in ws.iter_rows(values_only=True):
            vals = [(str(v).strip() if v is not None else "") for v in list(row)[:20]]
            if any(vals):
                out.append(" | ".join(vals))
                n += 1
                if n >= 200:
                    out.append("… (linhas restantes omitidas)")
                    break
    texto = "\n".join(out).strip()
    if not texto:
        raise DocErro("Planilha sem dados legíveis.", "vazio")
    return texto


def _extrair_csv(raw: bytes, delim: str = ",") -> str:
    texto = _decode(raw)
    try:
        linhas = list(csv.reader(io.StringIO(texto), delimiter=delim))[:201]
    except Exception:
        raise DocErro("CSV inválido.", "invalido") from None
    if not linhas:
        raise DocErro("CSV vazio.", "vazio")
    out = [" | ".join(c.strip() for c in r[:20]) for r in linhas if any((c or "").strip() for c in r)]
    if len(linhas) == 201:
        out.append("… (linhas restantes omitidas)")
    return "\n".join(out)


def _extrair_html(raw: bytes) -> str:
    texto = _decode(raw)
    try:
        from bs4 import BeautifulSoup
        sopa = BeautifulSoup(texto, "html.parser")
        for tag in sopa(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return re.sub(r"\n{3,}", "\n\n", sopa.get_text("\n", strip=True))
    except ImportError:
        txt = re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", texto)
        import html as ihtml
        return re.sub(r"\s+", " ", ihtml.unescape(txt)).strip()


def extrair_texto(ext: str, raw: bytes, nome: str) -> str:
    if ext == ".pdf":
        texto = _extrair_pdf(raw)
    elif ext == ".docx":
        texto = _extrair_docx(raw)
    elif ext in (".xlsx",):
        texto = _extrair_xlsx(raw, nome)
    elif ext == ".xls":
        raise DocErro("Converta .xls para .xlsx ou .csv e envie de novo.", "formato_antigo")
    elif ext in (".csv", ".tsv"):
        texto = _extrair_csv(raw, "\t" if ext == ".tsv" else ",")
    elif ext in (".html", ".htm"):
        texto = _extrair_html(raw)
    elif ext in (".txt", ".md", ".markdown"):
        texto = _decode(raw).strip()
        if not texto:
            raise DocErro("Arquivo de texto vazio.", "vazio")
    elif ext in (".pptx", ".ppt", ".odt", ".ods", ".epub"):
        raise DocErro(f"{ext} ainda não é lido. Converta para PDF e envie de novo.", "nao_suportado")
    else:
        raise DocErro(f"Tipo {ext or '?'} não suportado. Envie PDF, DOCX, TXT, CSV, XLSX ou HTML.", "nao_suportado")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if len(texto) < 10:
        raise DocErro("Não encontrei texto legível neste arquivo.", "vazio")
    return texto[:MAX_TEXTO_DOC]


def dividir_chunks(texto: str) -> list:
    partes, i, n = [], 0, len(texto)
    while i < n:
        partes.append(texto[i:i + TAM_CHUNK])
        if i + TAM_CHUNK >= n:
            break
        i += TAM_CHUNK - OVERLAP
    return partes


# ── Persistência ──────────────────────────────────────────────────────
def salvar_documento(db, nome: str, raw: bytes, conversation_id: str, owner=DONO_PADRAO) -> dict:
    import uuid
    owner = (str(owner or "").strip().lower() or DONO_PADRAO)[:40]
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise DocErro("Arquivo vazio.", "vazio")
    if len(raw) > MAX_BYTES:
        raise DocErro(f"Arquivo grande demais ({len(raw) // 1048576}MB; limite 15MB).", "grande")
    base = re.sub(r'[\\/:*?"<>|]', "_", (nome or "arquivo").strip())[:120] or "arquivo"
    ext = ("." + base.rsplit(".", 1)[1].lower()) if "." in base else ""
    if ext not in EXT_OK:
        raise DocErro(f"Tipo {ext or '?'} não suportado. Envie PDF, DOCX, TXT, CSV, XLSX ou HTML.", "nao_suportado")
    texto = extrair_texto(ext, bytes(raw), base)
    doc_id = "doc-" + uuid.uuid4().hex[:12]
    chunks = dividir_chunks(texto)
    with db:
        db.execute("""INSERT INTO documents
            (id, name, ext, size, chars, chunks, conversation_id, created_at, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, base, ext, len(raw), len(texto), len(chunks), conversation_id, agora_iso(), owner))
        for idx, ch in enumerate(chunks):
            db.execute("INSERT INTO doc_chunks (doc_id, idx, text, owner_id) VALUES (?, ?, ?, ?)",
                       (doc_id, idx, ch, owner))
    try:
        pasta = docs_dir()
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / (doc_id + ext)).write_bytes(bytes(raw))
    except OSError:
        pass
    log.info("documento %s (%s, %d chars, %d chunks)", doc_id, base, len(texto), len(chunks))
    return {"doc_id": doc_id, "name": base, "ext": ext, "chars": len(texto),
            "chunks": len(chunks), "paginas_aprox": max(1, len(texto) // 3000)}


def listar_documentos(db, limite: int = 50, owner=DONO_PADRAO) -> list:
    rows = db.execute("""SELECT id, name, ext, size, chars, chunks,
                                summary IS NOT NULL, conversation_id, created_at
                         FROM documents WHERE owner_id=? ORDER BY created_at DESC LIMIT ?""",
                      (owner, min(max(int(limite), 1), 200))).fetchall()
    return [{"doc_id": i, "name": n, "ext": e, "size": s, "chars": c,
             "chunks": k, "tem_resumo": bool(r), "conversation_id": cv,
             "created_at": ca} for i, n, e, s, c, k, r, cv, ca in rows]


def obter_texto(db, doc_id: str, limite: int = 60000, owner=DONO_PADRAO) -> str:
    rows = db.execute("SELECT text FROM doc_chunks WHERE doc_id=? AND owner_id=? ORDER BY idx",
                      (doc_id, owner)).fetchall()
    return "".join(t for (t,) in rows)[:limite]


def trechos_relevantes(db, pergunta: str, doc_id: str = "", k: int = 4, owner=DONO_PADRAO) -> list:
    """Recupera os chunks com maior sobreposição de palavras com a pergunta."""
    toks_q = _tokens(pergunta)
    if not toks_q:
        return []
    if doc_id:
        rows = db.execute("SELECT doc_id, idx, text FROM doc_chunks WHERE doc_id=? AND owner_id=?",
                          (doc_id, owner)).fetchall()
    else:
        rows = db.execute("SELECT doc_id, idx, text FROM doc_chunks WHERE owner_id=?", (owner,)).fetchall()
    nomes = {r[0]: r[1] for r in db.execute("SELECT id, name FROM documents WHERE owner_id=?", (owner,)).fetchall()}
    scored = []
    for did, idx, txt in rows:
        toks = _tokens(txt)
        inter = toks_q & toks
        if inter:
            scored.append((len(inter) / max(1, len(toks_q)) + 0.1 * len(inter) / max(1, len(toks)),
                           did, idx, txt))
    scored.sort(reverse=True)
    return [{"doc_id": did, "doc": nomes.get(did, did), "idx": idx,
             "trecho": txt[:1500]} for _, did, idx, txt in scored[:k]]


# ── Resumo e tópicos via Hermes ───────────────────────────────────────
def _llm(cfg: dict, sistema: str, usuario: str, max_tokens: int = 800) -> str:
    import hermes_bridge
    res = hermes_bridge.chat_complete(
        cfg["proxy"], cfg["model"],
        [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        max_tokens=max_tokens)
    return res["texto"]


def resumir_documento(db, cfg: dict, doc_id: str, owner=DONO_PADRAO) -> str:
    row = db.execute("SELECT summary, name FROM documents WHERE id=? AND owner_id=?",
                     (doc_id, owner)).fetchone()
    if not row:
        raise DocErro("Documento não encontrado.", "nao_encontrado")
    if row[0]:
        return row[0]
    texto = obter_texto(db, doc_id, owner=owner)
    if not texto.strip():
        raise DocErro("Documento sem texto.", "vazio")
    chunks = dividir_chunks(texto)
    if len(chunks) > 6:
        # amostra distribuída (começo, meio, fim) para caber no tempo/quota
        idxs = sorted({0, 1, len(chunks) // 3, len(chunks) // 2,
                       2 * len(chunks) // 3, len(chunks) - 1})
        chunks = [chunks[i] for i in idxs if 0 <= i < len(chunks)]
    parciais = []
    for ch in chunks:
        try:
            parciais.append(_llm(cfg, "Resuma o trecho em até 8 linhas, só o essencial.",
                                 ch[:4000], max_tokens=500))
        except Exception as exc:
            log.warning("resumo parcial falhou: %s", exc)
    if not parciais:
        raise DocErro("A IA falhou ao resumir. Tente de novo.", "ia_falhou")
    if len(parciais) == 1:
        final = parciais[0]
    else:
        final = _llm(cfg, "Junte os resumos parciais num resumo único, organizado com títulos e bullets.",
                      "\n\n---\n\n".join(parciais)[:15000], max_tokens=1000)
    with db:
        db.execute("UPDATE documents SET summary=? WHERE id=? AND owner_id=?", (final, doc_id, owner))
    return final


def topicos_documento(db, cfg: dict, doc_id: str, owner=DONO_PADRAO) -> str:
    row = db.execute("SELECT topics, name FROM documents WHERE id=? AND owner_id=?",
                     (doc_id, owner)).fetchone()
    if not row:
        raise DocErro("Documento não encontrado.", "nao_encontrado")
    if row[0]:
        return row[0]
    texto = obter_texto(db, doc_id, 30000, owner)
    try:
        final = _llm(cfg, "Extraia do documento: 1) tópicos principais (bullets), "
                           "2) palavras-chave, 3) datas/números importantes, "
                           "4) pendências ou próximos passos, se houver. Markdown curto.",
                      texto, max_tokens=800)
    except Exception as exc:
        raise DocErro(f"A IA falhou: {exc}.", "ia_falhou") from None
    with db:
        db.execute("UPDATE documents SET topics=? WHERE id=? AND owner_id=?", (final, doc_id, owner))
    return final
