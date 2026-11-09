"""Testes unitários da migração para Qwen 2.5 3B, Tool Calling e Mapas 3D Temáticos."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import model3d
import model3d_generative
from pc_modules import db_core, tool_execution
import providers


def test_modelo_padrao_migrado_para_qwen_3b():
    """Valida que o modelo padrão do sistema e dos provedores é o Qwen 2.5 3B."""
    cfg = db_core.ai_config()
    assert cfg["model"] == "vexx-qwen-2.5-3b"
    assert db_core.FALLBACKS_GRATIS_PADRAO[0] == "vexx-qwen-2.5-3b"

    catalogo = providers.listar_tudo()
    assert catalogo["default"] == "vexx-qwen-2.5-3b"
    assert catalogo["models"][0] == "vexx-qwen-2.5-3b"
    assert any(p["id"] == "vexx" and "3B" in p["label"] for p in catalogo["providers"])


def test_extrair_chamadas_tool_call():
    """Valida a extração de <tool_call> e ```tool_calls do conteúdo do modelo."""
    texto_tag = (
        "Vou verificar suas notificações agora.\n"
        "<tool_call>\n"
        "{\"name\": \"navegador_instagram\", \"arguments\": {\"acao\": \"verificar_mensagens\"}}\n"
        "</tool_call>\n"
        "Aguarde um instante."
    )
    chamadas = tool_execution.extrair_chamadas_tool_call(texto_tag)
    assert len(chamadas) == 1
    assert chamadas[0]["name"] == "navegador_instagram"
    assert chamadas[0]["arguments"]["acao"] == "verificar_mensagens"

    texto_code = (
        "Gerando modelo 3D.\n"
        "```tool_calls\n"
        "[{\"name\": \"gerar_modelo_3d\", \"arguments\": {\"prompt\": \"base lunar\", \"tipo\": \"mapa\"}}]\n"
        "```"
    )
    chamadas2 = tool_execution.extrair_chamadas_tool_call(texto_code)
    assert len(chamadas2) == 1
    assert chamadas2[0]["name"] == "gerar_modelo_3d"
    assert chamadas2[0]["arguments"]["tipo"] == "mapa"


def test_executar_ferramenta_gerar_modelo_3d():
    """Valida a execução de ferramenta para geração de mapa 3D validado."""
    res = tool_execution.executar_ferramenta("gerar_modelo_3d", {"prompt": "base planetaria lunar", "tipo": "mapa"})
    assert res["status"] == "sucesso"
    assert res["tipo"] == "model3d"
    assert "````model3d" in res["fence"]

    # Extrai o json da fence e valida no schema model3d
    json_str = res["fence"].split("````model3d\n")[1].split("\n````")[0]
    dados = json.loads(json_str)
    validado = model3d.validate(dados)
    assert validado["id"].startswith("dev-mapa-")
    assert len(validado["objects"]) >= 5


def test_processar_e_executar_chamadas_substitui_tags():
    """Valida que blocos de tool call são executados e formatados na resposta final."""
    texto = (
        "Processando solicitação.\n"
        "<tool_call>\n"
        "{\"name\": \"gerar_modelo_3d\", \"arguments\": {\"prompt\": \"datacenter de IA com racks refrigerados\", \"tipo\": \"mapa\"}}\n"
        "</tool_call>"
    )
    final, resultados = tool_execution.processar_e_executar_chamadas(texto)
    assert "<tool_call>" not in final
    assert "</tool_call>" not in final
    assert "````model3d" in final
    assert len(resultados) == 1
    assert resultados[0]["resultado"]["tipo"] == "model3d"


def test_mapas_tematicos_diversos_validacao():
    """Valida todos os novos arquétipos de mapas espaciais e layouts urbanos/tecnológicos."""
    temas = [
        ("Base Lunar em Marte com Domos", "lunar"),
        ("Datacenter de Supercomputação H100", "datacenter"),
        ("Hangar Aeroespacial de Lançamento", "hangar"),
        ("Cidade Inteligente e Monotrilho", "cidade"),
    ]
    for prompt_teste, chave in temas:
        cena = model3d_generative.gerar_mapa_3d(prompt_teste)
        valid = model3d.validate(cena)
        assert valid["id"].startswith("dev-mapa-")
        assert valid["objects"][0]["id"] == "piso_topografico"
        assert len(valid["objects"]) >= 5
        assert len(valid["steps"]) >= 3
