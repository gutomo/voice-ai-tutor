"""ORM モデル (Phase 4)。BUILD_PLAN.md のデータモデル (最小) に対応する。

- learners          学習者
- sessions          レッスン1回分 (LessonSession クラス。SQLAlchemy の Session と名前衝突を避ける)
- turns             ターンごとの採点結果 (audio turn_id を主キーに再利用 → 再評価は upsert)
- learner_profile   学習者の現在の推定レベル + 合格ライン到達度

jsonb は Postgres でのみ。SQLite (テスト) では汎用 JSON にフォールバックする。
ja-JP は音素を返さないので weak_phonemes には実際には「弱い単語」のリストが入る。
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Postgres では jsonb、それ以外 (SQLite) では JSON。
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    # まとめメールの宛先。未設定なら送信時に EMAIL_SENDER へフォールバックする (Phase 6)。
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    native_lang: Mapped[str] = mapped_column(String(16), default="id")  # 既定: Bahasa Indonesia
    target_sector: Mapped[str] = mapped_column(String(32), default="kaigo")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    sessions: Mapped[list["LessonSession"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    profile: Mapped["LearnerProfile | None"] = relationship(
        back_populates="learner", cascade="all, delete-orphan", uselist=False
    )


class LessonSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"))
    scenario: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    learner: Mapped["Learner"] = relationship(back_populates="sessions")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"

    # audio の turn_id (uuid hex) を主キーに再利用する → 同じターンの再評価は上書きになる。
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    turn_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)

    pron_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    pron_fluency: Mapped[float | None] = mapped_column(Float, nullable=True)
    pron_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ja-JP は音素名が無いため「弱い単語」のリストを入れる ([{word, accuracy, error_type}, ...])。
    weak_phonemes: Mapped[list | None] = mapped_column(JSONType, nullable=True)

    rubric: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    combined_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped["LessonSession"] = relationship(back_populates="turns")


class LearnerProfile(Base):
    __tablename__ = "learner_profile"

    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True
    )
    cefr_estimate: Mapped[str | None] = mapped_column(String(8), nullable=True)
    jlpt_estimate: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kaigo_passline_pct: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    learner: Mapped["Learner"] = relationship(back_populates="profile")
