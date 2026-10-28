"""Controle remoto do PC (fase AnyDesk MVP): captura de tela + mouse/teclado.

Somente Windows. Captura tenta mss, depois PIL ImageGrab (dependências
opcionais — o relay nunca importa este módulo). Entrada usa ctypes (stdlib).

SEGURANÇA:
- Entrada exige JULIA_REMOTE=1 ou autorização local validada pelo PC Agent.
  Sem isso, tudo é recusado com codigo "desativado" (modo só-visualização).
- Comandos validados (tipos, faixas, tamanhos) + rate limit em memória.
- Nenhuma execução de terminal/arquivos — só eventos de mouse/teclado.
- Coordenadas chegam normalizadas (0..1) e são convertidas aqui.
"""
import base64
import io
import sys
import time
from collections import deque

MAX_W = 1920
QUALIDADE = 78
MIN_INTERVALO = 0.05
MAX_POR_MINUTO = 720

TECLAS_NOMEADAS = {"enter", "backspace", "tab", "esc", "escape", "space",
                   "left", "right", "up", "down", "home", "end",
                   "pageup", "pagedown", "delete", "insert"}
VK = {"enter": 0x0D, "backspace": 0x08, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
      "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
      "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
      "delete": 0x2E, "insert": 0x2D}

_janela = deque()


class RemotoErro(ValueError):
    def __init__(self, mensagem, codigo="remoto"):
        super().__init__(mensagem)
        self.codigo = codigo


def entrada_ativada() -> bool:
    import os
    return os.environ.get("JULIA_REMOTE", "") == "1"


def _limpar_janela():
    agora = time.monotonic()
    while _janela and agora - _janela[0] > 60.0:
        _janela.popleft()


def checar_ritmo():
    _limpar_janela()
    agora = time.monotonic()
    if _janela and agora - _janela[-1] < MIN_INTERVALO:
        raise RemotoErro("Comandos rápidos demais.", "ritmo")
    if len(_janela) >= MAX_POR_MINUTO:
        raise RemotoErro("Limite de comandos por minuto.", "ritmo")
    _janela.append(agora)


def _num(v, nome):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise RemotoErro(f"Campo '{nome}' inválido.", "invalido") from None
    if not 0.0 <= f <= 1.0:
        raise RemotoErro(f"Campo '{nome}' fora da tela.", "invalido")
    return f


def validar_comando(cmd: dict) -> dict:
    if not isinstance(cmd, dict):
        raise RemotoErro("Comando inválido.", "invalido")
    tipo = cmd.get("kind")
    if tipo in ("move", "click", "double", "right"):
        return {"kind": tipo, "x": _num(cmd.get("x"), "x"), "y": _num(cmd.get("y"), "y")}
    if tipo == "drag":
        points = cmd.get("points")
        if not isinstance(points, list) or not 2 <= len(points) <= 32:
            raise RemotoErro("Arrasto exige 2 a 32 pontos.", "invalido")
        if any(not isinstance(p, dict) for p in points):
            raise RemotoErro("Ponto inválido.", "invalido")
        return {"kind": tipo, "points": [{"x": _num(p.get("x"), "x"),
                                         "y": _num(p.get("y"), "y")} for p in points]}
    if tipo == "scroll":
        try:
            dx, dy = int(cmd.get("dx", 0)), int(cmd.get("dy", 0))
        except (TypeError, ValueError):
            raise RemotoErro("Scroll inválido.", "invalido") from None
        return {"kind": tipo, "dx": max(-10, min(10, dx)), "dy": max(-10, min(10, dy))}
    if tipo == "key":
        tecla = str(cmd.get("key", "")).strip().lower()[:20]
        if len(tecla) != 1 and tecla not in TECLAS_NOMEADAS:
            raise RemotoErro("Tecla inválida.", "invalido")
        return {"kind": tipo, "key": tecla}
    if tipo == "text":
        texto = str(cmd.get("text", ""))
        if not texto or len(texto) > 200:
            raise RemotoErro("Texto inválido (1–200 chars).", "invalido")
        return {"kind": tipo, "text": texto}
    raise RemotoErro(f"Tipo '{tipo}' desconhecido.", "invalido")


def tamanho_tela() -> tuple:
    if sys.platform != "win32":
        raise RemotoErro("Captura só no Windows.", "plataforma")
    import ctypes
    u = ctypes.windll.user32
    return (u.GetSystemMetrics(0), u.GetSystemMetrics(1))


def posicao_cursor(largura: int, altura: int):
    """Position on the captured primary screen; other monitors stay hidden."""
    import ctypes
    from ctypes import wintypes
    point = wintypes.POINT()
    try:
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None
        if largura <= 0 or altura <= 0 or not (0 <= point.x < largura and 0 <= point.y < altura):
            return None
        return {"x": point.x / largura, "y": point.y / altura}
    except (AttributeError, OSError):
        return None


def capturar(max_w: int = MAX_W, qualidade: int = QUALIDADE) -> dict:
    if sys.platform != "win32":
        raise RemotoErro("Captura só no Windows.", "plataforma")
    max_w = max(320, min(int(max_w or MAX_W), MAX_W))
    qualidade = max(30, min(int(qualidade or QUALIDADE), 85))
    inicio = time.monotonic()
    rgb = tamanho = None
    try:
        import mss
        with mss.mss() as s:
            tiro = s.grab(s.monitors[1])
            tamanho = (tiro.width, tiro.height)
            rgb = (tiro.size, tiro.bgra)
    except ImportError:
        pass
    except Exception as exc:
        raise RemotoErro(f"Falha na captura ({exc}).", "captura") from None
    try:
        from PIL import Image
        if rgb is None:
            from PIL import ImageGrab
            img = ImageGrab.grab().convert("RGB")
            tamanho = img.size
        else:
            img = Image.frombytes("RGB", rgb[0], rgb[1], "raw", "BGRX").convert("RGB")
        img.thumbnail((max_w, max_w * 2))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=qualidade)
        return {"imagem": base64.b64encode(buf.getvalue()).decode(),
                "largura": img.size[0], "altura": img.size[1],
                "tela": list(tamanho), "cursor": posicao_cursor(*tamanho), "ms": int((time.monotonic() - inicio) * 1000)}
    except ImportError:
        raise RemotoErro("Sem mss nem Pillow no PC.", "dependencia") from None
    except Exception as exc:
        raise RemotoErro(f"Falha ao codificar ({exc}).", "captura") from None


def _para_px(x: float, y: float) -> tuple:
    w, h = tamanho_tela()
    return (min(w - 1, max(0, int(x * w))), min(h - 1, max(0, int(y * h))))


def _digitar_unicode(texto: str) -> None:
    """Teclas Unicode via SendInput (maiúsculas/símbolos corretos)."""
    import ctypes
    from ctypes import wintypes

    class KBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

    class HARDINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KBDINPUT), ("hi", HARDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", UNION)]

    try:
        encoded = texto.encode('utf-16-le')
    except UnicodeEncodeError:
        raise RemotoErro('Texto Unicode inválido.', 'invalido') from None
    n = []
    for offset in range(0, len(encoded), 2):
        code_unit = int.from_bytes(encoded[offset:offset + 2], 'little')
        for flags in (0x0004, 0x0004 | 0x0002):  # UNICODE down/up
            ki = KBDINPUT(0, code_unit, flags, 0, None)
            n.append(INPUT(1, UNION(ki=ki)))
    arr = (INPUT * len(n))(*n)
    send_input = ctypes.windll.user32.SendInput
    send_input.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    send_input.restype = wintypes.UINT
    if send_input(len(n), arr, ctypes.sizeof(INPUT)) != len(n):
        raise RemotoErro('O Windows não aceitou a digitação. Verifique a sessão e as permissões da janela.', 'entrada')


def executar(valido: dict, *, autorizado: bool = False) -> dict:
    """Evento validado. Consentimento por conta é conferido pelo chamador agente."""
    if not entrada_ativada() and not autorizado:
        raise RemotoErro("Controle desativado no PC (JULIA_REMOTE=1 para ativar).",
                         "desativado")
    if sys.platform != "win32":
        raise RemotoErro("Entrada só no Windows.", "plataforma")
    checar_ritmo()
    import ctypes
    u = ctypes.windll.user32
    tipo = valido["kind"]
    if tipo == "move":
        u.SetCursorPos(*_para_px(valido["x"], valido["y"]))
    elif tipo in ("click", "double", "right"):
        x, y = _para_px(valido["x"], valido["y"])
        u.SetCursorPos(x, y)
        down, up = (0x0008, 0x0010) if tipo == "right" else (0x0002, 0x0004)
        n = 2 if tipo == "double" else 1
        for _ in range(n):
            u.mouse_event(down, 0, 0, 0, 0)
            u.mouse_event(up, 0, 0, 0, 0)
            if n == 2:
                time.sleep(0.05)
    elif tipo == "drag":
        points = valido["points"]
        u.SetCursorPos(*_para_px(points[0]["x"], points[0]["y"]))
        try:
            u.mouse_event(0x0002, 0, 0, 0, 0)
            for point in points[1:]:
                u.SetCursorPos(*_para_px(point["x"], point["y"]))
                time.sleep(0.008)
        finally:
            # One bounded command: disconnects cannot leave a mouse button held.
            u.mouse_event(0x0004, 0, 0, 0, 0)
    elif tipo == "scroll":
        if valido["dy"]:
            u.mouse_event(0x0800, 0, 0, valido["dy"] * 120, 0)
        if valido.get("dx"):
            u.mouse_event(0x1000, 0, 0, valido["dx"] * 120, 0)
    elif tipo == "key":
        t = valido["key"]
        vk = VK.get(t, 0)
        if vk:
            u.keybd_event(vk, 0, 0, 0)
            u.keybd_event(vk, 0, 2, 0)
        else:
            _digitar_unicode(t)
    elif tipo == "text":
        _digitar_unicode(valido["text"])
    return {"ok": True, "kind": tipo}
