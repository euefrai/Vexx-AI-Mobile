"""Isola o estado volátil dos limitadores entre testes."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


@pytest.fixture(autouse=True)
def _limpar_limitadores():
    server.rate_limiter.clear()
    server.login_failures.clear()
    yield
    server.rate_limiter.clear()
    server.login_failures.clear()
