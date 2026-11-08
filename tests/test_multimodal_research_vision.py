"""Testes automatizados das melhorias de Pesquisa Profunda, Visão YOLO-World, Qwen e Localização de Alvos."""
from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

import vision_service
import qwen_llm_service
import agentic_deep_research


def test_sugerir_classes_visao_qwen_heuristica():
    """Testa se consultas em português extraem classes cirúrgicas para o YOLO-World v2."""
    res1 = qwen_llm_service.sugerir_classes_visao_qwen("quero encontrar um fone bluetooth e ver o preco")
    assert "headphone" in res1 or "earbuds" in res1
    assert "price" in res1

    res2 = qwen_llm_service.sugerir_classes_visao_qwen("clique no botao de comprar ou adicionar ao carrinho")
    assert "buy button" in res2 or "shopping cart" in res2


def test_analisar_imagem_com_classes_personalizadas():
    """Valida se classes_personalizadas aciona o endpoint /detectar_com_classes."""
    cliente_mock = MagicMock()
    cliente_mock.predict.return_value = {
        "status": "sucesso",
        "modelo": "YOLO-World v2 + RapidOCR",
        "dimensoes": {"largura": 1920, "altura": 1080},
        "total_objetos": 1,
        "total_textos": 0,
        "tags_busca": "blue headphones",
        "texto_extraido": "",
        "deteccoes": [
            {
                "tipo": "objeto",
                "objeto": "blue headphones",
                "confianca": 0.92,
                "coordenadas": [100, 200, 300, 400],
                "ponto_clique": {"x": 200, "y": 300, "x_norm": 0.1042, "y_norm": 0.2778},
            }
        ],
        "textos_lidos": [],
        "alvos_clique": [
            {
                "tipo": "objeto",
                "rotulo": "blue headphones",
                "confianca": 0.92,
                "coordenadas": [100, 200, 300, 400],
                "ponto_clique": {"x": 200, "y": 300, "x_norm": 0.1042, "y_norm": 0.2778},
            }
        ],
    }

    res = vision_service.analisar_imagem(
        "https://exemplo.com/fone.jpg",
        classes_personalizadas="blue headphones, earphones",
        client_factory=lambda *a, **k: cliente_mock,
    )

    assert res["status"] == "sucesso"
    assert res["total_objetos"] == 1
    assert res["deteccoes"][0]["objeto"] == "blue headphones"
    cliente_mock.predict.assert_called_once()
    args, kwargs = cliente_mock.predict.call_args
    assert "blue headphones" in args or kwargs.get("api_name") == "/detectar_com_classes"


def test_localizar_alvos_inteligente_ranqueamento(monkeypatch):
    """Valida o ranking de alvos visuais e coordenadas precisas de clique."""
    payload_mock = {
        "status": "sucesso",
        "dimensoes": {"largura": 1000, "altura": 1000},
        "total_objetos": 2,
        "total_textos": 2,
        "tags_busca": "headphone, keyboard",
        "texto_extraido": "Comprar Agora R$ 250",
        "alvos_clique": [
            {
                "tipo": "objeto",
                "rotulo": "headphone",
                "confianca": 0.88,
                "coordenadas": [100, 100, 300, 300],
                "ponto_clique": {"x": 200, "y": 200, "x_norm": 0.2, "y_norm": 0.2},
            },
            {
                "tipo": "texto",
                "rotulo": "Comprar Agora",
                "confianca": 0.95,
                "coordenadas": [500, 500, 700, 600],
                "ponto_clique": {"x": 600, "y": 550, "x_norm": 0.6, "y_norm": 0.55},
            },
        ],
    }
    monkeypatch.setattr(vision_service, "analisar_imagem", lambda *a, **k: payload_mock)

    loc_btn = vision_service.localizar_alvos_inteligente("fake_img", "comprar")
    assert loc_btn["status"] == "sucesso"
    assert loc_btn["total_alvos"] >= 1
    melhor = loc_btn["melhor_alvo"]
    assert melhor["rotulo"] == "Comprar Agora"
    assert melhor["tipo"] == "texto"
    assert melhor["x"] == 600
    assert melhor["y"] == 550

    loc_fone = vision_service.localizar_alvos_inteligente("fake_img", "headphone")
    assert loc_fone["melhor_alvo"]["rotulo"] == "headphone"
    assert loc_fone["melhor_alvo"]["x"] == 200


def test_clicar_alvo_tela_com_pyautogui(monkeypatch):
    """Valida se clicar_alvo_tela aciona pyautogui para cliques sincronizados em tempo real."""
    cliques_executados = []

    class FakePyAutoGUI:
        @staticmethod
        def size():
            return 1920, 1080

        @staticmethod
        def click(x, y):
            cliques_executados.append(("click", x, y))

    monkeypatch.setattr(vision_service, "localizar_alvos_inteligente", lambda *a, **k: {
        "status": "sucesso",
        "melhor_alvo": {
            "rotulo": "Botao Enviar",
            "tipo": "texto",
            "x": 960,
            "y": 540,
            "x_norm": 0.5,
            "y_norm": 0.5,
            "score": 100.0,
        }
    })

    import sys
    monkeypatch.setitem(sys.modules, "pyautogui", FakePyAutoGUI)

    res = vision_service.clicar_alvo_tela("Botao Enviar", imagem=None)
    assert res["ok"] is True
    assert res["metodo"] == "pyautogui"
    assert len(cliques_executados) == 1
    assert cliques_executados[0] == ("click", 960, 540)


def test_sintetizar_pesquisa_multimodal_qwen():
    """Valida síntese com links markdown e imagens de produtos/artigos."""
    fontes = [
        {
            "titulo": "Fone Bluetooth JBL 520BT Review",
            "url": "https://tech.com/jbl-520bt",
            "dominio": "tech.com",
            "trecho": "Excelente bateria de 57 horas e graves potentes por R$ 269.",
        },
        {
            "titulo": "Top Fones Bluetooth até R$ 300",
            "url": "https://reviews.com/top-fones",
            "dominio": "reviews.com",
            "trecho": "Comparativo completo com Edifier e QCY.",
        }
    ]
    imagens = [
        {"url": "https://tech.com/jbl520.jpg", "titulo": "JBL 520BT Preto"},
        {"url": "https://reviews.com/qcy.jpg", "titulo": "QCY T13 ANC"},
    ]

    res = qwen_llm_service.sintetizar_pesquisa_multimodal_qwen(
        "fone bluetooth até R$ 300",
        fontes=fontes,
        imagens=imagens,
        contexto_visao="Identificado fone supra-auricular preto com almofadas",
    )

    assert res["status"] == "sucesso"
    md = res["relatorio_markdown"]
    assert "https://tech.com/jbl-520bt" in md
    assert "![JBL 520BT Preto](https://tech.com/jbl520.jpg)" in md
    assert len(res["fontes"]) == 2
    assert len(res["imagens"]) == 2


def test_enriquecer_pesquisa_com_visao_qwen():
    """Valida se enriquecer_pesquisa_com_visao_qwen junta pergunta e visão."""
    dados_v = {
        "tags_busca": "mouse gamer, rgb keyboard",
        "texto_extraido": "DPI 16000 Sensor PixArt",
    }
    queries = qwen_llm_service.enriquecer_pesquisa_com_visao_qwen(
        "qual o preco desse mouse?",
        dados_visao=dados_v
    )
    assert len(queries) >= 1
    assert any("mouse" in q.lower() for q in queries)


def test_agentic_deep_research_decomposicao_com_qwen(monkeypatch):
    """Valida se decompose_complex_query utiliza o Qwen automaticamente."""
    chamadas_llm = []

    def mock_gerar_resposta(prompt, **kwargs):
        chamadas_llm.append(prompt)
        return {
            "status": "sucesso",
            "resposta": '["fone bluetooth bateria longa", "fone bluetooth ate 300 reais"]',
        }

    monkeypatch.setattr(qwen_llm_service, "gerar_resposta_qwen", mock_gerar_resposta)

    queries = agentic_deep_research.decompose_complex_query(
        "qual o melhor fone de ouvido bluetooth com bateria duradoura e cancelamento de ruido ate 300 reais?",
        mode="shopping"
    )

    assert len(chamadas_llm) == 1
    assert len(queries) == 2
    assert "fone bluetooth" in queries[0]
