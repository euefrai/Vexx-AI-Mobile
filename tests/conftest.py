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


@pytest.fixture(autouse=True)
def _isolated_weather_credentials_and_usage(monkeypatch,tmp_path):
    # Never consume the operator key or persist QA quota/cache in the real PC DB.
    monkeypatch.setenv('VISUAL_CROSSING_API_KEY','fixture-weather-key')
    monkeypatch.setenv('VISUAL_CROSSING_USAGE_PATH',str(tmp_path/'weather-usage.sqlite3'))
