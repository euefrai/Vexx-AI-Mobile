"""Isola o estado volátil dos limitadores entre testes."""
import pytest

import server


@pytest.fixture(autouse=True)
def _limpar_limitadores():
    server.rate_limiter.clear()
    server.login_failures.clear()
    yield
    server.rate_limiter.clear()
    server.login_failures.clear()
