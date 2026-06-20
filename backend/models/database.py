"""Database models for Tradi."""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TradeStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    strategy: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(20))
    token_from: Mapped[str] = mapped_column(String(20))
    token_to: Mapped[str] = mapped_column(String(20))
    amount_usd: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TradeStatus.PENDING.value)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    strategy: Mapped[str] = mapped_column(String(50))
    token: Mapped[str] = mapped_column(String(20))
    entry_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    size_usd: Mapped[float] = mapped_column(Float)
    size_pct: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    eligible: Mapped[bool] = mapped_column(Boolean, default=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_value_usd: Mapped[float] = mapped_column(Float)
    peak_value_usd: Mapped[float] = mapped_column(Float)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    daily_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    regime: Mapped[str] = mapped_column(String(20), default="ACCUMULATION")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    strategy: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(20))
    token: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    eligible: Mapped[bool] = mapped_column(Boolean, default=True)


class CircuitBreakerState(Base):
    __tablename__ = "circuit_breaker_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    breaker_type: Mapped[str] = mapped_column(String(50), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
