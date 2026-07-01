from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_org.adapters.postgres.repositories import SqlAlchemyRepository
from ai_org.domain.errors import ConflictError


class _FlushFailureSession:
    def flush(self) -> None:
        raise IntegrityError(
            "insert into private_table",
            {},
            Exception("duplicate key value violates unique constraint private_table_internal_key"),
        )


def test_postgres_integrity_errors_are_sanitized() -> None:
    repo = SqlAlchemyRepository(cast(Session, _FlushFailureSession()))

    with pytest.raises(ConflictError) as exc_info:
        repo._flush()

    assert str(exc_info.value) == "Database integrity conflict"
    assert "private_table" not in str(exc_info.value)
    assert "internal_key" not in str(exc_info.value)
