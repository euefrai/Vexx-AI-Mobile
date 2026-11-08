"""Testes unitários e de integração do módulo de Visão Computacional (YOLOv8 / Hugging Face Spaces)."""
from __future__ import annotations

import base64
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pc_agent
import server
import vision_service


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _mock_yolo_payload():
    return {
        "status": "sucesso",
        "total_objetos": 2,
        "tags_busca": "laptop, cell phone",
        "deteccoes": [
            {"objeto": "laptop", "confianca": 0.91, "coordenadas": [12.5, 30.0, 240.8, 198.4]},
            {"objeto": "cell phone", "confianca": 0.78, "coordenadas": [260.1, 80.2, 310.0, 175.6]},
        ],
    }


def test_analisar_imagem_url_arquivo_bytes_e_base64(tmp_path):
    chamadas = []

    class FakeClient:
        def predict(self, entrada, api_name="/predict"):
            chamadas.append((entrada, api_name))
            return _mock_yolo_payload()

    factory = lambda url, timeout: FakeClient()

    # 1. URL
    res_url = vision_service.analisar_imagem(
        "https://exemplo.com/setup.jpg", client_factory=factory, retries=1
    )
    assert res_url["status"] == "sucesso"
    assert res_url["tags_busca"] == "laptop, cell phone"
    assert len(res_url["deteccoes"]) == 2
    assert res_url["deteccoes"][0]["coordenadas"] == [12.5, 30.0, 240.8, 198.4]

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
    assert res_b64["tags_busca"] == "laptop, cell phone"
    assert len(chamadas) == 4


def test_analisar_imagem_retry_apos_hibernacao():
    tentativas = []

    class FlakySpaceClient:
        def predict(self, entrada, api_name="/predict"):
            tentativas.append(api_name)
            if len(tentativas) < 2:
                raise RuntimeError("Space waking up from hibernation (503)")
            return _mock_yolo_payload()

    res = vision_service.analisar_imagem(
        "https://exemplo.com/foto.png",
        client_factory=lambda url, timeout: FlakySpaceClient(),
        retries=3,
        backoff_s=0.01,
    )
    assert res["status"] == "sucesso"
    assert len(tentativas) == 2
    assert res["tags_busca"] == "laptop, cell phone"


def test_integracao_fluxo_pesquisa_e_chat_vexx(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / "vision_chat.sqlite")
    try:
        analisadas = []
        consultas_pesquisa = []

        def fake_analisar(texto, contexto_local=None, **kwargs):
            imgs = vision_service.extrair_imagens_do_texto(texto, contexto_local)
            analisadas.extend(imgs)
            return [dict(_mock_yolo_payload(), origem=imgs[0])] if imgs else []

        def fake_pesquisa_rapida(db_arg, owner_arg, consulta_arg, *args, **kwargs):
            consultas_pesquisa.append(consulta_arg)
            return {
                "fontes": [
                    {
                        "id": "S1",
                        "titulo": "Análise de Setup Notebook e Smartphone",
                        "url": "https://exemplo.com/artigo-setup",
                        "dominio": "exemplo.com",
                        "status": "aberta",
                        "trecho": "Comparativo de laptop e cell phone para produtividade.",
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

        # 1. A imagem foi processada pelo YOLO primeiro
        assert analisadas == ["https://exemplo.com/meu-setup.jpg"]
        assert "vision" in extras["ferramentas_usadas"]
        assert extras["tags_busca_visao"] == "laptop, cell phone"

        # 2. A consulta de pesquisa recebeu as tags_busca do YOLO
        assert len(consultas_pesquisa) == 1
        assert "laptop" in consultas_pesquisa[0]
        assert "cell phone" in consultas_pesquisa[0]

        # 3. O contexto do LLM recebeu as tags_busca e as coordenadas [x1, y1, x2, y2]
        sistema = messages[0]["content"]
        assert "ANÁLISE VISUAL (VEXX-AI Vision API / YOLOv8" in sistema
        assert "laptop, cell phone" in sistema
        assert "[12.5, 30.0, 240.8, 198.4]" in sistema
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
