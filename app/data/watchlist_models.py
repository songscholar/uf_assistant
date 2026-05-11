"""
UF Stock Assistant — 自选股票模型
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings

Base = declarative_base()


class WatchlistItem(Base):
    """自选股票表"""

    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    name = Column(String(50), nullable=True)
    added_price = Column(Float, nullable=True)  # 添加时的价格快照
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_watchlist_user_symbol", "user_id", "symbol", unique=True),
    )


_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database.url
        _engine = create_engine(
            db_url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
        )
        Base.metadata.create_all(_engine)
        _migrate_add_price_column(_engine)
    return _engine


def _migrate_add_price_column(engine):
    """兼容迁移：为已有表添加 added_price 列（SQLite/PostgreSQL 通用）"""
    from sqlalchemy import inspect

    insp = inspect(engine)
    columns = [c["name"] for c in insp.get_columns("watchlist_items")]
    if "added_price" not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE watchlist_items ADD COLUMN added_price FLOAT"))
            conn.commit()


def _get_session():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    return _session_factory()


def get_watchlist(user_id: int) -> list[dict]:
    """获取用户自选列表"""
    with _get_session() as session:
        items = session.query(WatchlistItem).filter_by(user_id=user_id).order_by(WatchlistItem.created_at.desc()).all()
        return [
            {
                "id": item.id,
                "symbol": item.symbol,
                "name": item.name,
                "added_price": item.added_price,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ]


def add_watchlist_item(user_id: int, symbol: str, name: str | None = None, added_price: float | None = None) -> dict:
    """添加自选股票"""
    with _get_session() as session:
        existing = session.query(WatchlistItem).filter_by(user_id=user_id, symbol=symbol).first()
        if existing:
            return {"error": "该股票已在自选列表中"}
        item = WatchlistItem(user_id=user_id, symbol=symbol, name=name, added_price=added_price)
        session.add(item)
        session.commit()
        return {
            "id": item.id,
            "symbol": item.symbol,
            "name": item.name,
            "added_price": item.added_price,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }


def remove_watchlist_item(user_id: int, symbol: str) -> bool:
    """删除自选股票"""
    with _get_session() as session:
        item = session.query(WatchlistItem).filter_by(user_id=user_id, symbol=symbol).first()
        if item:
            session.delete(item)
            session.commit()
            return True
        return False
