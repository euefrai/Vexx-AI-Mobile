"""V5.8 local performance/resource benchmark (no network, no production).

Measures only the new pure modules: JDUI view building, export rendering and
schema validation.  Heavy media libraries are deliberately NOT imported.
"""
import ctypes
import gc
import json
import sys
import time
import tracemalloc
from ctypes import wintypes
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import jdui  # noqa: E402
import research_exports  # noqa: E402
import research_view  # noqa: E402


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def rss_mb():
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.K32GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        kernel.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        kernel.K32GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return round(counters.WorkingSetSize / 1024 / 1024, 2)
    except Exception:
        return None


def _resumo(n_steps=24, n_claims=10, n_media=12, n_hyp=8):
    steps = [{"id": f"p{i}", "tipo": ("busca", "ler", "verificar")[i % 3],
              "alvo": f"consulta {i}", "status": "feita" if i % 2 else "pendente",
              "objetivo_etapa": "objetivo real da etapa", "dependencias": []}
             for i in range(n_steps)]
    claims = [{"afirmacao": f"Afirmação verificável {i} com 400 mg e unidade.",
               "estado": "SUPPORTED", "metodo": "lexical", "cobertura_lexica": 0.8,
               "fontes": [{"evidence_id": f"ev{i}", "title": f"Fonte {i}",
                           "url": f"https://example.com/{i}", "domain": "example.com",
                           "relation": "SUPPORTS", "read": True,
                           "access_state": "read", "used_excerpt": "trecho usado"}]}
              for i in range(n_claims)]
    media = [{"type": ("image", "video", "document")[i % 3], "title": f"Mídia {i}",
              "url": f"https://example.com/m{i}.bin", "source_url": "https://example.com/a",
              "publisher": "example.com", "date": "2026-09-01",
              "rights": "não informado", "access_state": "metadata_only",
              "validation_state": "unverified", "analysis_state": "not_analyzed",
              "evidence": False, "excerpt": ""}
             for i in range(n_media)]
    hyps = [{"statement": f"Hipótese {i}?", "status": "inconclusive",
             "cadeia": [{"rotulo": "HIPÓTESE", "texto": f"Hipótese {i}?"},
                        {"rotulo": "CONCLUSÃO", "texto": "INCONCLUSIVA"}]}
            for i in range(n_hyp)]
    return {"id": "rj-bench", "objetivo": "Benchmark local", "modo": "investigativa",
            "status": "concluida", "plano_versao": 3, "etapas": steps,
            "orcamento": {"buscas": 12, "paginas": 20, "midia": 20, "replans": 2},
            "usados": {"buscas": 7, "paginas": 12, "replans": 1},
            "achados": claims, "midia": media, "hipoteses": hyps, "evidencias": 10,
            "midia_resumo": {"total": n_media}}


def _time(fn, repeticoes=100):
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    ultimo = None
    for _ in range(repeticoes):
        ultimo = fn()
    dt = (time.perf_counter() - t0) / repeticoes
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return round(dt * 1000, 3), round(pico / 1024 / 1024, 2), ultimo


def main():
    resumo = _resumo()
    evidence = [{"id": f"e{i}", "titulo": f"Fonte {i}", "url": f"https://e.com/{i}",
                 "dominio": "e.com", "status": "recuperada", "texto_lido": True,
                 "trecho": "trecho " * 30, "access_state": "read"} for i in range(200)]
    hypotheses = [{"hypothesis_id": f"h{i}", "statement": f"Hipótese {i}",
                   "status": "inconclusive", "cadeia": [
                       {"rotulo": "HIPÓTESE", "texto": "x"},
                       {"rotulo": "CONCLUSÃO", "texto": "INCONCLUSIVA"}]}
                  for i in range(50)]
    tracemalloc.start()
    view_ms, view_peak, message = _time(lambda: research_view.build_view(resumo), 100)
    tracemalloc.stop()
    ok, _, erros = jdui.validar_mensagem(message)
    assert ok, erros
    export = {}
    for fmt in ("md", "csv", "json"):
        ms, peak, payload = _time(
            lambda fmt=fmt: research_exports.build_export(
                resumo, evidence, hypotheses, fmt), 20)
        export[fmt] = {"ms": ms, "peak_python_mb": peak, "bytes": len(payload[0])}
    resultados = {
        "quando": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ambiente": {"python": sys.version.split()[0],
                     "rss_mb": rss_mb(), "plataforma": sys.platform},
        "view": {"steps": 24, "claims": 10, "media": 12, "hypotheses": 8,
                 "build_ms": view_ms, "peak_python_mb": view_peak,
                 "blocos": len(message.get("blocks", []))},
        "exports": export,
        "limites": {"MAX_EXPORT_BYTES": research_exports.MAX_EXPORT_BYTES,
                    "MAX_ITEMS": research_exports.MAX_ITEMS,
                    "JDUI_MAX_BLOCOS": 6},
        "libs_pesadas_importadas": [m for m in sys.modules
                                    if any(x in m.lower() for x in
                                           ("pdfjs", "echarts", "video.js", "docling"))],
        "observacao": "Tempos locais de módulos puros; não são latência de rede/render.",
    }
    destino = RAIZ / "qa-artifacts" / "v58" / "performance.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultados, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(json.dumps(resultados, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
