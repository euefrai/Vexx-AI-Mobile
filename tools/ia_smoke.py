"""Smoke REAL dos provedores de LLM (rodar no PC, onde ficam as chaves).

Uso:
  python tools/ia_smoke.py                 # testa o 1º modelo curado de cada provedor com chave
  python tools/ia_smoke.py openai/gpt-4o-mini gemini/gemini-2.0-flash

O que faz, sem mentir e sem inventar:
  1. Lista o catálogo do seletor (hermes + provedores com chave), sem chaves.
  2. Para cada alvo: uma chamada curta real (chat completions) e um stream real.
  3. Imprime modelo, latência e o texto mínimo devolvido; erros só como código.

Nunca imprime valores de chave. Custo real: ~poucos tokens por chamada.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hermes_bridge  # noqa: E402
import providers  # noqa: E402

PROMPT = [{"role": "user", "content": "Responda apenas: ok"}]


def alvo_padrao() -> list:
    """1º modelo curado de cada provedor com chave (sem hermes)."""
    alvos = []
    for nome, d in providers.PROVIDERS.items():
        if nome == "hermes" or not providers.chave(nome):
            continue
        alvos.append(f"{nome}/{d['modelos'][0]}")
    return alvos


def testar(modelo: str) -> bool:
    prov, mid = providers.dividir(modelo)
    print(f"\n== {modelo} (provedor: {prov}) ==")
    if prov == "hermes":
        print("  (hermes: teste manual via 'hermes proxy status'; aqui é só provedor externo)")
        return True
    ok = True
    # 1) Chamada simples
    try:
        t0 = time.monotonic()
        res = providers.chat_complete(prov, mid, PROMPT, timeout=30, max_tokens=12)
        print(f"  completo  ok  {res['latencia_s']}s  -> {res['texto'][:60]!r}")
    except hermes_bridge.BridgeErro as exc:
        ok = False
        print(f"  completo  FALHOU  codigo={exc.codigo}  ({exc})  [{(time.monotonic()-t0):.1f}s]")
    # 2) Stream
    try:
        pedacos = []
        t0 = time.monotonic()
        res2 = providers.chat_stream(prov, mid, PROMPT, lambda s, t: pedacos.append(t),
                                     timeout=30, max_tokens=12)
        print(f"  stream    ok  {res2['latencia_s']}s  {len(pedacos)} delta(s)  -> {res2['texto'][:60]!r}")
    except hermes_bridge.BridgeErro as exc:
        ok = False
        print(f"  stream    FALHOU  codigo={exc.codigo}  ({exc})  [{(time.monotonic()-t0):.1f}s]")
    return ok


def main() -> int:
    alvos = sys.argv[1:] or alvo_padrao()
    print("Provedores com chave no PC:", ", ".join(providers.configurados()) or "nenhum")
    try:
        cat = providers.listar_tudo()
        por_prov = {}
        for item in cat.get("items", []):
            por_prov.setdefault(item["provider"], 0)
            por_prov[item["provider"]] += 1
        print("Catálogo do seletor:", ", ".join(f"{k}={v}" for k, v in sorted(por_prov.items())))
    except hermes_bridge.BridgeErro as exc:
        print(f"Catálogo indisponível ({exc.codigo}); seguindo com os alvos.")
    if not alvos:
        print("\nBLOQUEADO: nenhum provedor externo com chave configurada.")
        print("Configure no PC (ex.: setx OPENAI_API_KEY \"sua-chave\") e reabra o agente.")
        return 2
    falhas = [m for m in alvos if not testar(m)]
    print(f"\nResultado: {len(alvos) - len(falhas)}/{len(alvos)} alvo(s) ok.")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
