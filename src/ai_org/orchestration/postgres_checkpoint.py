from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ai_org.adapters.postgres.models import CHECKPOINT_SCHEMA
from ai_org.orchestration.checkpoint_security import build_serializer, configure_checkpoint_security

configure_checkpoint_security()

import psycopg  # noqa: E402
from langgraph.checkpoint.postgres import PostgresSaver  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402


@contextmanager
def postgres_checkpointer(database_url: str, *, setup: bool = False) -> Iterator[PostgresSaver]:
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        if setup:
            conn.execute(f"create schema if not exists {CHECKPOINT_SCHEMA}")
        conn.execute(f"set search_path to {CHECKPOINT_SCHEMA}, public")
        saver = PostgresSaver(conn, serde=build_serializer())
        if setup:
            saver.setup()
        yield saver
