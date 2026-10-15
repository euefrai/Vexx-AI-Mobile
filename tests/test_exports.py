import asyncio
from io import BytesIO

from openpyxl import load_workbook


def test_export_xlsx_authenticated_route_and_formula_text(monkeypatch):
    import server

    monkeypatch.setattr(server, "require_csrf", lambda request: None)

    async def owner(request):
        return "test-user"

    monkeypatch.setattr(server, "revogacao_ok", owner)
    body = server.XlsxExport(
        title="=HYPERLINK(\"https://example.invalid\")",
        messages=[
            server.ExportMessage(
                role="assistant",
                text="+1+1",
                created_at="2026-01-02T03:04:05-03:00",
            )
        ],
    )
    response = asyncio.run(server.export_xlsx(object(), body))

    assert response.status_code == 200
    assert response.media_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    workbook = load_workbook(BytesIO(response.body), data_only=False)
    sheet = workbook["Conversa"]
    assert sheet["B1"].value.startswith("'=")
    assert sheet["C3"].value == "'+1+1"
    assert sheet["C3"].data_type == "s"
    assert sheet.freeze_panes == "A3"


def test_export_schema_caps_messages():
    import pytest
    from pydantic import ValidationError

    import server

    with pytest.raises(ValidationError):
        server.XlsxExport(messages=[])
    with pytest.raises(ValidationError):
        server.ExportMessage(role="system", text="conteúdo interno")
