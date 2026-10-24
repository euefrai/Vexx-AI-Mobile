"""Multimodal evidence metadata (V5.8).

This module is intentionally conservative: discovering an image, video or
document never turns it into evidence.  It records where the item was found,
what was actually read (metadata/link only), and which validation/analysis
steps did *not* run.

No media is downloaded or rehosted here.  Callers must not claim that an item
was watched, transcribed or visually analysed based on this metadata.
"""
from __future__ import annotations

import hashlib
import re
import urllib.parse
from html.parser import HTMLParser

MAX_MEDIA = 12
MAX_URL = 500
MAX_TEXT = 240

MEDIA_TYPES = ("image", "video", "document")
ACCESS_STATES = ("metadata_only", "link_only", "not_fetched")
VALIDATION_STATES = ("unverified", "blocked", "invalid")

_SAFE_SCHEMES = ("http", "https")
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg")
_DOC_EXT = (".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".tsv", ".xlsx",
            ".json", ".html", ".htm")
_VIDEO_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
                "vimeo.com", "www.vimeo.com", "player.vimeo.com")
_VIDEO_EMBED_HOSTS = ("youtube.com", "www.youtube.com", "www.youtube-nocookie.com",
                      "player.vimeo.com")
_SKIP_SCHEMES = ("data:", "javascript:", "blob:", "mailto:", "tel:", "file:")


def _safe_url(raw, base: str = "") -> str:
    """Absolute http(s) URL without credentials; empty when unsafe."""
    text = str(raw or "").strip()
    if not text or len(text) > MAX_URL or text.lower().startswith(_SKIP_SCHEMES):
        return ""
    try:
        absolute = urllib.parse.urljoin(base or "", text)
        parts = urllib.parse.urlsplit(absolute)
        if parts.scheme.lower() not in _SAFE_SCHEMES:
            return ""
        if not parts.hostname or parts.username or parts.password:
            return ""
        host=parts.hostname.rstrip('.').lower()
        if host=='localhost' or host.endswith(('.localhost','.local','.internal')):
            return ''
        import ipaddress
        try:
            if not ipaddress.ip_address(host).is_global:return ''
        except ValueError:
            if re.fullmatch(r'(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+))*',host):return ''
        # Reject malformed port declarations without performing DNS or fetching.
        _=parts.port
    except ValueError:
        return ""
    # Fragments are not sent to servers and can carry misleading anchors.
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc, parts.path or "/", parts.query, ""))[:MAX_URL]


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()[:120]
    except ValueError:
        return ""


def _clean(value, limit: int = MAX_TEXT) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _item_id(kind: str, url: str) -> str:
    return "med-" + hashlib.sha1(f"{kind}|{url}".encode("utf-8")).hexdigest()[:12]


def _youtube_id(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        if host == "youtu.be":
            return (parts.path.strip("/").split("/")[0] or "")[:20]
        if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if parts.path == "/watch":
                return (urllib.parse.parse_qs(parts.query).get("v") or [""])[0][:20]
            match = re.match(r"^/(?:embed|shorts|live)/([A-Za-z0-9_-]{6,20})", parts.path)
            if match:
                return match.group(1)
    except ValueError:
        pass
    return ""


def _is_video(url: str) -> bool:
    host = _host(url)
    if host in _VIDEO_HOSTS and re.fullmatch(r'[A-Za-z0-9_-]{6,20}', _youtube_id(url)):
        return True
    if host in ('vimeo.com','www.vimeo.com','player.vimeo.com') and re.search(r"/(?:video/)?\d{6,}(?:/|$)", urllib.parse.urlsplit(url).path):
        return True
    return bool(re.search(r"\.(mp4|webm|mov|m4v)(?:$|\?)", url, re.IGNORECASE))


def _is_image(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    return path.endswith(_IMAGE_EXT)


def _is_document(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    return path.endswith(_DOC_EXT)


class _MediaParser(HTMLParser):
    """Collect only metadata and link targets; never executes page content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.images: list[dict] = []
        self.videos: list[dict] = []
        self.anchors: list[str] = []
        self.iframes: list[dict] = []
        self._in_title = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").strip().lower()
            content = values.get("content", "").strip()
            if key and content:
                self.meta.setdefault(key, []).append(content[:500])
        elif tag == "title":
            self._in_title = True
        elif tag == "img":
            if len(self.images) < 24:
                self.images.append({
                    "src": values.get("src") or values.get("data-src") or "",
                    "alt": values.get("alt", ""),
                })
        elif tag == "video":
            if len(self.videos) < 12:
                self.videos.append({
                    "src": values.get("src", ""),
                    "poster": values.get("poster", ""),
                    "title": values.get("title", ""),
                })
        elif tag == "source":
            if len(self.videos) < 12:
                self.videos.append({
                    "src": values.get("src", ""),
                    "poster": "",
                    "title": values.get("title", ""),
                })
        elif tag == "iframe":
            if len(self.iframes) < 12:
                self.iframes.append({
                    "src": values.get("src") or values.get("data-src") or "",
                    "title": values.get("title", ""),
                })
        elif tag == "a":
            href = values.get("href", "")
            if href and len(self.anchors) < 120:
                self.anchors.append(href)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len("".join(self.title_parts)) < 300:
            self.title_parts.append(data)


def _meta(parser: _MediaParser, *keys: str) -> str:
    for key in keys:
        values = parser.meta.get(key) or []
        if values:
            return _clean(values[0], 500)
    return ""


def _add(out: list, item: dict, seen: set) -> None:
    if len(out) >= MAX_MEDIA:
        return
    key = (item["type"], item["url"])
    if key in seen:
        return
    seen.add(key)
    out.append(item)


def _base_item(kind: str, url: str, *, title: str, source_title: str,
               source_url: str, date: str = "", excerpt: str = "",
               access_state: str = "link_only", validation_state: str = "unverified",
               analysis_state: str = "not_analyzed") -> dict:
    return {
        "id": _item_id(kind, url),
        "type": kind,
        "title": _clean(title, 160) or f"{kind} descoberto",
        "url": url,
        "final_url": url,
        "source_title": _clean(source_title, 160),
        "source_url": source_url,
        "publisher": _host(url),
        "date": _clean(date, 40),
        "rights": "não informado",
        "access_state": access_state,
        "validation_state": validation_state,
        "analysis_state": analysis_state,
        "excerpt": _clean(excerpt),
        "used_excerpt": "",
        "evidence": False,
        "provenance": "html metadata" if access_state != "link_only" else "html link",
    }


def extrair_midia(pagina: str, url_base: str, titulo: str = "") -> list[dict]:
    """Extract image/video/document discovery metadata from an HTML page.

    The returned records are *discoveries*.  Images are metadata-only; videos
    and documents are links only.  ``evidence`` is always False and
    ``used_excerpt`` is always empty until a separate, explicit analysis
    records actual use.
    """
    base = _safe_url(url_base)
    if not base or not isinstance(pagina, str):
        return []
    parser = _MediaParser()
    try:
        parser.feed(pagina[:2_000_000])
    except Exception:
        return []
    page_title = _clean(titulo or _meta(parser, "og:title", "twitter:title")
                        or "".join(parser.title_parts), 160)
    published = _meta(parser, "article:published_time", "datepublished", "date")
    description = _meta(parser, "og:description", "twitter:description", "description")
    out: list[dict] = []
    seen: set = set()

    # Images explicitly advertised by the page.  Generic <img> tags are only
    # accepted when they carry meaningful alt text, reducing logo/chrome noise.
    image_candidates = []
    for key in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        value = _meta(parser, key)
        if value:
            image_candidates.append((value, _meta(parser, "og:image:alt", "twitter:image:alt")
                                     or description))
    for image in parser.images:
        if image["src"] and _clean(image["alt"], 160):
            image_candidates.append((image["src"], image["alt"]))
    for raw, alt in image_candidates:
        url = _safe_url(raw, base)
        if not url or not (_is_image(url) or _meta(parser, "og:image")):
            continue
        _add(out, _base_item(
            "image", url, title=alt or page_title or "Imagem descoberta",
            source_title=page_title, source_url=base, date=published,
            excerpt=alt or description, access_state="metadata_only",
            analysis_state="not_analyzed"), seen)

    # Videos: real player URLs first, then links to known video hosts.
    video_candidates = []
    for video in parser.videos:
        if video["src"]:
            video_candidates.append((video["src"], video["title"]))
    for iframe in parser.iframes:
        if iframe["src"] and _host(_safe_url(iframe["src"], base)) in _VIDEO_EMBED_HOSTS:
            video_candidates.append((iframe["src"], iframe["title"]))
    for anchor in parser.anchors:
        url = _safe_url(anchor, base)
        if url and _is_video(url):
            video_candidates.append((url, ""))
    for raw, label in video_candidates:
        url = _safe_url(raw, base)
        if not url:
            continue
        _add(out, _base_item(
            "video", url, title=label or page_title or "Vídeo descoberto",
            source_title=page_title, source_url=base, date=published,
            excerpt=description, access_state="link_only",
            analysis_state="not_analyzed"), seen)

    # Structured metadata is distinct from watching/transcribing the video.
    import web_extract
    for record in web_extract._ld_por_tipo(web_extract._ldjson_objs(pagina), {'videoobject'}, teto=6):
        target = _safe_url(record.get('url') or record.get('embedUrl') or record.get('contentUrl'), base)
        if not target or not _is_video(target):
            continue
        item = _base_item('video', target, title=record.get('name') or page_title,
            source_title=page_title, source_url=base, date=record.get('uploadDate') or '',
            excerpt=record.get('description') or '', access_state='metadata_only')
        thumb = record.get('thumbnailUrl') or ''
        author = record.get('author') or {}
        item.update({'thumb':_safe_url(thumb[0] if isinstance(thumb,list) and thumb else thumb, base),
            'publisher':_clean(author.get('name') if isinstance(author,dict) else author),
            'duration':_clean(record.get('duration')), 'metadata_state':'METADATA_READ'})
        # Prefer actual metadata over an earlier bare link to the same video.
        out = [prior for prior in out if (prior['type'],prior['url']) != ('video',target)]
        seen.discard(('video',target))
        _add(out,item,seen)

    # Documents linked by the page (real links; no download attempted).
    for anchor in parser.anchors:
        url = _safe_url(anchor, base)
        if not url or not _is_document(url):
            continue
        name = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
        _add(out, _base_item(
            "document", url, title=name or page_title or "Documento descoberto",
            source_title=page_title, source_url=base, date=published,
            excerpt=description, access_state="link_only",
            analysis_state="not_analyzed"), seen)
    return out


def discover_search_media(results: list[dict]) -> list[dict]:
    """Keep known media targets even when they cannot be read as HTML.

    No download, analysis, invented thumbnail or licence; image targets are
    restricted to the existing Commons adapter's Wikimedia hosts.
    """
    out, seen = [], set()
    for source in (results or [])[:MAX_MEDIA]:
        metadata = source.get('meta') or {}
        url = _safe_url((metadata.get('original_url') if source.get('origem')=='commons' else '') or source.get('pdf_url') or source.get('url'))
        if not url:
            continue
        import ipaddress
        host = _host(url)
        try:
            if not ipaddress.ip_address(host).is_global:
                continue
        except ValueError:
            if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
                continue
        kind = ('image' if source.get('tipo') == 'imagem' and source.get('origem') == 'commons'
                and _host(url) in ('upload.wikimedia.org','thumb.wikimedia.org') else
                'video' if _is_video(url) else
                'document' if source.get('pdf_url') or urllib.parse.urlsplit(url).path.lower().endswith('.pdf') else '')
        if not kind:
            continue
        page = _safe_url((source.get('meta') or {}).get('pagina') or source.get('landing_url') or source.get('url'))
        item = _base_item(kind, url, title=source.get('titulo') or source.get('title'),
                          source_title=source.get('titulo') or '', source_url=page,
                          date=source.get('publicado_em') or '', access_state='link_only')
        item['provenance'] = 'search metadata'
        item['rights'] = _clean(source.get('license')) or 'não informado'
        metadata = source.get('meta') or {}
        if kind == 'image':
            item.update({'thumb':_safe_url(metadata.get('thumb_url')),
                'width':metadata.get('largura'), 'height':metadata.get('altura'),
                'mime':_clean(metadata.get('mime')), 'attribution':_clean(source.get('attribution')),
                'license_url':_safe_url(metadata.get('license_url')),
                'excerpt':_clean(source.get('description')),
                'metadata_state':'METADATA_READ'})
        elif kind == 'video':
            item['metadata_state'] = 'VIDEO_FOUND'
        _add(out, item, seen)
    return out


def relevant_media(items: list[dict], query: str) -> list[dict]:
    """Conservative topic metadata gate, never visual/content verification."""
    normalized = query.casefold()
    wanted = ('image' if re.search(r'\b(imagens?|fotos?|fotografias?)\b', normalized) else
              'video' if re.search(r'\b(v[ií]deos?)\b', normalized) else '')
    if not wanted:
        return items
    import search_orchestrator as orch
    topic = re.sub(r'\b(imagens?|fotos?|fotografias?|v[ií]deos?|licenciad[oa]s?|p[uú]blic[oa]s?|apresenta[cç][aã]o|mostre|encontre)\b', ' ', query, flags=re.I)
    terms = orch._termos_correspondencia(topic)
    out=[]
    for item in items:
        body=' '.join(str(item.get(k) or '') for k in ('title','excerpt','source_title','url')).replace('_',' ')
        if item.get('type') == wanted and terms and sum(orch._tem_termo(t,body) for t in terms)/len(terms)>=0.6:
            out.append({**item,'relevance_state':'TOPIC_METADATA_MATCH'})
    return out


def resumo_midia(items: list[dict]) -> dict:
    """Honest counts for cards/progress; never implies analysis."""
    items = [item for item in (items or []) if isinstance(item, dict)]
    return {
        "total": len(items),
        "images": sum(1 for item in items if item.get("type") == "image"),
        "videos": sum(1 for item in items if item.get("type") == "video"),
        "documents": sum(1 for item in items if item.get("type") == "document"),
        "metadata_only": sum(1 for item in items
                             if item.get("access_state") == "metadata_only"),
        "link_only": sum(1 for item in items if item.get("access_state") == "link_only"),
        "validated": sum(1 for item in items
                         if item.get("validation_state") not in ("unverified", "invalid")),
        "analyzed": sum(1 for item in items
                        if item.get("analysis_state") not in ("not_analyzed", "")),
        "evidence": sum(1 for item in items if item.get("evidence") is True),
    }
