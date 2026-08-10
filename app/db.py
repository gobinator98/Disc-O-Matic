import logging
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, ForeignKey, Float, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

logger = logging.getLogger("discomatic.db")

DB_USER = os.environ.get("POSTGRES_USER", "discomatic")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "discomatic")
DB_HOST = os.environ.get("POSTGRES_HOST", "disco-matic-postgres")
DB_NAME = os.environ.get("POSTGRES_DB", "discomatic")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class DiscEvent(Base):
    __tablename__ = "disc_events"

    id = Column(Integer, primary_key=True)
    device = Column(String, nullable=False)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    media_type = Column(String, nullable=False)
    disc_label = Column(String, nullable=True)
    raw_properties = Column(JSON, nullable=True)

    # "unmatched" (no lookup attempted - e.g. no_media), "pending" (lookup
    # queued/running), "matched" (candidates found), "no_candidates",
    # "error" (lookup itself failed, e.g. API unreachable)
    match_status = Column(String, nullable=False, default="unmatched")

    matches = relationship("DiscMatch", back_populates="disc_event", order_by="DiscMatch.score.desc()")


class DiscMatch(Base):
    __tablename__ = "disc_matches"

    id = Column(Integer, primary_key=True)
    disc_event_id = Column(Integer, ForeignKey("disc_events.id"), nullable=False)
    source = Column(String, nullable=False)  # "tmdb_movie", "tmdb_tv", "musicbrainz"
    external_id = Column(String, nullable=True)
    title = Column(String, nullable=True)
    year = Column(String, nullable=True)
    score = Column(Float, nullable=True)  # source-native relevance score, not cross-comparable between sources
    extra = Column(JSON, nullable=True)  # overview/artist/track-list/etc., whatever the source gives us
    matched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    disc_event = relationship("DiscEvent", back_populates="matches")


def _sync_missing_columns():
    """Lightweight additive-only auto-migration: create_all() never alters
    tables that already exist, so as the schema grows during development
    we'd otherwise crash on the first insert against a stale table. This
    adds any columns the models declare that the live table is missing.
    Does not handle column removal/type changes/renames - fine for now,
    worth replacing with real migrations (Alembic) once the schema
    stabilizes.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                ddl_type = column.type.compile(dialect=engine.dialect)
                logger.warning("Adding missing column %s.%s (%s)", table.name, column.name, ddl_type)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'))


def init_db():
    Base.metadata.create_all(bind=engine)
    _sync_missing_columns()

