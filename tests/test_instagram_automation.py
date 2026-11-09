"""Testes unitários e de integração do módulo especialista do Instagram (pc_modules/instagram_automation.py)."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_modules import instagram_automation


def test_rotear_comando_instagram_envio_mensagem(monkeypatch):
    chamadas = []
    def fake_enviar(dest, msg):
        chamadas.append((dest, msg))
        return {
            "status": "sucesso",
            "destinatario": dest,
            "mensagem_enviada": msg,
            "resumo": f"Mensagem enviada com sucesso para {dest}: {msg}"
        }
    monkeypatch.setattr(instagram_automation, "enviar_mensagem_instagram", fake_enviar)

    texto = "envie uma mensagem para Gustavo dizendo 'já vi o anexo, ficou top!'"
    res = instagram_automation.rotear_comando_instagram(texto)
    assert res is not None
    assert len(chamadas) == 1
    assert chamadas[0][0] == "Gustavo"
    assert "já vi o anexo" in chamadas[0][1]
    assert "Mensagem enviada com sucesso" in res


def test_rotear_comando_instagram_verificar_online(monkeypatch):
    chamadas = []
    def fake_online(contato):
        chamadas.append(contato)
        return {
            "status": "sucesso",
            "contato": contato,
            "online_agora": True,
            "resumo": f"Status de Atividade: {contato} está ONLINE AGORA."
        }
    monkeypatch.setattr(instagram_automation, "verificar_online_usuario", fake_online)

    texto_1 = "que horas Gustavo estava online no instagram?"
    res_1 = instagram_automation.rotear_comando_instagram(texto_1)
    assert res_1 is not None
    assert chamadas[-1] == "Gustavo"
    assert "ONLINE AGORA" in res_1

    texto_2 = "veja se wzz está online"
    res_2 = instagram_automation.rotear_comando_instagram(texto_2)
    assert res_2 is not None
    assert chamadas[-1] == "wzz"


def test_rotear_comando_instagram_entrar_na_conversa(monkeypatch):
    chamadas = []
    def fake_entrar(contato):
        chamadas.append(contato)
        return {
            "status": "sucesso",
            "contato": contato,
            "resumo": f"Conversa aberta com sucesso no Instagram Direct com {contato}."
        }
    monkeypatch.setattr(instagram_automation, "entrar_na_conversa", fake_entrar)

    texto = "entre na conversa com Gustavo no instagram"
    res = instagram_automation.rotear_comando_instagram(texto)
    assert res is not None
    assert chamadas[0] == "Gustavo"
    assert "Conversa aberta" in res


def test_rotear_comando_instagram_pesquisa(monkeypatch):
    chamadas = []
    def fake_busca(termo):
        chamadas.append(termo)
        return {
            "status": "sucesso",
            "termo": termo,
            "resumo": f"Resultados de Pesquisa no Instagram para '{termo}'."
        }
    monkeypatch.setattr(instagram_automation, "pesquisar_instagram", fake_busca)

    texto = "pesquise no instagram por loja de informática"
    res = instagram_automation.rotear_comando_instagram(texto)
    assert res is not None
    assert "loja de informática" in chamadas[0]
    assert "Resultados de Pesquisa" in res


def test_rotear_comando_instagram_scroll(monkeypatch):
    rolagens = []
    monkeypatch.setattr(instagram_automation, "rolar_lista_conversas", lambda delta, passos: rolagens.append(delta) or True)

    texto_baixo = "role as mensagens do instagram para baixo"
    res_baixo = instagram_automation.rotear_comando_instagram(texto_baixo)
    assert res_baixo is not None
    assert "para baixo" in res_baixo
    assert rolagens[-1] < 0

    texto_cima = "role o chat do instagram para cima"
    res_cima = instagram_automation.rotear_comando_instagram(texto_cima)
    assert res_cima is not None
    assert "para cima" in res_cima
    assert rolagens[-1] > 0
