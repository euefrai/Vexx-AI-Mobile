import json
import os
import sys
import tempfile
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_quality_lab as lab


def setup_module():
    from argon2 import PasswordHasher
    os.environ['JULIA_USERNAME'] = 'owneruser'
    os.environ['JULIA_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['JULIA_SESSION_SECRET'] = 'a' * 64
    os.environ['JULIA_AGENT_TOKEN'] = 'b' * 64
    import server
    server.login_failures.clear()


DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "research_quality_v1.json"


def test_frozen_dataset_is_versioned_and_fixture_scoped():
    dataset, digest = lab.load_dataset(DATASET)
    assert dataset["version"] == "1.0.0"
    assert dataset["truth_basis"] == "synthetic_local_fixture"
    assert digest == (
        # Digest canônico (LF): load_dataset normaliza CRLF→LF, então o
        # mesmo valor vale no Windows (autocrlf) e no Linux/CI.
        "9942a2587743a883debd407da68be0d884475561aab8d95959b3fe84a05ad314"
    )
    assert len(dataset["documents"]) >= 8
    assert {case["category"] for case in dataset["cases"]} >= {
        "factual_qa", "multi_hop_research", "contradiction_detection",
        "source_attribution", "document_research", "numerical_reasoning",
        "temporal_research", "adversarial_research",
    }
    assert {scenario["step_count"] for scenario in dataset["checkpoint_scenarios"]} == {
        10, 25, 50,
    }


def test_dataset_rejects_unknown_reference_and_non_fixture_truth(tmp_path):
    raw = json.loads(DATASET.read_text(encoding="utf-8"))
    raw["truth_basis"] = "model_answer"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(lab.QualityLabError, match="truth basis"):
        lab.load_dataset(bad)

    raw["truth_basis"] = "synthetic_local_fixture"
    raw["cases"][0]["queries"][0]["relevance"]["invented-doc"] = 3
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(lab.QualityLabError, match="unknown relevant document"):
        lab.load_dataset(bad)


def test_retrieval_metrics_are_exact_and_report_duplicates():
    result = lab.retrieval_metrics(
        ["doc-a", "doc-b", "doc-a", "irrelevant"],
        {"doc-a": 3, "doc-b": 1},
        k=4,
    )
    assert result["precision_at_k"] == 0.5
    assert result["recall_at_k"] == 1.0
    assert result["mrr_at_k"] == 1.0
    assert result["duplicate_rate_at_k"] == 0.25
    assert 0 < result["ndcg_at_k"] <= 1


def test_retrieval_metrics_reject_bad_k_and_empty_reference():
    with pytest.raises(lab.QualityLabError, match="positive integer"):
        lab.retrieval_metrics([], {"doc": 1}, k=0)
    with pytest.raises(lab.QualityLabError, match="positive integer grades"):
        lab.retrieval_metrics([], {}, k=5)


def test_claim_label_metrics_do_not_infer_semantics():
    result = lab.classification_metrics(
        ["SUPPORTED", "CONTRADICTED", "UNVERIFIED"],
        ["SUPPORTED", "UNVERIFIED", "UNVERIFIED"],
    )
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["confusion_matrix"]["CONTRADICTED"]["UNVERIFIED"] == 1
    assert result["per_label"]["CONTRADICTED"]["recall"] == 0.0


def test_citation_validation_stages_remain_separate():
    result = lab.citation_stage_metrics([
        {
            "citation_exists": True,
            "source_retrieved": True,
            "passage_found": False,
            "claim_supported": False,
        },
        {
            "citation_exists": True,
            "source_retrieved": False,
            "passage_found": False,
            "claim_supported": False,
        },
    ])
    stages = result["stages"]
    assert stages["citation_exists"]["rate"] == 1.0
    assert stages["source_retrieved"]["rate"] == 0.5
    assert stages["passage_found"]["rate"] == 0.0
    assert stages["claim_supported"]["rate"] == 0.0


def test_contradiction_metric_reports_false_positives_and_negatives():
    result = lab.contradiction_metrics(
        [True, True, False, False],
        [True, False, True, False],
    )
    assert result == {
        "count": 4,
        "true_positive": 1,
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 1,
        "precision": 0.5,
        "recall": 0.5,
    }


def test_checkpoint_metric_covers_state_and_duplicate_operations():
    result = lab.checkpoint_metrics(
        {
            "objectives": ["objective"],
            "constraints": ["owner-only", "no-llm"],
            "decisions": ["do-not-research-online"],
            "evidence_ids": ["e-1", "e-2"],
            "pending": ["verify-source"],
        },
        {
            "objectives": ["objective"],
            "constraints": ["owner-only"],
            "decisions": ["do-not-research-online"],
            "evidence_ids": ["e-1", "e-2"],
            "pending": ["verify-source"],
            "operation_ids": ["step-1", "step-2", "step-2"],
        },
    )
    assert result["state"]["constraints"]["recall"] == 0.5
    assert result["state"]["constraints"]["missing"] == ["no-llm"]
    assert result["duplicate_operation_ids"] == 1


def test_optimization_recommendations_are_tied_to_measured_signals():
    recommendations = lab.retrieval_recommendations({
        "precision_at_k": 0.2,
        "recall_at_k": 0.95,
        "ndcg_at_k": 0.99,
        "duplicate_rate_at_k": 0.0,
    })
    assert [item["signal"] for item in recommendations] == [
        "low_precision_with_recall",
    ]


def test_runner_measures_real_local_document_retriever_in_isolated_store(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JULIA_DOCS_PATH", str(tmp_path / "original-user-docs"))
    old_path = str(tmp_path / "original-user-docs")
    work_dir = tmp_path / "isolated-run"
    report = lab.run_document_retrieval_benchmark(DATASET, work_dir, k=5)

    assert report["dataset"]["truth_basis"] == "synthetic_local_fixture"
    assert report["dataset"]["sha256"]
    assert report["execution"]["retriever"] == "docs_agent.trechos_relevantes"
    assert report["counts"] == {"documents": 11, "cases": 8, "queries": 9}
    assert report["timing_ms"]["retrieval_mean"] >= 0
    assert report["retrieval_metrics"]["recall_at_k"] is not None
    assert report["source_quality_metrics"]["primary_source"]["recall"] == 1.0
    assert report["source_quality_metrics"]["contradiction_evidence_pair"]["recall"] == 1.0
    assert report["optimization_recommendations"][0]["signal"] == (
        "low_precision_with_recall"
    )
    assert (work_dir / "documents").is_dir()
    assert not (Path(old_path) / "protocol-gh-a.txt").exists()
    assert any(
        "semantic claim correctness" in item
        for item in report["not_measured"]
    )


def test_runner_measures_persisted_checkpoint_restore_after_reopen(tmp_path):
    report = lab.run_checkpoint_benchmark(
        DATASET, tmp_path / "checkpoints.sqlite3"
    )

    assert report["counts"] == {
        "scenarios": 3,
        "checkpoints_saved": 85,
        "steps_in_scenarios": 85,
    }
    for scenario in report["scenarios"]:
        assert scenario["checkpoint_sequence"] == scenario["step_count"]
        assert scenario["restored_sequence"] == scenario["step_count"]
        assert scenario["metrics"]["duplicate_operation_ids"] is None
        assert all(
            value["recall"] == 1.0
            for value in scenario["metrics"]["state"].values()
        )


def test_cli_store_db_persiste_relatorio(tmp_path):
    import sqlite3
    import subprocess
    import sys
    destino = tmp_path / "quality.sqlite3"
    saida = tmp_path / "relatorio.json"
    r = subprocess.run(
        [sys.executable, "run_research_quality_lab.py", "--store-db", str(destino),
         "--output", str(saida)],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True, timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    assert saida.exists() and json.loads(saida.read_text(encoding="utf-8"))["dataset"]
    con = sqlite3.connect(destino)
    try:
        rows = con.execute("SELECT id, owner_id, dataset_id FROM quality_runs").fetchall()
    finally:
        con.close()
    assert len(rows) == 1 and rows[0][1] == "quality-lab-cli" and rows[0][2]


DATASET_V2 = Path(__file__).resolve().parents[1] / "benchmarks" / "research_quality_v2.json"


def test_dataset_v2_versionado_e_valido():
    dataset, digest = lab.load_dataset(DATASET_V2)
    assert dataset["version"] == "2.0.0"
    assert len(digest) == 64
    assert len(dataset["documents"]) >= 10
    assert len(dataset.get("factual_pairs", [])) >= 5
    assert len(dataset.get("memory_cases", [])) >= 2
    assert dataset.get("graph_cases") and dataset.get("graph_evidence")


def test_memory_retrieval_benchmark(tmp_path):
    rep = lab.run_memory_retrieval_benchmark(DATASET_V2, tmp_path / "mem")
    assert rep["summary"]["query_count"] == 3
    assert rep["summary"]["recall_at_k"] == 1.0
    assert all(q["metrics"]["mrr_at_k"] == 1.0 for q in rep["queries"])
    assert rep["summary"]["total_ms"] >= 0


def test_graph_retrieval_benchmark(tmp_path):
    rep = lab.run_graph_retrieval_benchmark(DATASET_V2, tmp_path / "graph")
    assert rep["summary"]["query_count"] == 1
    assert rep["summary"]["recall_at_k"] == 1.0
    got = rep["queries"][0]["retrieved_evidence_ids"]
    assert set(got) >= {"ev-photon", "ev-reprint"}


def test_factual_verification_benchmark():
    rep = lab.run_factual_verification_benchmark(DATASET_V2)
    assert rep["classification"]["count"] == 6
    assert rep["classification"]["accuracy"] == 1.0
    assert all(r["match"] for r in rep["pairs"])


def test_format_benchmark_formatos_reais(tmp_path):
    rep = lab.run_format_benchmark(tmp_path / "fmt")
    assert rep["docx_gerado"] and rep["xlsx_gerado"]
    assert rep["todos_extraidos"], rep["resultados"]
    assert rep["todos_buscaveis"], rep["resultados"]
    nomes = {r["arquivo"] for r in rep["resultados"]}
    assert {"relatorio.pdf", "contrato.docx", "planilha.xlsx", "pagina.html",
            "contrato.json", "tabela.csv", "nota.md", "texto.txt"} <= nomes


def _mem_db(tmp_path, nome="quality.sqlite3"):
    import pc_agent
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def test_quality_runs_persistidos_por_dono(tmp_path):
    db = _mem_db(tmp_path)
    rep = {"dataset": {"dataset_id": "d", "version": "1", "sha256": "abc"},
           "summary": {"precision_at_k": 0.5, "query_count": 4}}
    rid = lab.store_report(db, "local", rep)
    assert rid.startswith("qr-")
    runs = lab.list_reports(db, "local")
    assert len(runs) == 1 and runs[0]["id"] == rid
    assert runs[0]["summary"]["precision_at_k"] == 0.5
    assert runs[0]["dataset_sha256"] == "abc"
    assert lab.list_reports(db, "u-outro") == []  # isolamento
    try:
        lab.store_report(db, "local", {})
        raise AssertionError("relatório vazio deveria falhar")
    except lab.QualityLabError:
        pass


def test_admin_quality_endpoints_exigem_papel():
    import server
    from fastapi.testclient import TestClient
    from test_auth import _agente_generico
    with TestClient(server.app) as client:
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            respostas = {
                'auth_login': lambda r: {'type': 'auth_ok', 'uid': 'u-aaa', 'username': 'ana',
                                         'display': 'Ana', 'role': 'user', 'sid': 'sid-ana'},
                'auth_whoami': lambda r: {'type': 'auth_user',
                                          'user': {'uid': 'u-aaa', 'username': 'ana',
                                                   'display': 'Ana', 'role': 'user', 'status': 'ativo'}},
            }
            t = threading.Thread(target=_agente_generico, args=(ws, respostas, {}), daemon=True)
            t.start()
            lg = client.post('/api/login', json={'username': 'ana', 'password': 'senha-forte-1'})
            csrf = lg.json()['csrf']
            r = client.get('/api/admin/quality/runs', headers={'X-CSRF-Token': csrf})
            assert r.status_code == 403  # comum barrado no relay
            r = client.post('/api/admin/quality/run', headers={'X-CSRF-Token': csrf})
            assert r.status_code == 403


def test_admin_quality_run_e_runs_pelo_agente_fake():
    import server
    from fastapi.testclient import TestClient
    from test_auth import _agente_generico, _login_legacy
    with TestClient(server.app) as client:
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            respostas = {
                'quality_run': lambda r: {'type': 'quality_run', 'run_id': 'qr-1',
                                          'summary': {'precision_at_k': 0.75, 'query_count': 8},
                                          'dataset': {'dataset_id': 'd', 'version': '1',
                                                      'sha256': 'abc'}},
                'quality_runs': lambda r: {'type': 'quality_runs',
                                           'runs': [{'id': 'qr-1', 'summary': {'precision_at_k': 0.75}}]},
            }
            t = threading.Thread(target=_agente_generico, args=(ws, respostas, {}), daemon=True)
            t.start()
            csrf = _login_legacy(client)  # dono local = admin
            r = client.post('/api/admin/quality/run', headers={'X-CSRF-Token': csrf})
            assert r.status_code == 200, r.text
            assert r.json()["run_id"] == "qr-1"
            assert r.json()["summary"]["precision_at_k"] == 0.75
            r = client.get('/api/admin/quality/runs', headers={'X-CSRF-Token': csrf})
            assert r.json()["runs"][0]["id"] == "qr-1"


def test_cmd_qualidade_admin_e_negacoes(tmp_path):
    import pc_agent
    db = _mem_db(tmp_path)
    assert pc_agent.cmd_qualidade(db, "qual o clima?", "local") == ""
    assert "avaliações armazenadas" in pc_agent.cmd_qualidade(db, "mostre a qualidade da pesquisa",
                                                              "local")
    import julia_auth as _ja
    _ja.config_set(db, 'modo_cadastro', 'aberto')
    assert "restrito ao administrador" in pc_agent.cmd_qualidade(
        db, "qualidade da pesquisa", "u-zzz")
    rid = lab.store_report(db, "local", {"dataset": {"dataset_id": "d", "version": "1",
                                                     "sha256": "abc"},
                                         "summary": {"precision_at_k": 1.0, "recall_at_k": 0.5,
                                                     "mrr_at_k": 1.0, "ndcg_at_k": 0.9,
                                                     "query_count": 8, "k": 5}})
    out = pc_agent.cmd_qualidade(db, "painel de qualidade", "local")
    assert "```jdui" in out and '"component": "dashboard"' in out
    assert "1.0" in out and "qr-" not in out  # números reais, sem IDs internos
    db.close()


def test_mode_comparison_ordena_orcamentos(tmp_path):
    rep = lab.run_mode_comparison_benchmark(tmp_path / "modes")
    assert set(rep["modos"]) == {"rapida", "pro", "profunda", "investigativa"}
    assert rep["provider"] == "frozen-synthetic"
    evs = [rep["modos"][m]["evidencias"] for m in ("rapida", "pro", "profunda", "investigativa")]
    assert evs == sorted(evs)
    assert all(rep["modos"][m]["status"] == "concluida" for m in rep["modos"])


def test_doc_benchmark_mede_pico_python(tmp_path):
    rep = lab.run_document_retrieval_benchmark(DATASET, tmp_path / "mem")
    assert rep["timing_ms"]["peak_python_kb"] > 0
