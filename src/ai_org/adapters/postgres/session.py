from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_org.adapters.postgres.models import AI_ORG_SCHEMA
from ai_org.ports.repositories import Repository


def build_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, future=True)


def configure_search_path(session: Session) -> None:
    session.execute(text(f"set search_path to {AI_ORG_SCHEMA}, public"))


class PostgresUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self._repo: Repository | None = None

    @property
    def repo(self) -> Repository:
        if self._repo is None:
            raise RuntimeError("PostgresUnitOfWork has not been entered")
        return self._repo

    def __enter__(self) -> PostgresUnitOfWork:
        from ai_org.adapters.postgres.repositories import SqlAlchemyRepository

        self.session = self._session_factory()
        configure_search_path(self.session)
        self._repo = SqlAlchemyRepository(self.session)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.session is None:
            return
        if exc_type:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()

    def commit(self) -> None:
        if self.session is not None:
            self.session.commit()

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()
