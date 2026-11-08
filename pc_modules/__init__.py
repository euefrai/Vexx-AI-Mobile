"""Pacote modular do agente local do PC (pc_agent)."""
from pc_modules import (
    db_core, memory_store, calendar_projects, intents_jdui, context_providers, study_lifecycle,
    research_commands, visual_fences, ai_pipeline, research_jobs, rpc_loop,
)

# Conecta referências cruzadas entre módulos na carga do pacote.
memory_store.CONFIRM_RE = calendar_projects.CONFIRM_RE
memory_store.atualizar_evento = calendar_projects.atualizar_evento
memory_store.confirmar_pendencia = calendar_projects.confirmar_pendencia
memory_store.descartar_pendencia = calendar_projects.descartar_pendencia
memory_store.pendencias = calendar_projects.pendencias
memory_store.proximos_eventos = calendar_projects.proximos_eventos
context_providers.ESTUDO_TERMOS = study_lifecycle.ESTUDO_TERMOS
context_providers._JOB_START_RE = research_commands._JOB_START_RE
context_providers.enviar_ws = ai_pipeline.enviar_ws
context_providers.linha_desempenho = study_lifecycle.linha_desempenho
study_lifecycle._texto_seguro = ai_pipeline._texto_seguro
research_commands.iniciar_job_bg = research_jobs.iniciar_job_bg
research_commands.rjob_start = research_jobs.rjob_start
