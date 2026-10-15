import sys, time
sys.path.insert(0, ".")
import hermes_bridge

BASE = "http://127.0.0.1:8645/v1"
t0 = time.monotonic()
try:
    ms = hermes_bridge.listar_modelos(BASE, timeout=10.0)
    print("MODELS: %d em %.1fs" % (len(ms), time.monotonic() - t0))
except Exception as e:
    print("MODELS_ERRO", type(e).__name__, getattr(e, "codigo", "?"), str(e)[:120])

for mid in ("poolside/laguna-s-2.1:free",):
    for i in range(2):
        t0 = time.monotonic()
        try:
            r = hermes_bridge.chat_complete(
                BASE, mid, [{"role": "user", "content": "Diga apenas: OK"}],
                timeout=60.0, max_tokens=10)
            print("CHAT_OK %.1fs resp=%r" % (time.monotonic() - t0, str(r.get("texto"))[:80]))
        except Exception as e:
            print("CHAT_ERRO %.1fs %s %s %s" % (time.monotonic() - t0, type(e).__name__,
                  getattr(e, "codigo", "?"), str(e)[:100]))
