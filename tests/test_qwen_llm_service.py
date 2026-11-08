"""Testes do serviço do modelo prioritário Qwen2.5-3B-Instruct (VEXX-AI)."""
import pytest
from unittest.mock import patch, MagicMock

import qwen_llm_service as qwen
import providers


def test_gerar_resposta_qwen_sucesso():
    fake_api_response = {
        "status": "sucesso",
        "modelo": "Qwen2.5-3B-Instruct-VEXX",
        "resposta": "Esta é a resposta detalhada e precisa gerada pelo Qwen2.5-3B.",
        "tool_calls": [],
        "queries_pesquisa": ["pesquisa mercado tech 2026"],
        "uso": {"prompt_tokens": 45, "completion_tokens": 30, "total_tokens": 75}
    }

    with patch("qwen_llm_service._chamar_api_qwen_com_retry", return_value=fake_api_response):
        res = qwen.gerar_resposta_qwen(
            mensagens=[{"role": "user", "content": "Analise o mercado de tecnologia."}],
            contexto_pesquisa="Dados de crescimento de 20% no setor.",
            temperatura=0.3
        )

    assert res["status"] == "sucesso"
    assert res["modelo"] == "Qwen2.5-3B-Instruct-VEXX"
    assert "resposta detalhada" in res["resposta"]
    assert len(res["queries_pesquisa"]) == 1
    assert res["queries_pesquisa"][0] == "pesquisa mercado tech 2026"


def test_planejar_pesquisa_qwen_com_contexto_visao():
    fake_response = {
        "status": "sucesso",
        "modelo": "Qwen2.5-3B-Instruct-VEXX",
        "resposta": "Pesquisando os dados do produto.",
        "tool_calls": [],
        "queries_pesquisa": [
            "RTX 4060 16GB preco brasil",
            "RTX 4060 benchmark consumo"
        ],
        "uso": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35}
    }

    with patch("qwen_llm_service._chamar_api_qwen_com_retry", return_value=fake_response):
        queries = qwen.planejar_pesquisa_qwen(
            pergunta="Qual o valor desta placa de vídeo?",
            contexto_visao="Tags: gpu, graphics card | OCR: RTX 4060 16GB GDDR6"
        )

    assert len(queries) == 2
    assert "RTX 4060 16GB preco brasil" in queries
    assert "RTX 4060 benchmark consumo" in queries


def test_decidir_ferramenta_qwen():
    fake_tool_call = {
        "name": "clicar_por_visao",
        "arguments": {"alvo": "Botão Comprar", "confirmar": True}
    }
    fake_response = {
        "status": "sucesso",
        "modelo": "Qwen2.5-3B-Instruct-VEXX",
        "resposta": "Executando ação de clique.",
        "tool_calls": [fake_tool_call],
        "queries_pesquisa": [],
        "uso": {}
    }

    ferramentas = [
        {"name": "pesquisar_web", "description": "Pesquisa na web"},
        {"name": "clicar_por_visao", "description": "Clica em elemento na tela"}
    ]

    with patch("qwen_llm_service._chamar_api_qwen_com_retry", return_value=fake_response):
        acao = qwen.decidir_ferramenta_qwen(
            pergunta="Clique no botão Comprar na tela",
            ferramentas_disponiveis=ferramentas
        )

    assert acao is not None
    assert acao["name"] == "clicar_por_visao"
    assert acao["arguments"]["alvo"] == "Botão Comprar"


def test_qwen_prioritario_numero_um_no_catalogo():
    # Verifica que o Qwen2.5-3B é o modelo #1 absoluto e padrão do catálogo
    catalogo = providers.listar_tudo()

    assert catalogo["default"] == "vexx-qwen-2.5-3b"
    assert catalogo["models"][0] == "vexx-qwen-2.5-3b"
    assert catalogo["items"][0]["id"] == "vexx-qwen-2.5-3b"
    assert catalogo["items"][0]["provider"] == "vexx"
    assert "Prioritário" in catalogo["items"][0]["label"]

    # Verifica suporte a chat sem erro de seleção
    assert providers.supports_chat("vexx-qwen-2.5-3b") is True
    assert providers.selection_error("vexx-qwen-2.5-3b") is None

    # Verifica roteamento da divisão
    prov, mid = providers.dividir("vexx-qwen-2.5-3b")
    assert prov == "vexx"
    assert mid == "vexx-qwen-2.5-3b"


def test_fallback_hibernacao_space():
    # Simula erro de conexão (Space hibernando / timeout total)
    fake_erro = {
        "status": "erro",
        "mensagem": "HTTP 503 Service Unavailable / Space hibernating",
        "modelo": "Qwen2.5-3B-Instruct-VEXX",
        "resposta": "",
        "tool_calls": [],
        "queries_pesquisa": [],
        "uso": {}
    }

    with patch("qwen_llm_service._chamar_api_qwen_com_retry", return_value=fake_erro):
        res = qwen.gerar_resposta_qwen(
            mensagens=[{"role": "user", "content": "Qual a previsão do tempo?"}],
            contexto_pesquisa="Tempo ensolarado com 26 graus."
        )

    # Não deve quebrar; retorna fallback transparente
    assert res["status"] == "fallback"
    assert "Tempo ensolarado" in res["resposta"]
    assert res["modelo"] == "Qwen2.5-3B-Instruct-VEXX"
