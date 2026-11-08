"""Testes unitários e de integração do módulo de Visão, Leitura de Fontes (OCR) e Clique (YOLOv8 + RapidOCR)."""
from __future__ import annotations

import base64
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pc_agent
import server
import vision_service


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _mock_yolo_ocr_payload():
    return {
        "status": "sucesso",
        "dimensoes": {"largura": 1000, "altura": 500},
        "total_objetos": 2,
        "total_textos": 2,
        "tags_busca": "laptop, cell phone, Comprar, Agora, RTX4090",
        "texto_extraido": "Notebook Gamer RTX4090 Comprar Agora",
        "deteccoes": [
            {
                "tipo": "objeto",
                "objeto": "laptop",
                "confianca": 0.91,
                "coordenadas": [100.0, 50.0, 500.0, 350.0],
                "ponto_clique": {"x": 300, "y": 200, "x_norm": 0.3, "y_norm": 0.4},
            },
            {
                "tipo": "objeto",
                "objeto": "cell phone",
                "confianca": 0.78,
                "coordenadas": [600.0, 100.0, 800.0, 400.0],
                "ponto_clique": {"x": 700, "y": 250, "x_norm": 0.7, "y_norm": 0.5},
            },
        ],
        "textos_lidos": [
            {
                "tipo": "texto",
                "texto": "Notebook Gamer RTX4090",
                "confianca": 0.98,
                "coordenadas": [120.0, 20.0, 480.0, 46.0],
                "ponto_clique": {"x": 300, "y": 33, "x_norm": 0.3, "y_norm": 0.066},
            },
            {
                "tipo": "texto",
                "texto": "Comprar Agora",
                "confianca": 0.96,
                "coordenadas": [750.0, 420.0, 950.0, 480.0],
                "ponto_clique": {"x": 850, "y": 450, "x_norm": 0.85, "y_norm": 0.9},
            },
        ],
        "alvos_clique": [
            {
                "tipo": "objeto",
                "rotulo": "laptop",
                "confianca": 0.91,
                "coordenadas": [100.0, 50.0, 500.0, 350.0],
                "ponto_clique": {"x": 300, "y": 200, "x_norm": 0.3, "y_norm": 0.4},
            },
            {
                "tipo": "objeto",
                "rotulo": "cell phone",
                "confianca": 0.78,
                "coordenadas": [600.0, 100.0, 800.0, 400.0],
                "ponto_clique": {"x": 700, "y": 250, "x_norm": 0.7, "y_norm": 0.5},
            },
            {
                "tipo": "texto",
                "rotulo": "Notebook Gamer RTX4090",
                "confianca": 0.98,
                "coordenadas": [120.0, 20.0, 480.0, 46.0],
                "ponto_clique": {"x": 300, "y": 33, "x_norm": 0.3, "y_norm": 0.066},
            },
            {
                "tipo": "texto",
                "rotulo": "Comprar Agora",
                "confianca": 0.96,
                "coordenadas": [750.0, 420.0, 950.0, 480.0],
                "ponto_clique": {"x": 850, "y": 450, "x_norm": 0.85, "y_norm": 0.9},
            },
        ],
    }


def test_analisar_imagem_url_arquivo_bytes_e_base64(tmp_path):
    chamadas = []

    class FakeClient:
        def predict(self, entrada, api_name="/predict"):
            chamadas.append((entrada, api_name))
            return _mock_yolo_ocr_payload()

    factory = lambda url, timeout: FakeClient()

    # 1. URL
    res_url = vision_service.analisar_imagem(
        "https://exemplo.com/setup.jpg", client_factory=factory, retries=1
    )
    assert res_url["status"] == "sucesso"
    assert res_url["dimensoes"] == {"largura": 1000, "altura": 500}
    assert res_url["total_objetos"] == 2
    assert res_url["total_textos"] == 2
    assert "RTX4090" in res_url["texto_extraido"]
    assert len(res_url["alvos_clique"]) == 4

    # 2. Arquivo local
    img_file = tmp_path / "mesa.png"
    img_file.write_bytes(PNG_1X1)
    res_file = vision_service.analisar_imagem(img_file, client_factory=factory, retries=1)
    assert res_file["status"] == "sucesso"
    assert res_file["origem"] == "mesa.png"

    # 3. Bytes brutos
    res_bytes = vision_service.analisar_imagem(PNG_1X1, client_factory=factory, retries=1)
    assert res_bytes["status"] == "sucesso"
    assert res_bytes["total_objetos"] == 2

    # 4. Data URI Base64
    b64_uri = "data:image/png;base64," + base64.b64encode(PNG_1X1).decode("ascii")
    res_b64 = vision_service.analisar_imagem(b64_uri, client_factory=factory, retries=1)
    assert res_b64["status"] == "sucesso"
    assert len(chamadas) == 4


def test_ler_fontes_e_encontrar_coordenada_clique():
    factory = lambda url, timeout: type(
        "Fake", (), {"predict": lambda self, e, api_name="/predict": _mock_yolo_ocr_payload()}
    )()

    # 1. Leitura de fontes/textos na imagem
    ocr = vision_service.ler_fontes_imagem(
        "https://exemplo.com/banner.png", client_factory=factory, retries=1
    )
    assert ocr["status"] == "sucesso"
    assert ocr["total_textos"] == 2
    assert ocr["texto_extraido"] == "Notebook Gamer RTX4090 Comprar Agora"
    assert ocr["textos_lidos"][1]["ponto_clique"] == {"x": 850, "y": 450, "x_norm": 0.85, "y_norm": 0.9}

    # 2. Busca coordenada de clique por TEXTO lido (botão "Comprar Agora")
    clique_txt = vision_service.encontrar_coordenada_clique(
        "https://exemplo.com/banner.png", "Comprar Agora", client_factory=factory, retries=1
    )
    assert clique_txt is not None
    assert clique_txt["tipo"] == "texto"
    assert clique_txt["rotulo"] == "Comprar Agora"
    assert clique_txt["x"] == 850 and clique_txt["y"] == 450
    assert clique_txt["x_norm"] == 0.85 and clique_txt["y_norm"] == 0.9

    # 3. Busca coordenada de clique por OBJETO do YOLO ("laptop")
    clique_obj = vision_service.encontrar_coordenada_clique(
        "https://exemplo.com/banner.png", "laptop", client_factory=factory, retries=1
    )
    assert clique_obj is not None
    assert clique_obj["tipo"] == "objeto"
    assert clique_obj["x"] == 300 and clique_obj["y"] == 200
    assert clique_obj["x_norm"] == 0.3 and clique_obj["y_norm"] == 0.4


def test_clicar_alvo_tela_integra_com_remoto(monkeypatch):
    comandos_executados = []
    monkeypatch.setattr(
        pc_agent.remoto,
        "executar",
        lambda cmd, autorizado=False: comandos_executados.append((cmd, autorizado)) or {"ok": True, "kind": cmd["kind"]},
    )
    res = pc_agent.clicar_alvo_tela(
        "Comprar Agora",
        imagem=_mock_yolo_ocr_payload(),
        autorizado=True,
    )
    assert res["ok"] is True
    assert res["alvo"] == "Comprar Agora"
    assert res["coordenada"] == {"x": 850, "y": 450, "x_norm": 0.85, "y_norm": 0.9}
    assert comandos_executados == [({"kind": "click", "x": 0.85, "y": 0.9}, True)]


def test_analisar_imagem_retry_apos_hibernacao():
    tentativas = []

    class FlakySpaceClient:
        def predict(self, entrada, api_name="/predict"):
            tentativas.append(api_name)
            if len(tentativas) < 2:
                raise RuntimeError("Space waking up from hibernation (503)")
            return _mock_yolo_ocr_payload()

    res = vision_service.analisar_imagem(
        "https://exemplo.com/foto.png",
        client_factory=lambda url, timeout: FlakySpaceClient(),
        retries=3,
        backoff_s=0.01,
    )
    assert res["status"] == "sucesso"
    assert len(tentativas) == 2
    assert "RTX4090" in res["texto_extraido"]


def test_integracao_fluxo_pesquisa_e_chat_vexx(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / "vision_chat.sqlite")
    try:
        analisadas = []
        consultas_pesquisa = []

        def fake_analisar(texto, contexto_local=None, **kwargs):
            imgs = vision_service.extrair_imagens_do_texto(texto, contexto_local)
            analisadas.extend(imgs)
            return [dict(_mock_yolo_ocr_payload(), origem=imgs[0])] if imgs else []

        def fake_pesquisa_rapida(db_arg, owner_arg, consulta_arg, *args, **kwargs):
            consultas_pesquisa.append(consulta_arg)
            return {
                "fontes": [
                    {
                        "id": "S1",
                        "titulo": "Análise de Setup Notebook RTX4090",
                        "url": "https://exemplo.com/artigo-setup",
                        "dominio": "exemplo.com",
                        "status": "aberta",
                        "trecho": "Comparativo de laptop RTX4090 e cell phone.",
                    }
                ],
                "etapas": ["busca: 1 resultado"],
                "estado": "ok",
            }

        monkeypatch.setattr(vision_service, "analisar_imagens_contexto", fake_analisar)
        monkeypatch.setattr(pc_agent.research, "pesquisa_rapida", fake_pesquisa_rapida)

        cfg = {
            "model": "test",
            "context": 10,
            "system": "Sistema Vexx AI.",
            "memoria_global": True,
            "pesquisa_web": True,
        }
        prompt = "Pesquise informações sobre os equipamentos desta foto: https://exemplo.com/meu-setup.jpg"
        messages, extras = pc_agent.ai_montar_mensagens(
            db, "conv-visao", cfg, prompt, owner="local"
        )

        # 1. A imagem foi processada pelo YOLO + OCR primeiro
        assert analisadas == ["https://exemplo.com/meu-setup.jpg"]
        assert "vision" in extras["ferramentas_usadas"]
        assert "RTX4090" in extras["texto_extraido_visao"]
        assert len(extras["alvos_clique_visao"]) == 4

        # 2. A consulta de pesquisa recebeu tanto objetos quanto o texto lido nas fontes
        assert len(consultas_pesquisa) == 1
        assert "laptop" in consultas_pesquisa[0]
        assert "RTX4090" in consultas_pesquisa[0]

        # 3. O contexto do LLM recebeu tags_busca, texto_extraido e coordenadas de clique
        sistema = messages[0]["content"]
        assert "ANÁLISE VISUAL (VEXX-AI Vision API / YOLOv8 + RapidOCR" in sistema
        assert "Notebook Gamer RTX4090 Comprar Agora" in sistema
        assert "clique=(850, 450 | norm=0.85, 0.9)" in sistema
    finally:
        db.close()


def test_ai_request_aceita_campo_image():
    req = server.AIRequest(
        message_id="msg-vision-0001",
        conversation_id="conv-001",
        text="O que há nesta imagem?",
        image="https://exemplo.com/item.png",
    )
    assert req.image == "https://exemplo.com/item.png"
    ctx = pc_agent._contexto_local_seguro(req.model_dump())
    assert ctx.get("image") == "https://exemplo.com/item.png"
    assert vision_service.extrair_imagens_do_texto(req.text, ctx) == ["https://exemplo.com/item.png"]
