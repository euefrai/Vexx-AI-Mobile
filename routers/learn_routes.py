"""Router: Estudos: avaliações, planos, flashcards e aulas."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from relay_core import erro_relay, relay, require_csrf, revogacao_ok, verify_session

router = APIRouter()

class LearnAttemptIn(BaseModel):
    assessment_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class LearnAnswerIn(BaseModel):
    attempt_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    question_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    resposta: str = Field(min_length=1, max_length=2000)


class LearnFinishIn(BaseModel):
    attempt_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class LearnAvulsoIn(BaseModel):
    titulo: str = Field(default="Quiz", max_length=160)
    assunto: str = Field(default="", max_length=120)
    certas: int = Field(ge=0, le=1000)
    total: int = Field(ge=1, le=1000)


def _learn_erro(result: dict) -> HTTPException:
    """learn_error do agente vira HTTP: bloqueada→403, ausente→404, resto→503."""
    codigo = result.get("codigo", "erro")
    if codigo == "bloqueada":
        return erro_relay(result, "Conta indisponível.")
    if codigo in ("ausente", "finalizada"):
        raise HTTPException(404 if codigo == "ausente" else 409,
                            result.get("error", "Não encontrado"))
    return HTTPException(503, result.get("error", "Aprendizado indisponível"))


@router.get("/api/learn/assessments/{aid}")
async def learn_assessment(request: Request, aid: str):
    """Prova sem gabarito (o gabarito só aparece na correção)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(aid) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "learn_get", "owner": dono, "id": aid},
                                  timeout=20.0)
    if result.get("type") != "learn_assessment":
        raise _learn_erro(result)
    return {"id": result["id"], "titulo": result.get("titulo", ""),
            "assunto": result.get("assunto", ""), "origem": result.get("origem", ""),
            "questions": result.get("questions", [])}


@router.post("/api/learn/attempts")
async def learn_attempt(request: Request, body: LearnAttemptIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_attempt", "owner": dono,
                                   "assessment_id": body.assessment_id}, timeout=20.0)
    if result.get("type") != "learn_attempt":
        raise _learn_erro(result)
    return {"id": result["id"], "assessment_id": result.get("assessment_id", "")}


@router.post("/api/learn/answer")
async def learn_answer(request: Request, body: LearnAnswerIn):
    """Correção objetiva determinística no PC; discursiva = avaliação assistida."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_answer", "owner": dono,
                                   "attempt_id": body.attempt_id,
                                   "question_id": body.question_id,
                                   "resposta": body.resposta}, timeout=20.0)
    if result.get("type") != "learn_answer":
        raise _learn_erro(result)
    saida = {"correta": result.get("correta")}
    if "avaliacao" in result:
        saida["avaliacao"] = result["avaliacao"]
        saida["aviso"] = result.get("aviso", "")
    return saida


@router.post("/api/learn/finish")
async def learn_finish(request: Request, body: LearnFinishIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_finish", "owner": dono,
                                   "attempt_id": body.attempt_id}, timeout=20.0)
    if result.get("type") != "learn_result":
        raise _learn_erro(result)
    return {"id": result["id"], "nota": result.get("nota", 0.0),
            "certas": result.get("certas", 0), "total": result.get("total", 0),
            "pendentes_avaliacao": result.get("pendentes_avaliacao", 0),
            "erradas": result.get("erradas", [])[:10]}


@router.post("/api/learn/avulso")
async def learn_avulso(request: Request, body: LearnAvulsoIn):
    """Registra resultado de quiz inline (JDUI quiz). Origem marcada como quiz-inline."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_avulso", "owner": dono,
                                   "titulo": body.titulo, "assunto": body.assunto,
                                   "certas": body.certas, "total": body.total},
                                  timeout=20.0)
    if result.get("type") != "learn_avulso_ok":
        raise _learn_erro(result)
    return {"ok": True, "assessment_id": result.get("assessment_id", ""),
            "attempt_id": result.get("attempt_id", "")}


@router.get("/api/learn/stats")
async def learn_stats(request: Request):
    """Resumo + desempenho por assunto (só dados reais; vazio útil sem dados)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_stats", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_stats":
        raise _learn_erro(result)
    return {"resumo": result.get("resumo", {}), "por_assunto": result.get("por_assunto", [])}


class LearnPlanIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=160)
    objetivo: str = Field(default="", max_length=500)
    assunto: str = Field(default="", max_length=120)
    prazo_iso: str = Field(default="", max_length=32)
    min_dia: int = Field(default=30, ge=5, le=480)
    itens: list = Field(default=[], min_length=1, max_length=50)
    id: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_-]*$")


class LearnPlanItemIn(BaseModel):
    plan_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    item_id: int = Field(ge=1)
    feito: bool = True


class LearnPlanUpdateIn(BaseModel):
    plan_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    mudancas: dict = Field(default={})


class LearnCardsIn(BaseModel):
    cards: list = Field(min_length=1, max_length=100)


class LearnReviewIn(BaseModel):
    flashcard_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    acertou: bool = True


class LearnFlagIn(BaseModel):
    question_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    motivo: str = Field(min_length=5, max_length=500)


@router.post("/api/learn/plans")
async def learn_plan_create(request: Request, body: LearnPlanIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plan_create", "owner": dono,
                                   "titulo": body.titulo, "objetivo": body.objetivo,
                                   "assunto": body.assunto, "prazo_iso": body.prazo_iso,
                                   "min_dia": body.min_dia, "itens": body.itens,
                                   "id": body.id}, timeout=20.0)
    if result.get("type") != "learn_plan":
        raise _learn_erro(result)
    return {"id": result["id"], "itens": result.get("itens", 0)}


@router.get("/api/learn/plans")
async def learn_plans(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plans", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_plans":
        raise _learn_erro(result)
    return {"planos": result.get("planos", [])}


@router.get("/api/learn/plans/{pid}")
async def learn_plan_get(request: Request, pid: str):
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(pid) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "learn_plan_get", "owner": dono, "id": pid},
                                  timeout=20.0)
    if result.get("type") != "learn_plan_full":
        raise _learn_erro(result)
    result.pop("request_id", None)
    result.pop("type", None)
    return result


@router.post("/api/learn/plans/item")
async def learn_plan_item(request: Request, body: LearnPlanItemIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plan_item", "owner": dono,
                                   "plan_id": body.plan_id, "item_id": body.item_id,
                                   "feito": "1" if body.feito else "0"}, timeout=20.0)
    if result.get("type") != "learn_plan_progress":
        raise _learn_erro(result)
    return {"progresso": result.get("progresso", {})}


@router.post("/api/learn/plans/update")
async def learn_plan_update(request: Request, body: LearnPlanUpdateIn):
    """Atualização compatível: concluídos preservados (match por título)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_plan_update", "owner": dono,
                                   "plan_id": body.plan_id, "mudancas": body.mudancas},
                                  timeout=20.0)
    if result.get("type") != "learn_plan_full":
        raise _learn_erro(result)
    result.pop("request_id", None)
    result.pop("type", None)
    return result


@router.post("/api/learn/cards")
async def learn_cards_create(request: Request, body: LearnCardsIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_cards_create", "owner": dono,
                                   "cards": body.cards}, timeout=20.0)
    if result.get("type") != "learn_cards":
        raise _learn_erro(result)
    return {"ids": result.get("ids", []), "total": result.get("total", 0)}


@router.get("/api/learn/cards/due")
async def learn_cards_due(request: Request, limite: int = 50):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_cards_due", "owner": dono,
                                   "limite": max(1, min(limite, 200))}, timeout=20.0)
    if result.get("type") != "learn_cards_due":
        raise _learn_erro(result)
    return {"cards": result.get("cards", [])}


@router.post("/api/learn/cards/review")
async def learn_cards_review(request: Request, body: LearnReviewIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_cards_review", "owner": dono,
                                   "flashcard_id": body.flashcard_id,
                                   "acertou": "1" if body.acertou else "0"}, timeout=20.0)
    if result.get("type") != "learn_cards_review":
        raise _learn_erro(result)
    return {"id": result.get("id", ""), "acertou": result.get("acertou", True),
            "intervalo_d": result.get("intervalo_d", 1),
            "proxima_iso": result.get("proxima_iso", "")}


@router.get("/api/learn/recommend")
async def learn_recommend(request: Request):
    """Recomendações determinísticas; sem dados → lista vazia com motivo."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_recommend", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_recommend":
        raise _learn_erro(result)
    return {"recomendacoes": result.get("recomendacoes", []),
            "motivo": result.get("motivo", "sem_dados"),
            "aviso": result.get("aviso", "")}


@router.post("/api/learn/flag")
async def learn_flag(request: Request, body: LearnFlagIn):
    """Sinaliza gabarito duvidoso (registra; não reescreve o histórico)."""
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_flag", "owner": dono,
                                   "question_id": body.question_id,
                                   "motivo": body.motivo}, timeout=20.0)
    if result.get("type") != "learn_flag_ok":
        raise _learn_erro(result)
    return {"ok": True, "question_id": result.get("question_id", "")}


@router.get("/api/learn/mistakes")
async def learn_mistakes(request: Request, limite: int = 20):
    """Erros recentes do dono (base p/ refazer e simulados de reforço)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_mistakes", "owner": dono,
                                   "limite": max(1, min(limite, 100))}, timeout=20.0)
    if result.get("type") != "learn_mistakes":
        raise _learn_erro(result)
    return {"erradas": result.get("erradas", [])}


class LearnLessonIn(BaseModel):
    aula: dict
    origem: str = Field(default="ia", max_length=20)
    id: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_-]*$")


class LearnLessonSectionIn(BaseModel):
    lesson_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    ordem: int = Field(ge=0, le=50)


@router.post("/api/learn/lessons")
async def learn_lesson_create(request: Request, body: LearnLessonIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_lesson_create", "owner": dono,
                                   "aula": body.aula, "origem": body.origem,
                                   "id": body.id}, timeout=20.0)
    if result.get("type") != "learn_lesson":
        raise _learn_erro(result)
    return {"id": result["id"], "secoes": result.get("secoes", 0)}


@router.get("/api/learn/lessons")
async def learn_lessons(request: Request):
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_lessons", "owner": dono}, timeout=20.0)
    if result.get("type") != "learn_lessons":
        raise _learn_erro(result)
    return {"aulas": result.get("aulas", [])}


@router.get("/api/learn/lessons/{lid}")
async def learn_lesson_get(request: Request, lid: str):
    verify_session(request)
    dono = await revogacao_ok(request)
    if not (2 <= len(lid) <= 64):
        raise HTTPException(422, "Identificador inválido")
    result = await relay.exchange({"type": "learn_lesson_get", "owner": dono, "id": lid},
                                  timeout=20.0)
    if result.get("type") != "learn_lesson_full":
        raise _learn_erro(result)
    result.pop("request_id", None)
    result.pop("type", None)
    return result


@router.post("/api/learn/lessons/section")
async def learn_lesson_section(request: Request, body: LearnLessonSectionIn):
    require_csrf(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_lesson_section", "owner": dono,
                                   "lesson_id": body.lesson_id, "ordem": body.ordem},
                                  timeout=20.0)
    if result.get("type") != "learn_lesson_progress":
        raise _learn_erro(result)
    return {"estado": result.get("estado", ""), "progresso": result.get("progresso", {})}


@router.get("/api/learn/history")
async def learn_history(request: Request, limite: int = 50):
    """Tentativas finalizadas do dono (séries factuais p/ gráficos de evolução)."""
    verify_session(request)
    dono = await revogacao_ok(request)
    result = await relay.exchange({"type": "learn_history", "owner": dono,
                                   "limite": max(1, min(limite, 200))}, timeout=20.0)
    if result.get("type") != "learn_history":
        raise _learn_erro(result)
    return {"tentativas": result.get("tentativas", [])}
