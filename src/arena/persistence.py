"""Database persistence for arena state, agent knowledge, and trade history."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


class AgentRecord(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    terminated_at = Column(DateTime, nullable=True)
    status = Column(String, default="active")  # active, terminated, champion
    total_pnl = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    knowledge_json = Column(Text, default="{}")
    cycles_survived = Column(Integer, default=0)


class TradeLog(Base):
    __tablename__ = "trade_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String, nullable=False)
    spread_type = Column(String, nullable=False)
    action = Column(String, nullable=False)  # open, close
    quantity = Column(Integer, default=1)
    price = Column(Float, default=0.0)
    pnl = Column(Float, nullable=True)
    reasoning = Column(Text, default="")
    market_conditions_json = Column(Text, default="{}")


class CycleRecord(Base):
    __tablename__ = "cycles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_number = Column(Integer, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    winner_id = Column(String, nullable=True)
    loser_id = Column(String, nullable=True)
    winner_pnl = Column(Float, default=0.0)
    loser_pnl = Column(Float, default=0.0)
    payout_amount = Column(Float, default=0.0)
    payout_tx_id = Column(String, default="")


class PayoutLog(Base):
    __tablename__ = "payouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_number = Column(Integer, nullable=False)
    amount_usd = Column(Float, nullable=False)
    amount_crypto = Column(Float, nullable=False)
    coin = Column(String, nullable=False)
    wallet_address = Column(String, nullable=False)
    tx_id = Column(String, default="")
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")


class Database:
    """Async database manager for arena persistence."""

    def __init__(self):
        self._engine = None
        self._session_factory = None

    async def initialize(self) -> None:
        self._engine = create_async_engine(settings.database_url, echo=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    def session(self) -> AsyncSession:
        return self._session_factory()

    async def save_agent(self, agent_id: str, name: str, knowledge_dict: dict) -> None:
        async with self.session() as session:
            record = AgentRecord(
                id=agent_id,
                name=name,
                knowledge_json=json.dumps(knowledge_dict, default=str),
            )
            session.add(record)
            await session.commit()

    async def update_agent(self, agent_id: str, **kwargs) -> None:
        async with self.session() as session:
            from sqlalchemy import update
            stmt = update(AgentRecord).where(AgentRecord.id == agent_id).values(**kwargs)
            await session.execute(stmt)
            await session.commit()

    async def log_trade(
        self,
        agent_id: str,
        symbol: str,
        spread_type: str,
        action: str,
        quantity: int,
        price: float,
        pnl: float | None = None,
        reasoning: str = "",
        market_conditions: dict | None = None,
    ) -> None:
        async with self.session() as session:
            record = TradeLog(
                agent_id=agent_id,
                symbol=symbol,
                spread_type=spread_type,
                action=action,
                quantity=quantity,
                price=price,
                pnl=pnl,
                reasoning=reasoning,
                market_conditions_json=json.dumps(market_conditions or {}, default=str),
            )
            session.add(record)
            await session.commit()

    async def log_cycle(
        self,
        cycle_number: int,
        start_date: datetime,
        end_date: datetime,
        winner_id: str,
        loser_id: str,
        winner_pnl: float,
        loser_pnl: float,
        payout_amount: float = 0.0,
        payout_tx_id: str = "",
    ) -> None:
        async with self.session() as session:
            record = CycleRecord(
                cycle_number=cycle_number,
                start_date=start_date,
                end_date=end_date,
                winner_id=winner_id,
                loser_id=loser_id,
                winner_pnl=winner_pnl,
                loser_pnl=loser_pnl,
                payout_amount=payout_amount,
                payout_tx_id=payout_tx_id,
            )
            session.add(record)
            await session.commit()

    async def shutdown(self) -> None:
        if self._engine:
            await self._engine.dispose()
