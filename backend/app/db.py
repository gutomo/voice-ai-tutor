"""データベース接続まわり (Phase 4)。

SQLAlchemy 2.0 の同期エンジン。本番は Postgres (`DATABASE_URL`)、テストは SQLite。
重いマイグレーションは入れず、`init_db()` の `create_all` でテーブルを用意する
(デモ用。本番運用に移すなら Alembic へ差し替える前提)。

DB アクセスはブロッキングなので、ルート側からは `run_in_threadpool` で呼ぶ。
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    """全 ORM モデルの基底。"""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def configure_engine(url: str | None = None) -> None:
    """エンジンとセッションファクトリを (再)構築する。

    テストは SQLite を渡してここを差し替える。in-memory SQLite はスレッドごとに
    別 DB になってしまうので、共有用に StaticPool を使う。
    """
    global _engine, _SessionLocal
    url = url or settings.database_url

    if url.startswith("sqlite"):
        # ファイル SQLite でもスレッド跨ぎを許可。:memory: は単一接続を共有する。
        connect_args = {"check_same_thread": False}
        if ":memory:" in url or url == "sqlite://":
            _engine = create_engine(
                url, connect_args=connect_args, poolclass=StaticPool, future=True
            )
        else:
            _engine = create_engine(url, connect_args=connect_args, future=True)
    else:
        # Postgres: アイドル接続が切れていても拾えるよう pre_ping。
        _engine = create_engine(url, pool_pre_ping=True, future=True)

    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def get_engine() -> Engine:
    if _engine is None:
        configure_engine()
    assert _engine is not None
    return _engine


def dispose_engine() -> None:
    """エンジンを破棄して未設定状態に戻す (主にテストの後始末)。"""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db() -> None:
    """テーブルを作成する (存在すれば何もしない)。"""
    # モデルを import して Base.metadata に登録させる (副作用 import)。
    from app import models  # noqa: F401

    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    """トランザクション境界。正常終了で commit、例外で rollback、最後に close。"""
    if _SessionLocal is None:
        configure_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
