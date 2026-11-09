"""Testes unitários e de integração para o motor local YOLOv8,

benchmark de latência, fallback e endpoints de visão do VEXX-AI.
"""
from __future__ import annotations

import base64
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pc_agent
import server
import vision_service

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _criar_imagem_teste() -> Image.Image:
  img = Image.new("RGB", (640, 480), (130, 160, 200))
  return img


def test_motores_visao_configuracao_e_listagem():
  """Verifica a alternância e a listagem dos motores de visão (local, huggingface, auto)."""
  original = vision_service.obter_motor_visao()
  try:
    assert vision_service.definir_motor_visao("local") == "local"
    assert vision_service.obter_motor_visao() == "local"

    assert vision_service.definir_motor_visao("huggingface") == "huggingface"
    assert vision_service.obter_motor_visao() == "huggingface"

    assert vision_service.definir_motor_visao("auto") == "auto"
    assert vision_service.obter_motor_visao() == "auto"

    motores = vision_service.listar_motores_visao()
    ids = [m["id"] for m in motores]
    assert "auto" in ids
    assert "local" in ids
    assert "huggingface" in ids

    motor_local = next(m for m in motores if m["id"] == "local")
    assert motor_local["disponivel"] is True
    assert "yolov8" in motor_local["modelo"].lower()
  finally:
    vision_service.definir_motor_visao(original)


def test_analisar_imagem_local_com_sucesso():
  """Valida a inferência do YOLOv8 rodando no computador local."""
  img = _criar_imagem_teste()
  res = vision_service.analisar_imagem(img, motor="local")

  assert res["status"] == "sucesso"
  assert res["motor"] == "local"
  assert "Local (PC)" in res["modelo"]
  assert res["dimensoes"] == {"largura": 640, "altura": 480}
  assert isinstance(res["deteccoes"], list)
  assert isinstance(res["alvos_clique"], list)
  assert "latencia_ms" in res
  assert res["latencia_ms"] > 0


def test_testar_latencia_yolo_local_benchmark():
  """Valida a medição de latência do YOLO no PC (warm-up + iterações)."""
  bench = vision_service.testar_latencia_yolo_local(iteracoes=3)

  assert bench["status"] == "sucesso"
  assert bench["motor"] == "local"
  assert bench["iteracoes"] == 3
  assert bench["latencia_media_ms"] > 0
  assert bench["latencia_min_ms"] > 0
  assert bench["latencia_max_ms"] >= bench["latencia_min_ms"]
  assert bench["fps_estimado"] > 0
  assert bench["dispositivo"] in ("CPU", "CUDA (GPU)")
  assert "YOLOv8 no PC" in bench["mensagem"]


def test_fallback_yolo_local_quando_huggingface_falha(monkeypatch):
  """Quando o motor é huggingface e o Space falha/está indisponível, deve acionar o YOLO local."""

  def _fake_hf_fail(*args, **kwargs):
    return {"status": "erro", "mensagem": "Space hibernando ou erro 503"}

  monkeypatch.setattr(vision_service, "analisar_imagem_huggingface", _fake_hf_fail)

  img = _criar_imagem_teste()
  res = vision_service.analisar_imagem(img, motor="huggingface")

  # Acionou o fallback para o YOLO local no PC
  assert res["status"] == "sucesso"
  assert res["motor"] == "local"
  assert res.get("fallback_de_huggingface") is True


def test_fallback_huggingface_quando_local_falha(monkeypatch):
  """Quando o motor é local e ocorre falha, deve acionar o fallback para o Hugging Face."""

  def _fake_local_fail(*args, **kwargs):
    raise RuntimeError("Falha simulada no carregamento do modelo local")

  payload_hf = {
      "status": "sucesso",
      "dimensoes": {"largura": 800, "altura": 600},
      "total_objetos": 1,
      "total_textos": 0,
      "tags_busca": "keyboard",
      "texto_extraido": "",
      "deteccoes": [{
          "tipo": "objeto",
          "objeto": "keyboard",
          "confianca": 0.85,
          "coordenadas": [10, 10, 200, 100],
          "ponto_clique": {"x": 105, "y": 55, "x_norm": 0.13, "y_norm": 0.09},
      }],
      "textos_lidos": [],
      "alvos_clique": [],
      "origem": "fake",
  }

  monkeypatch.setattr(vision_service, "analisar_imagem_local", _fake_local_fail)
  monkeypatch.setattr(
      vision_service, "analisar_imagem_huggingface", lambda *a, **k: payload_hf
  )

  img = _criar_imagem_teste()
  res = vision_service.analisar_imagem(img, motor="local")

  assert res["status"] == "sucesso"
  assert res["dimensoes"] == {"largura": 800, "altura": 600}
  assert res["total_objetos"] == 1


def test_ai_request_aceita_campo_vision_engine():
  """Valida que o schema AIRequest aceita e propaga o campo vision_engine."""
  req = server.AIRequest(
      message_id="msg-vision-0002",
      conversation_id="conv-002",
      text="Analise a tela",
      vision_engine="local",
  )
  assert req.vision_engine == "local"
  ctx = pc_agent._contexto_local_seguro(req.model_dump())
  assert ctx.get("vision_engine") == "local"


def test_api_vision_endpoints(monkeypatch):
  """Valida as rotas REST /api/vision/engine, /api/vision/latency-test e /api/vision/analyze."""
  client = TestClient(server.app)

  async def _mock_revogacao(req):
    return "usr-test"

  import routers.ai_routes as ai_routes
  monkeypatch.setattr(ai_routes, "revogacao_ok", _mock_revogacao)
  monkeypatch.setattr(ai_routes, "require_csrf", lambda req: None)

  # 1. GET /api/vision/engine
  resp_get = client.get("/api/vision/engine")
  assert resp_get.status_code == 200
  data_get = resp_get.json()
  assert "engine" in data_get
  assert "engines" in data_get
  assert len(data_get["engines"]) >= 3

  # 2. POST /api/vision/engine
  resp_post = client.post(
      "/api/vision/engine", json={"engine": "local"}
  )
  assert resp_post.status_code == 200
  assert resp_post.json()["engine"] == "local"

  # 3. POST /api/vision/latency-test
  resp_lat = client.post(
      "/api/vision/latency-test", json={"iterations": 2}
  )
  assert resp_lat.status_code == 200
  lat_data = resp_lat.json()
  assert lat_data["status"] == "sucesso"
  assert lat_data["latencia_media_ms"] > 0
  assert lat_data["iteracoes"] == 2
