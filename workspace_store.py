"""Project/chat organization, persisted only on the PC and isolated per account."""
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class WorkspaceRecord(BaseModel):
    id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    kind: Literal["project", "chat"]
    title: str = Field(min_length=1, max_length=80)
    project_id: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_-]*$")
    pinned: bool = False
    archived: bool = False
    deleted: bool = False
    updated_at: str = Field(max_length=48)
    change_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Informe um nome")
        return value

    @field_validator("updated_at")
    @classmethod
    def timestamp(cls, value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @model_validator(mode="after")
    def no_nested_projects(self):
        if self.kind == "project" and self.project_id:
            raise ValueError("Projetos não podem conter projetos")
        return self


class WorkspaceBatch(BaseModel):
    records: list[WorkspaceRecord] = Field(default_factory=list, max_length=300)


def create_tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS workspace_records (
        owner_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
        payload TEXT NOT NULL, updated_at TEXT NOT NULL, change_id TEXT NOT NULL,
        PRIMARY KEY (owner_id, kind, id)
    )""")


def merge_records(db, records, owner):
    # Validate the complete batch before starting a write. The relay is not trusted
    # to supply the owner: it is taken from the authenticated RPC envelope.
    batch = WorkspaceBatch.model_validate({"records": records})
    with db:
        for record in batch.records:
            data = record.model_dump()
            cursor = db.execute("""INSERT INTO workspace_records
                (owner_id, kind, id, payload, updated_at, change_id) VALUES (?,?,?,?,?,?)
                ON CONFLICT(owner_id,kind,id) DO UPDATE SET
                    payload=excluded.payload, updated_at=excluded.updated_at,
                    change_id=excluded.change_id
                WHERE (excluded.updated_at, excluded.change_id) >
                      (workspace_records.updated_at, workspace_records.change_id)""",
                (owner, record.kind, record.id, json.dumps(data, ensure_ascii=False),
                 record.updated_at, record.change_id))
            if cursor.rowcount and record.kind == "chat" and record.deleted:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "messages" in tables:
                    if "ui_state" in tables:
                        db.execute("""DELETE FROM ui_state WHERE owner_id=? AND message_id IN
                            (SELECT id FROM messages WHERE owner_id=? AND conversation_id=? AND origin='mobile')""",
                            (owner, owner, record.id))
                    db.execute("DELETE FROM messages WHERE owner_id=? AND conversation_id=? AND origin='mobile'",
                               (owner, record.id))
                if "ai_requests" in tables:
                    db.execute("DELETE FROM ai_requests WHERE owner_id=? AND conversation_id=?", (owner, record.id))


def list_records(db, owner):
    return [json.loads(row[0]) for row in db.execute(
        "SELECT payload FROM workspace_records WHERE owner_id=? ORDER BY kind,id", (owner,))]
