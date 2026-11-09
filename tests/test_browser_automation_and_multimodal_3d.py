import pytest
from pathlib import Path
import sqlite3

import model3d_generative
import model3d
from pc_modules import browser_automation, db_core, memory_store


def test_model3d_mapa_generative():
    mapa = model3d_generative.gerar_mapa_3d("hangar espacial tático")
    valid = model3d.validate(mapa)
    assert valid["id"].startswith("dev-mapa-")
    assert len(valid["objects"]) >= 4
    assert valid["objects"][0]["id"] == "piso_topografico"
    assert "Mapeamento Cartográfico Espacial" in valid["source"]


def test_model3d_especificacao_tecnica():
    spec = """
    Equipamento com chassi de titanio de 160x80x12 mm.
    Possui display OLED frontal com emissao azul, modulo de energia de 5000 mAh e placa principal com barramento de cobre.
    """
    cena = model3d_generative.gerar_modelo_3d_de_especificacao(spec, "Dispositivo Militar")
    valid = model3d.validate(cena)
    assert valid["id"].startswith("dev-")
    assert any(o["id"] == "painel_display" for o in valid["objects"])
    assert any(o["id"] == "nucleo_processamento" for o in valid["objects"])
    assert valid["objects"][0]["metalness"] >= 0.8  # chassi de titânio


def test_browser_automation_routing(monkeypatch):
    # Verifica que o navegador padrão do sistema é detectado dinamicamente
    exe_padrao = browser_automation.obter_navegador_padrao_windows()
    assert exe_padrao is not None
    assert "brave" in exe_padrao.lower()

    # Mock iniciar_navegador_perfil, sleep, e capturar_tela to run instantly in tests
    monkeypatch.setattr(browser_automation, "iniciar_navegador_perfil", lambda url: None)
    monkeypatch.setattr(browser_automation, "abrir_navegador", lambda url, isolado=False: None)
    monkeypatch.setattr(browser_automation, "disparar_notificacao_windows", lambda t, m: True)

    from PIL import Image
    fake_img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    monkeypatch.setattr(browser_automation, "capturar_tela", lambda: fake_img)

    # Monkeypatch verificar_instagram timeout
    monkeypatch.setattr(browser_automation.time, "sleep", lambda s: None)

    cmd_insta = browser_automation.executar_comando_automacao("verifique meu instagram para ver se tem novas mensagens")
    assert cmd_insta is not None
    assert "Instagram Direct" in cmd_insta

    cmd_tiktok = browser_automation.executar_comando_automacao("veja as tendencias e trends no tiktok de hoje")
    assert cmd_tiktok is not None
    assert "TikTok" in cmd_tiktok

    cmd_kabum = browser_automation.executar_comando_automacao("monitore o kabum para rtx 4070 abaixo de 3500 reais")
    assert cmd_kabum is not None
    assert "Kabum" in cmd_kabum


def test_agent_cognition_and_desires(tmp_path):
    db_file = tmp_path / "test_cog.sqlite3"
    db = db_core.open_db(db_file)

    cog = memory_store.obter_cognicao_agente(db, "test_owner")
    assert cog["humor"] == "curioso_e_focado"
    assert cog["energia"] == 1.0

    updated = memory_store.atualizar_cognicao_agente(
        db, "test_owner", humor="reflexivo", energia=0.95,
        desejo="Aprender sobre automações complexas",
        pensamento="O usuário deseja expandir as capacidades do VEXX AI.",
        novo_aprendizado="Instagram e TikTok podem ser navegados visualmente com perfil persistente"
    )
    assert updated["humor"] == "reflexivo"
    assert updated["energia"] == 0.95
    assert len(updated["aprendizados"]) == 1

    # Test natural query interpretation
    res = memory_store.interpretar_comando_memoria(db, "qual o seu desejo interno?", "test_owner")
    assert res is not None
    assert "Estado Cognitivo" in res[0]
    assert "Reflexivo" in res[0]


def test_verificar_instagram_analise_real_com_notificacoes(monkeypatch):
    from pc_modules import browser_automation
    monkeypatch.setattr(browser_automation, "disparar_notificacao_windows", lambda t, m: True)

    img_path = r"C:\Users\efrai\.gemini\antigravity\brain\1b10b50a-5d0f-497f-a792-807af867cd5c\.user_uploaded\media_1794242148455_a8a54b7f.jpg"
    res = browser_automation.verificar_instagram(caminho_imagem_teste=img_path)
    assert res["status"] == "sucesso"
    assert res["total_pendentes"] == 7
    assert len(res["mensagens_nao_lidas"]) >= 2
    assert "Gustavo" in res["resumo"]
    assert "WZZ" in res["resumo"]
    assert "7 mensagens pendentes detectadas" in res["resumo"]
