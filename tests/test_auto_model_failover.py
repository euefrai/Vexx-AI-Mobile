import pytest
import time
from unittest.mock import patch, MagicMock
from hermes_bridge import BridgeErro
import providers
from pc_modules.db_core import (
    modelos_tentativa,
    FALLBACKS_GRATIS_PADRAO,
    registrar_cooldown_modelo,
    _MODELOS_COOLDOWN,
)

def test_modelos_tentativa_inclui_fallbacks_gratis():
    cfg = {"model": "custom/pago-caro", "fallbacks": []}
    fila = modelos_tentativa(cfg, "custom/pago-caro")
    assert fila[0] == "custom/pago-caro"
    # Deve conter os fallbacks gratuitos no pipeline
    assert "vexx-qwen-2.5-3b" in fila
    assert any("free" in m or "qwen" in m for m in fila)

def test_cooldown_rebaixa_modelo_em_falha():
    _MODELOS_COOLDOWN.clear()
    cfg = {"model": "modelo/com-rate-limit"}
    registrar_cooldown_modelo("modelo/com-rate-limit", segundos=60.0)

    fila = modelos_tentativa(cfg, "")
    # O modelo com rate limit deve ter ido para o fim da fila de espera
    assert fila[0] != "modelo/com-rate-limit"
    assert "modelo/com-rate-limit" in fila

def test_tentar_modelos_auto_failover_em_rate_limit():
    _MODELOS_COOLDOWN.clear()
    modelos = ["openrouter/modelo-esgotado", "openrouter/modelo-gratis-backup"]

    def fake_chat_complete(prov, mid, messages, timeout=60.0, max_tokens=2000, proxy=""):
        if mid == "modelo-esgotado":
            raise BridgeErro("Rate limit excedido (429)", "rate_limit")
        return {"texto": "Resposta do modelo backup gratuito"}

    with patch.object(providers, "chat_complete", side_effect=fake_chat_complete):
        res = providers.tentar_modelos(modelos, [{"role": "user", "content": "Olá"}])
        assert res["texto"] == "Resposta do modelo backup gratuito"
        assert res["model_usado"] == "openrouter/modelo-gratis-backup"
        assert res["fallback_usado"] is True
        # Verifica que o modelo esgotado foi colocado em cooldown
        assert "openrouter/modelo-esgotado" in _MODELOS_COOLDOWN

def test_chat_stream_fb_auto_failover():
    _MODELOS_COOLDOWN.clear()
    modelos = ["openrouter/modelo-indisponivel", "openrouter/modelo-gratis-backup"]
    chunks_recebidos = []

    def fake_chat_stream(prov, mid, messages, emit, deve_parar=None, timeout=180.0, max_tokens=2000, proxy=""):
        if mid == "modelo-indisponivel":
            raise BridgeErro("Modelo 503 temporariamente indisponível", "indisponivel")
        emit(1, "Texto stream de backup")
        return {"texto": "Texto stream de backup"}

    with patch.object(providers, "chat_stream", side_effect=fake_chat_stream):
        res = providers.chat_stream_fb(
            modelos,
            [{"role": "user", "content": "Olá"}],
            on_delta=lambda seq, txt: chunks_recebidos.append(txt),
        )
        assert res["texto"] == "Texto stream de backup"
        assert res["model_usado"] == "openrouter/modelo-gratis-backup"
        assert res["fallback_usado"] is True
        assert chunks_recebidos == ["Texto stream de backup"]
        assert "openrouter/modelo-indisponivel" in _MODELOS_COOLDOWN

def test_qwen_hibernando_aciona_failover():
    _MODELOS_COOLDOWN.clear()
    modelos = ["vexx-qwen-2.5-3b", "openrouter/meituan/longcat-2.5:free"]
    fake_res_qwen = {"status": "fallback", "resposta": "Análise Qwen: Processando..."}

    with patch("qwen_llm_service.gerar_resposta_qwen", return_value=fake_res_qwen):
        with pytest.raises(BridgeErro) as exc_info:
            providers.chat_complete("vexx", "vexx-qwen-2.5-3b", [{"role": "user", "content": "Teste"}])
        assert exc_info.value.codigo == "indisponivel"

        real_complete = providers.chat_complete
        def fake_complete(prov, mid, *a, **k):
            if prov == "vexx":
                return real_complete(prov, mid, *a, **k)
            return {"texto": "OK Longcat"}

        with patch.object(providers, "chat_complete", side_effect=fake_complete):
            res = providers.tentar_modelos(modelos, [{"role": "user", "content": "Teste"}])
            assert res["model_usado"] == "openrouter/meituan/longcat-2.5:free"
            assert res["fallback_usado"] is True
            assert res["texto"] == "OK Longcat"
