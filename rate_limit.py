"""Limites técnicos em memória para o relay.

Defesa em profundidade contra rajadas e esgotamento de recursos. O estado é
volátil por instância (Render free) e NUNCA substitui o throttle persistente
do PC para autenticação. Chaves e janelas são limitadas para que um atacante
não consiga crescer memória indefinidamente.
"""
from __future__ import annotations

import ipaddress
import os
import threading
import time
from collections import deque

MAX_CHAVES = 4096
TTL_MAX = 24 * 60 * 60


def env_int(nome: str, padrao: int, minimo: int = 1, maximo: int = 1_000_000) -> int:
    try:
        valor = int(os.environ.get(nome, ""))
    except (TypeError, ValueError):
        valor = padrao
    return max(minimo, min(maximo, valor))


def _ip_valido(valor: str) -> str:
    texto = (valor or "").strip()
    if not texto:
        return ""
    try:
        return str(ipaddress.ip_address(texto))
    except ValueError:
        return ""


def client_ip(request, confiar_proxy: bool | None = None) -> str:
    """IP do cliente com proxy opcional.

    Só lê cabeçalhos de proxy quando JULIA_TRUST_PROXY está explicitamente
    ativo (render.yaml). Sem isso, usa o peer direto e ignora cabeçalhos
    forjáveis. O throttle persistente do PC cobre rotação de IP.
    """
    peer = getattr(getattr(request, "client", None), "host", "") or "unknown"
    if confiar_proxy is None:
        confiar_proxy = os.environ.get("JULIA_TRUST_PROXY", "").strip().lower() in (
            "1", "true", "yes", "sim")
    if not confiar_proxy:
        return str(peer)[:80]
    headers = getattr(request, "headers", {})
    for nome in ("cf-connecting-ip", "x-real-ip"):
        ip = _ip_valido(headers.get(nome, ""))
        if ip:
            return ip
    # X-Forwarded-For: o primeiro item é o cliente original na cadeia do
    # Cloudflare/Render. Só aceitamos itens que sejam IPs válidos.
    for parte in str(headers.get("x-forwarded-for", "")).split(","):
        ip = _ip_valido(parte)
        if ip:
            return ip
    return str(peer)[:80]


class RateLimiter:
    """Janela deslizante por chave, com poda e teto de chaves."""

    def __init__(self, max_chaves: int = MAX_CHAVES):
        self._buckets: dict[str, tuple[float, deque[float]]] = {}
        self._lock = threading.Lock()
        self._max_chaves = max(64, int(max_chaves))

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()

    def __len__(self) -> int:
        return len(self._buckets)

    def hit(self, chave: str, teto: int, janela: float) -> int:
        """Registra uma tentativa e retorna 0 ou os segundos de espera."""
        agora = time.monotonic()
        janela = min(TTL_MAX, max(1.0, float(janela)))
        teto = max(1, int(teto))
        with self._lock:
            bucket = self._buckets.get(chave)
            if bucket is None or bucket[0] != janela:
                fila: deque[float] = deque()
                self._buckets[chave] = (janela, fila)
            else:
                fila = bucket[1]
            while fila and agora - fila[0] >= janela:
                fila.popleft()
            if len(fila) >= teto:
                espera = int(janela - (agora - fila[0])) + 1
                return max(1, min(espera, int(janela) + 1))
            fila.append(agora)
            self._podar(agora)
            return 0

    def _podar(self, agora: float) -> None:
        if len(self._buckets) <= self._max_chaves:
            return
        for chave, (janela, fila) in list(self._buckets.items()):
            while fila and agora - fila[0] >= janela:
                fila.popleft()
            if not fila:
                self._buckets.pop(chave, None)
        if len(self._buckets) <= self._max_chaves:
            return
        excedente = len(self._buckets) - self._max_chaves
        antigos = sorted(
            self._buckets.items(),
            key=lambda item: item[1][1][-1] if item[1][1] else 0.0,
        )[:excedente]
        for chave, _ in antigos:
            self._buckets.pop(chave, None)
