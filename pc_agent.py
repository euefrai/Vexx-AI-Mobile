"""PC agent (Windows): connects OUTBOUND to the Render relay, stores messages
in local SQLite, and answers via local Hermes CLI. Browser never reaches the PC.

Arquitetura modularizada em `pc_modules/`:
- `db_core.py` ............ configuração, SQLite/migrações/FTS e geração base (`tentar_modelos`);
- `memory_store.py` ....... memória persistente, FTS, contexto temporal/local e comandos;
- `calendar_projects.py` .. agenda em português, candidatos, projetos e aprendizado contínuo;
- `intents_jdui.py` ....... classificadores de intenção e sintetizadores JDUI;
- `context_providers.py` .. montagem de mensagens/orçamento, fontes, provedores e tela/input remoto;
- `study_lifecycle.py` .... ciclo de preparo/continuação de IA e sintetizadores de estudo;
- `research_commands.py` .. comandos de pesquisa, tabular, qualidade, shopping e validação;
- `visual_fences.py` ...... fences visuais JDUI, dados ao vivo e modelos 3D;
- `ai_pipeline.py` ........ guarda de stream, `ai_completa` e `ai_stream_worker`;
- `research_jobs.py` ...... jobs de pesquisa profunda em background e recuperação;
- `rpc_loop.py` ........... loop WebSocket RPC (`run`, incluindo `conv_forget`).

Todos os símbolos permanecem acessíveis em `pc_agent.<nome>` e qualquer
atribuição (`pc_agent.<nome> = ...` ou `monkeypatch.setattr`) é propagada
automaticamente para os submódulos.
"""
import sys
import types

import pc_modules
from pc_modules import (
    db_core, memory_store, calendar_projects, intents_jdui, context_providers, study_lifecycle,
    research_commands, visual_fences, ai_pipeline, research_jobs, rpc_loop,
)

import conversation_followups  # noqa: F401
import docs_agent  # noqa: F401
import env_local  # noqa: F401
import evidence_graph as evgraph  # noqa: F401
import files_agent  # noqa: F401
import hermes_bridge  # noqa: F401
import inference_status  # noqa: F401
import intent  # noqa: F401
import jdui  # noqa: F401
import json  # noqa: F401
import julia_auth as JULIA_auth  # noqa: F401
import learning  # noqa: F401
import live_data  # noqa: F401
import logging  # noqa: F401
import model3d  # noqa: F401
import model3d_research  # noqa: F401
import os  # noqa: F401
import providers  # noqa: F401
import query_intelligence  # noqa: F401
import random  # noqa: F401
import re  # noqa: F401
import remote_access  # noqa: F401
import remoto  # noqa: F401
import research  # noqa: F401
import research_agents  # noqa: F401
import shlex  # noqa: F401
import shopping  # noqa: F401
import sqlite3  # noqa: F401
import subprocess  # noqa: F401
import sys  # noqa: F401
import threading  # noqa: F401
import time  # noqa: F401
import tool_protocol  # noqa: F401
import unicodedata  # noqa: F401
import uuid  # noqa: F401
import vision_service  # noqa: F401
import workspace_store  # noqa: F401

from assistant_identity import (
    CONVERSATION_NAME, limitar_afirmacoes_nao_suportadas, OFFICIAL_NAME,
    pergunta_identidade_produto, resposta_identidade_produto, system_with_identity,
)  # noqa: F401
from concurrent.futures import ThreadPoolExecutor  # noqa: F401
from datetime import datetime, timedelta, timezone  # noqa: F401
from pathlib import Path  # noqa: F401
from urllib.parse import urlparse  # noqa: F401
from websockets.exceptions import ConnectionClosed, InvalidStatus  # noqa: F401
from websockets.sync.client import connect  # noqa: F401
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: F401
from pc_modules.db_core import (
    _BOOT_ISO, _BOOT_MONO, _colunas, _criar_fts_memorias, _ensure_owner_coluna, _fts_sync,
    _lista_fallbacks, _memoria_v41, _migrar_ai_requests_por_dono, _migrar_memories_por_dono,
    _migrar_messages_por_dono, _REVISAO_CACHE, _SCREEN_POOL, _SCREEN_SLOT, _SINT_POOL,
    _sintetizar_isolado, agora_iso, ai_config, configurar_log_persistente, database_path,
    DONO_PADRAO, dono_valido, gerar_stream, gerar_texto, hello_agente, list_messages, log,
    modelos_tentativa, open_db, persist_messages, revisao_agente, sqlite_integro,
    SYSTEM_PADRAO,
)  # noqa: F401
from pc_modules.memory_store import (
    _contexto_local_seguro, _data_local, _instrucoes_contexto_local, _normalizar_temporal,
    _resposta_temporal_direta, _RX_EVENTO_CMD, _SAUDACOES_VOCATIVO, _tokens_memoria,
    aprendizado_ativo, buscar_fts, cmd_identidade, data_curta, definir_aprendizado,
    guardar_fato, interpretar_comando_memoria, lembrancas_relevantes, ler_memorias,
    memoria_global, memorias_relevantes, NOMES_ALHEIOS, PALAVRAS_VAZIAS_MEMORIA, proveniencia,
    registrar_memoria, salvar_fatos, SENSIVEIS, STATUS_MEMORIA, TIPOS_MEMORIA,
)  # noqa: F401
from pc_modules.calendar_projects import (
    _consolidar_memorias, _projetos_relevantes, _trechos_projeto, _ultimas_de_conv,
    analisar_memoria, aprender_com_conversa, atualizar_evento, bloco_projetos, CONFIRM_RE,
    confirmar_pendencia, data_br, descartar_pendencia, DIAS_PT, doc_mencionado, eh_sensivel,
    extrair_candidatos, listar_conversas, MESES_PT, ORCAMENTO_MEMORIA_CHARS,
    ORCAMENTO_PROJETO_CHARS, parse_data, pendencias, proximos_eventos, registrar_evento,
)  # noqa: F401
from pc_modules.intents_jdui import (
    _ALVO_ARQUIVO_RE, _entidades_factuais, _fence_quiz, _indice_resposta, _limpa_opcao,
    _MEMORIA_GATILHOS, _opcoes_inline, _RX_FACTUAL_CODE, _RX_FACTUAL_COMPARE,
    _RX_FACTUAL_CREATIVE, _RX_FACTUAL_DOC, _RX_FACTUAL_DOC_ACT, _RX_FACTUAL_ENTITY,
    _RX_FACTUAL_HISTORY, _RX_FACTUAL_HOW, _RX_FACTUAL_HOWTO, _RX_FACTUAL_IDENTITY,
    _RX_FACTUAL_INSTRUCTION, _RX_FACTUAL_LOCAL, _RX_FACTUAL_MATH, _RX_FACTUAL_META,
    _RX_FACTUAL_NO_SEARCH, _RX_FACTUAL_NUMBER, _RX_FACTUAL_PERSONAL, _RX_FACTUAL_RECOMMEND,
    _RX_FACTUAL_STRONG_Q, _RX_FACTUAL_SUMMARY, _RX_FACTUAL_TALK, _RX_FACTUAL_TIME,
    _RX_FACTUAL_VERB, _RX_FACTUAL_WHAT, _RX_FACTUAL_WHY, _sem_acentos_factual,
    _sintetizar_jdui_llm, _VERBO_ARQUIVO_RE, APROFUNDADA_TRIGGERS,
    classificar_intencao_factual, extrair_checklist, extrair_quiz_codigo, extrair_quiz_texto,
    intencao_factual, intencao_imagem, intencao_pesquisa, intencao_pesquisa_aprofundada,
    intencao_widget, JDUI_CATALOGO, JDUI_SINTETIZAR, JULIAPresentationEngine, PEDIDO_CODIGO_RE,
    quer_criar_arquivo, REGRA_ARQUIVO, sintetizar_calculadora, sintetizar_jdui,
    termos_memoria_pesquisa, TERMOS_PESQUISA, ultimos_blocos_jdui,
)  # noqa: F401
from pc_modules.context_providers import (
    _apagar_todos_dados, _aplicar_arquivos_gerados, _IMG_MD, _ja_tem_fontes_markdown,
    _ORIGINAIS_PROVEDOR, _resposta_input_locked, _RX_CITACAO_FONTE, _RX_FONTES_HEAD,
    _RX_IMG_PLACEHOLDER, _RX_LINK_LINHA, _tem_citacao_inline, _validar_chave_provedor,
    ai_estado, ai_marcar, ai_montar_mensagens, anexar_fontes, aplicar_orcamento,
    contexto_conversa, definir_chave_provedor, dono_bloqueado, imagens_primeiro,
    ORCAMENTO_CHARS, REGRAS_CONFIANCA, REGRAS_ESCOPO_FORMATO, REGRAS_SHOPPING,
    remover_chave_provedor, resposta_input, resposta_screen, submit_screen,
)  # noqa: F401
from pc_modules.study_lifecycle import (
    _ai_preparar, _AI_PREPARE_LOCK, ai_continuar, ai_guardar_resposta, ai_preparar, ai_resetar,
    AULA_TRIGGERS, ESTUDO_TERMOS, EVOLUCAO_TRIGGERS, GRAFICO_TRIGGERS, intencao_aula,
    intencao_grafico_evolucao, intencao_prova, intencao_reforco, linha_desempenho,
    PROVA_TRIGGERS, REFORCO_TRIGGERS, sintetizar_aula, sintetizar_grafico_evolucao,
    sintetizar_prova, sintetizar_reforco,
)  # noqa: F401
from pc_modules.research_commands import (
    _cmd_analisar_tabular, _cmd_intervencao, _CONTINUAR_RE, _evidencias_verificaveis,
    _fallback_dados_recuperados, _fallback_sem_inferencia, _filtrar_usados_restricao,
    _JOB_START_RE, _pesquisa_sem_evidencia, _resumo_onde_paramos, _resumo_projeto,
    _RX_JDUIF_BLOCO, _shopping_aplicar, _shopping_executar, _shopping_resposta_factual,
    _shopping_sem_ofertas, _texto_followup_sem_contexto, _ultimo_job, _validar_comparacoes,
    _validar_resposta, cmd_pesquisa, cmd_projeto, cmd_qualidade,
)  # noqa: F401
from pc_modules.visual_fences import (
    _num_celula, cmd_dados_atuais, cmd_model3d, fence_de_evidencias, fence_de_fontes,
    fence_de_grafo, fence_de_pesquisa, fence_tabela_para_grafico, fence_transformacao_visual,
    intencao_transformar_pesquisa, TRANSFORM_FORMATOS, TRANSFORM_VERBOS,
)  # noqa: F401
from pc_modules.ai_pipeline import (
    _complemento_stream, _GuardaStreamResposta, _texto_seguro, ai_completa, ai_resposta_direta,
    ai_stream_worker, enviar_ws, ENVIO_LOCK, SessaoStream,
)  # noqa: F401
from pc_modules.research_jobs import (
    _db_job, _job_tailer, _job_worker, _persistir_resultado_pesquisa, _research_writer,
    iniciar_job_bg, JOBS_BG, JOBS_BG_LOCK, MAX_JOBS_SIMULTANEOS, recover_interrupted_ai,
    recover_interrupted_research, rjob_cancel, rjob_delete, rjob_evidence, rjob_hypotheses,
    rjob_intervene, rjob_list, rjob_pause, rjob_report, rjob_start, rjob_status,
)  # noqa: F401
from pc_modules.rpc_loop import run  # noqa: F401


_MODULOS_COMPARTILHADOS = (db_core, memory_store, calendar_projects, intents_jdui, context_providers, study_lifecycle, research_commands, visual_fences, ai_pipeline, research_jobs, rpc_loop)


class _PcAgentModule(types.ModuleType):
    """Propaga `pc_agent.<nome> = valor` para todos os submódulos de `pc_modules`."""

    def __setattr__(self, nome, valor):
        for modulo in _MODULOS_COMPARTILHADOS:
            if nome in modulo.__dict__:
                setattr(modulo, nome, valor)
        super().__setattr__(nome, valor)


sys.modules[__name__].__class__ = _PcAgentModule


if __name__ == "__main__":
    import agent_runtime
    agent_runtime.launch(sys.modules[__name__])
