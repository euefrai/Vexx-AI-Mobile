"""Stream framing, backpressure, denial and mid-stream revocation."""
import asyncio
import json

import pytest
from fastapi import HTTPException

import server
from fastapi.testclient import TestClient


class Connection:
    disconnected = False

    async def is_disconnected(self):
        return self.disconnected


def test_stream_http_rejects_anonymous():
    with TestClient(server.app) as client:
        assert client.get('/api/screen/stream').status_code == 401


def test_stream_checks_access_before_headers(monkeypatch):
    async def denied(*args):
        raise HTTPException(403, 'Sem autorização')
    monkeypatch.setattr(server, 'screen', denied)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.screen_stream(Connection()))
    assert exc.value.status_code == 403


def test_stream_rechecks_each_frame_and_reports_revocation(monkeypatch):
    calls = []

    async def capture(*args):
        calls.append(args)
        if len(calls) == 3:
            raise HTTPException(403, 'Acesso revogado')
        return {'imagem': 'jpeg', 'largura': 640, 'altura': 360}
    monkeypatch.setattr(server, 'screen', capture)

    async def run():
        response = await server.screen_stream(Connection(), 640, 50)
        assert response.headers['cache-control'] == 'no-store, private'
        assert response.media_type == 'application/x-ndjson'
        assert len(calls) == 1  # no capture ahead of consumer
        first = await anext(response.body_iterator)
        assert json.loads(first)['largura'] == 640
        assert len(calls) == 1
        rest = [json.loads(line) async for line in response.body_iterator]
        assert rest[-1] == {'error': 'Acesso revogado', 'status': 403}
        assert len(calls) == 3
    asyncio.run(run())


def test_stream_disconnect_stops_capture(monkeypatch):
    calls = []

    async def capture(*args):
        calls.append(1)
        return {'imagem': 'jpeg', 'largura': 640, 'altura': 360}
    monkeypatch.setattr(server, 'screen', capture)

    async def run():
        request = Connection()
        response = await server.screen_stream(request)
        await anext(response.body_iterator)
        request.disconnected = True
        assert [part async for part in response.body_iterator] == []
        assert len(calls) == 1
    asyncio.run(run())
