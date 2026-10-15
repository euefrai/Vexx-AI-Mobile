"""Lifecycle helpers for subprocesses used by real-process E2E tests."""

import socket
import subprocess
import threading
from pathlib import Path


class LoggedProcess:
    """Capture child output in the test process so children never hold log files."""

    def __init__(self, command, log_path, *, cwd=None, env=None):
        self.log_path = Path(log_path)
        self._log = self.log_path.open("wb")
        self._reader_error = None
        self._output_received = threading.Event()
        try:
            self.process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
        except BaseException:
            self._log.close()
            raise

        self._reader = threading.Thread(
            target=self._copy_output,
            name=f"e2e-output-{self.process.pid}",
            daemon=True,
        )
        self._reader.start()

    def _copy_output(self):
        stream = self.process.stdout
        if stream is None:
            self._reader_error = RuntimeError("subprocess output pipe was not created")
            return
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                self._log.write(chunk)
                self._log.flush()
                self._output_received.set()
        except OSError as exc:
            self._reader_error = exc
        finally:
            stream.close()

    def stop(self, timeout=15):
        try:
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                except OSError:
                    if self.process.poll() is None:
                        raise
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=timeout)
        finally:
            self._reader.join(timeout=timeout)
            if self._reader.is_alive():
                if self.process.stdout is not None:
                    self.process.stdout.close()
                self._reader.join(timeout=timeout)
            if self._reader.is_alive():
                raise RuntimeError(
                    f"output reader for child PID {self.process.pid} did not stop"
                )
            self._log.close()
        if self._reader_error is not None:
            raise RuntimeError(
                f"failed reading output for child PID {self.process.pid}"
            ) from self._reader_error

    def __enter__(self):
        return self

    def wait_for_output(self, timeout=5):
        if not self._output_received.wait(timeout=timeout):
            raise TimeoutError(
                f"child PID {self.process.pid} produced no output within {timeout}s"
            )

    def __exit__(self, *exc_info):
        self.stop()
        return False if exc_info else None


def available_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
