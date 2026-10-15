import sys

from e2e_processes import LoggedProcess


def test_logged_process_closes_log_and_terminates_child(tmp_path):
    log_path = tmp_path / "worker.log"
    child = LoggedProcess(
        [
            sys.executable,
            "-u",
            "-c",
            "import time; print('ready', flush=True); time.sleep(60)",
        ],
        log_path,
    )
    child.wait_for_output(timeout=5)
    child.stop(timeout=5)

    assert child.process.poll() is not None
    assert "ready" in log_path.read_text(encoding="utf-8")
    log_path.unlink()
    assert not log_path.exists()
