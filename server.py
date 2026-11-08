"""Vexx AI relay: authentication + ephemeral WebSocket RPC only.
No chat history or SQLite file is stored on Render.

Ponto de entrada (`uvicorn server:app`). Este módulo só compõe a aplicação:

- relay_core.py ........ configuração, app FastAPI, middlewares, sessão/CSRF,
                         revogação, rate limit e AgentRelay;
- routers/<domínio>.py . uma APIRouter por domínio (auth, admin, sync, docs,
                         memories, ai, remote, learn, research, agent, public).

Compatibilidade: todos os nomes históricos continuam acessíveis como
`server.<nome>`, e atribuições como `server.relay = ...` (inclusive
`monkeypatch.setattr` nos testes) são propagadas aos módulos que compartilham
o mesmo objeto, como acontecia quando tudo vivia em um único arquivo.
Contratos preservados nos routers:
- `routers/sync_routes.py`: exclusão com tombstone (`conv_forget`);
- `routers/ai_routes.py` (`/api/ai/models`): filtra metadados seguros sem expor
  segredos (`"items": [{"id", "provider", "free"}]`,
  `"providers": [{k: p.get(k) for k in ("id", "label", "configured", "auth_error", "source")}]`).
"""
import sys
import types

import relay_core
from relay_core import *  # noqa: F401,F403 - superfície pública histórica (server.<nome>)
from relay_core import (
    _COMMIT_RE, _inteiro_limitado, _limite_tentativas, _limpa_tentativas,
    _monitor_agente_offline, _rate_limit,
)  # noqa: F401
from routers import (
    auth_routes, admin_routes, sync_routes, docs_routes, memories_routes, ai_routes,
    remote_routes, learn_routes, research_routes, agent_routes, public_routes,
)
from routers.auth_routes import (
    _auth_config_indisponivel, account_delete, account_me, account_password, auth_config,
    ExcluiConta, login, logout, register, Registro, session, TrocaSenha, ultima_auth_config,
)  # noqa: F401
from routers.admin_routes import (
    admin_audit, admin_config_get, admin_config_set, admin_create_invite, admin_create_user,
    admin_decide_reg, admin_delete_user, admin_invites, admin_quality_run, admin_quality_runs,
    admin_regs, admin_revoke_invite, admin_revoke_sessions, admin_set_limits, admin_set_role,
    admin_set_status, admin_uid, admin_users, AdminConfigSet, AdminCreateUser,
    AdminInviteCreate, AdminLimitsBody, AdminRegDecide, AdminRoleBody, AdminStatusBody,
    AdminUidBody,
)  # noqa: F401
from routers.sync_routes import (
    conversation_forget, conversations, export_xlsx, messages, status, sync_messages,
    ui_state_list, ui_state_save, UiStateBody, UiStateItem, workspace_sync,
)  # noqa: F401
from routers.docs_routes import (
    DocAsk, DocCompare, docs_compare, docs_delete, docs_list, docs_resumo, docs_search,
    docs_topicos, docs_upload, DocSearch, files_delete, files_download, files_list,
)  # noqa: F401
from routers.memories_routes import (
    memories_confirm, memories_forget, memories_full, memories_list, memories_update,
    memory_events, memory_settings_get, memory_settings_set, MemSettings, MemUpdate,
)  # noqa: F401
from routers.ai_routes import (
    ai_complete, ai_continue, ai_models, ai_regenerate, ai_stream, ai_stream_post, AIContinue,
    provider_key, ProviderKey,
)  # noqa: F401
from routers.remote_routes import (
    _remote_access_exchange, remote_access_request, remote_access_revoke, remote_access_status,
    remote_frame, remote_input, remote_input_batch, screen,
)  # noqa: F401
from routers.learn_routes import (
    _learn_erro, learn_answer, learn_assessment, learn_attempt, learn_avulso,
    learn_cards_create, learn_cards_due, learn_cards_review, learn_finish, learn_flag,
    learn_history, learn_lesson_create, learn_lesson_get, learn_lesson_section, learn_lessons,
    learn_mistakes, learn_plan_create, learn_plan_get, learn_plan_item, learn_plan_update,
    learn_plans, learn_recommend, learn_stats, LearnAnswerIn, LearnAttemptIn, LearnAvulsoIn,
    LearnCardsIn, LearnFinishIn, LearnFlagIn, LearnLessonIn, LearnLessonSectionIn, LearnPlanIn,
    LearnPlanItemIn, LearnPlanUpdateIn, LearnReviewIn,
)  # noqa: F401
from routers.research_routes import (
    _research_erro, research_cancel, research_delete, research_evidence, research_export,
    research_hypotheses, research_intervene, research_jobs, research_pause, research_report,
    research_start, research_status, research_stream, research_view, ResearchInterveneIn,
    ResearchJobIn, ResearchPauseIn, ResearchStartIn,
)  # noqa: F401
from routers.agent_routes import agent_ws  # noqa: F401
from routers.public_routes import (
    _public_file, three_engine_asset, trust_contato, trust_privacidade, trust_robots,
    trust_security_txt, trust_seguranca, trust_sitemap, trust_sobre, trust_termos,
)  # noqa: F401


# A ordem de registro preserva a precedência de rotas do monólito original.
for _modulo in (auth_routes, admin_routes, sync_routes, docs_routes, memories_routes,
                ai_routes, remote_routes, learn_routes, research_routes, agent_routes,
                public_routes):
    app.include_router(_modulo.router)


_AUSENTE = object()
_MODULOS_COMPARTILHADOS = (relay_core, auth_routes, admin_routes, sync_routes, docs_routes, memories_routes, ai_routes, remote_routes, learn_routes, research_routes, agent_routes, public_routes)


class _ServerModule(types.ModuleType):
    """Propaga `server.<nome> = valor` para os módulos que usam o mesmo objeto."""

    def __setattr__(self, nome, valor):
        atual = self.__dict__.get(nome, _AUSENTE)
        if atual is not _AUSENTE:
            for modulo in _MODULOS_COMPARTILHADOS:
                if modulo.__dict__.get(nome, _AUSENTE) is atual:
                    setattr(modulo, nome, valor)
        super().__setattr__(nome, valor)


sys.modules[__name__].__class__ = _ServerModule

import admin_http  # noqa: E402
admin_http.install(app, sys.modules[__name__])

# Public companions never receive the central inference agent's credential.
import companion_api  # noqa: E402
companion_hub = companion_api.install(sys.modules[__name__])

app.mount("/", StaticFiles(directory=str(ROOT / "public"), html=True), name="mobile-static")
