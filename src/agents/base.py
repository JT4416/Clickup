"""Base trading agent with ReAct (Reason-Act-Observe) loop and knowledge persistence."""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from src.broker.models import OptionOrder, Position
from src.broker.schwab_client import SchwabClient
from src.data.market_data import MarketDataEngine, MarketSnapshot
from src.options.analyzer import OptionsAnalyzer, SpreadCandidate
from src.risk.manager import RiskManager
from src.utils.logging import get_agent_logger


class AgentState(str, Enum):
    INITIALIZING = "INITIALIZING"
    REASONING = "REASONING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    IDLE = "IDLE"
    TERMINATED = "TERMINATED"


class TradeRecord(BaseModel):
    """Record of a completed trade for learning."""
    order: OptionOrder
    entry_time: datetime
    exit_time: datetime | None = None
    pnl: float = 0.0
    reasoning: str = ""
    market_conditions: dict[str, Any] = Field(default_factory=dict)
    outcome_analysis: str = ""
    lessons_learned: list[str] = Field(default_factory=list)


class Knowledge(BaseModel):
    """Transferable knowledge bank for an agent."""
    agent_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Trading patterns learned
    successful_patterns: list[dict[str, Any]] = Field(default_factory=list)
    failed_patterns: list[dict[str, Any]] = Field(default_factory=list)

    # Market regime understanding
    regime_models: dict[str, Any] = Field(default_factory=dict)

    # Strategy preferences (evolved through experience)
    strategy_weights: dict[str, float] = Field(default_factory=lambda: {
        "credit_spreads": 0.25,
        "debit_spreads": 0.25,
        "iron_condors": 0.20,
        "straddles": 0.10,
        "single_options": 0.20,
    })

    # Risk parameters learned
    optimal_position_size: float = 0.03
    preferred_dte_range: tuple[int, int] = (14, 45)
    preferred_delta_range: tuple[float, float] = (0.15, 0.40)

    # Sector/symbol preferences
    preferred_symbols: list[str] = Field(default_factory=lambda: [
        "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META",
    ])
    avoided_symbols: list[str] = Field(default_factory=list)

    # Accumulated wisdom (natural language insights)
    insights: list[str] = Field(default_factory=list)

    # Trade history digest
    total_trades: int = 0
    win_rate: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    best_trade: dict[str, Any] = Field(default_factory=dict)
    worst_trade: dict[str, Any] = Field(default_factory=dict)

    def merge_from(self, other: Knowledge) -> None:
        """Absorb knowledge from a defeated agent."""
        self.successful_patterns.extend(other.successful_patterns)
        self.failed_patterns.extend(other.failed_patterns)

        # Blend strategy weights (70% winner, 30% loser)
        for key in self.strategy_weights:
            if key in other.strategy_weights:
                self.strategy_weights[key] = (
                    0.7 * self.strategy_weights[key] + 0.3 * other.strategy_weights[key]
                )

        # Take union of preferred symbols, intersection of avoided
        self.preferred_symbols = list(
            set(self.preferred_symbols) | set(other.preferred_symbols)
        )
        self.avoided_symbols = list(
            set(self.avoided_symbols) & set(other.avoided_symbols)
        )

        self.insights.extend(other.insights)

        # Keep top insights by deduplication
        seen = set()
        unique = []
        for insight in self.insights:
            normalized = insight.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(insight)
        self.insights = unique[-50:]  # Keep most recent 50

        # Merge regime models
        self.regime_models.update(other.regime_models)


class TradingAgent(ABC):
    """Base autonomous trading agent using ReAct framework.

    Lifecycle: REASON -> ACT -> OBSERVE -> (repeat)
    Each cycle, the agent:
    1. REASON: Analyzes market data, positions, and knowledge to form a thesis
    2. ACT: Executes trades based on the thesis
    3. OBSERVE: Records outcomes and updates knowledge
    """

    def __init__(
        self,
        agent_id: str | None = None,
        name: str = "Agent",
        broker: SchwabClient | None = None,
        market_data: MarketDataEngine | None = None,
        risk_manager: RiskManager | None = None,
        knowledge: Knowledge | None = None,
    ):
        self.agent_id = agent_id or str(uuid.uuid4())[:8]
        self.name = name
        self.broker = broker
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.analyzer = OptionsAnalyzer()
        self.knowledge = knowledge or Knowledge(agent_id=self.agent_id)
        self.state = AgentState.INITIALIZING
        self.log = get_agent_logger(self.agent_id)

        # Performance tracking
        self.cycle_start_equity: float = 0.0
        self.current_equity: float = 0.0
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self.trade_history: list[TradeRecord] = []
        self.open_positions: list[Position] = []

        # ReAct loop state
        self._running = False
        self._reasoning_history: list[dict[str, Any]] = []

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def pnl_pct(self) -> float:
        if self.cycle_start_equity == 0:
            return 0.0
        return self.total_pnl / self.cycle_start_equity

    async def start(self) -> None:
        """Start the ReAct trading loop."""
        self._running = True
        self.state = AgentState.IDLE

        if self.broker:
            acct = await self.broker.get_account_info()
            self.cycle_start_equity = acct.total_equity
            self.current_equity = acct.total_equity

        self.log.info(f"Agent {self.name} ({self.agent_id}) started. Equity: ${self.cycle_start_equity:,.2f}")
        asyncio.create_task(self._react_loop())

    async def stop(self) -> None:
        """Stop the trading loop."""
        self._running = False
        self.state = AgentState.IDLE
        self.log.info(f"Agent {self.name} stopped. PnL: ${self.total_pnl:,.2f} ({self.pnl_pct:.2%})")

    async def terminate(self) -> Knowledge:
        """Terminate the agent and return its accumulated knowledge."""
        await self.stop()
        self.state = AgentState.TERMINATED

        # Close all open positions
        await self._close_all_positions()

        # Final knowledge update
        self._update_knowledge_stats()

        self.log.warning(
            f"Agent {self.name} TERMINATED. Final PnL: ${self.total_pnl:,.2f}. "
            f"Knowledge contains {len(self.knowledge.insights)} insights."
        )
        return self.knowledge

    async def _react_loop(self) -> None:
        """Main ReAct loop - runs every 60 seconds during market hours."""
        while self._running:
            try:
                # REASON
                self.state = AgentState.REASONING
                snapshot = await self.market_data.get_snapshot()
                thesis = await self.reason(snapshot)

                if thesis:
                    # ACT
                    self.state = AgentState.ACTING
                    actions = await self.act(thesis, snapshot)

                    # OBSERVE
                    self.state = AgentState.OBSERVING
                    await self.observe(actions, snapshot)

                self.state = AgentState.IDLE

            except Exception as e:
                self.log.error(f"ReAct loop error: {e}")
                self.state = AgentState.IDLE

            await asyncio.sleep(60)

    @abstractmethod
    async def reason(self, snapshot: MarketSnapshot) -> dict[str, Any] | None:
        """Analyze market conditions and form a trading thesis.

        Returns a thesis dict with:
        - direction: "bullish", "bearish", "neutral"
        - conviction: 0.0-1.0
        - target_symbols: list of symbols to trade
        - strategy: preferred strategy type
        - reasoning: natural language explanation
        """
        ...

    @abstractmethod
    async def act(self, thesis: dict[str, Any], snapshot: MarketSnapshot) -> list[OptionOrder]:
        """Execute trades based on the thesis. Returns list of orders placed."""
        ...

    async def observe(self, orders: list[OptionOrder], snapshot: MarketSnapshot) -> None:
        """Observe outcomes and update knowledge."""
        # Update position tracking
        if self.broker:
            acct = await self.broker.get_account_info()
            self.current_equity = acct.total_equity
            self.unrealized_pnl = self.current_equity - self.cycle_start_equity - self.realized_pnl
            self.open_positions = [p for p in acct.positions if p.agent_id == self.agent_id]

        # Record trades
        for order in orders:
            record = TradeRecord(
                order=order,
                entry_time=datetime.utcnow(),
                reasoning=self._reasoning_history[-1].get("reasoning", "") if self._reasoning_history else "",
                market_conditions={
                    "spy_price": snapshot.spy_price,
                    "vix": snapshot.vix,
                    "fear_greed": snapshot.fear_greed_index,
                },
            )
            self.trade_history.append(record)

        # Learn from recent outcomes
        await self._learn_from_outcomes()

    async def _learn_from_outcomes(self) -> None:
        """Analyze recent trades and update knowledge."""
        recent_closed = [t for t in self.trade_history if t.exit_time and not t.lessons_learned]

        for trade in recent_closed:
            if trade.pnl > 0:
                self.knowledge.successful_patterns.append({
                    "strategy": trade.order.spread_type.value,
                    "conditions": trade.market_conditions,
                    "pnl": trade.pnl,
                    "reasoning": trade.reasoning,
                })
                lesson = f"Profitable {trade.order.spread_type.value}: {trade.reasoning[:100]}"
            else:
                self.knowledge.failed_patterns.append({
                    "strategy": trade.order.spread_type.value,
                    "conditions": trade.market_conditions,
                    "pnl": trade.pnl,
                    "reasoning": trade.reasoning,
                })
                lesson = f"Loss on {trade.order.spread_type.value}: {trade.reasoning[:100]}"

            trade.lessons_learned.append(lesson)
            self.knowledge.insights.append(lesson)

        self._update_knowledge_stats()

    def _update_knowledge_stats(self) -> None:
        """Update aggregate stats in knowledge bank."""
        if not self.trade_history:
            return

        closed = [t for t in self.trade_history if t.exit_time]
        if not closed:
            return

        self.knowledge.total_trades = len(closed)
        winners = [t for t in closed if t.pnl > 0]
        losers = [t for t in closed if t.pnl <= 0]

        self.knowledge.win_rate = len(winners) / len(closed) if closed else 0
        self.knowledge.avg_winner = sum(t.pnl for t in winners) / len(winners) if winners else 0
        self.knowledge.avg_loser = sum(t.pnl for t in losers) / len(losers) if losers else 0

        if closed:
            best = max(closed, key=lambda t: t.pnl)
            worst = min(closed, key=lambda t: t.pnl)
            self.knowledge.best_trade = {"pnl": best.pnl, "strategy": best.order.spread_type.value}
            self.knowledge.worst_trade = {"pnl": worst.pnl, "strategy": worst.order.spread_type.value}

    async def _close_all_positions(self) -> None:
        """Close all open positions (used during termination)."""
        if not self.broker:
            return

        self.log.info(f"Closing {len(self.open_positions)} open positions...")
        for pos in self.open_positions:
            try:
                from src.broker.models import OrderAction, SpreadType

                action = (
                    OrderAction.SELL_TO_CLOSE if pos.quantity > 0
                    else OrderAction.BUY_TO_CLOSE
                )
                order = OptionOrder(
                    agent_id=self.agent_id,
                    contracts=[
                        OptionContract(
                            symbol=pos.symbol,
                            underlying=pos.underlying,
                            option_type=pos.option_type,
                            strike=pos.strike,
                            expiration=pos.expiration,
                            bid=pos.current_price * 0.95,
                            ask=pos.current_price * 1.05,
                        )
                    ],
                    actions=[action],
                    quantities=[abs(pos.quantity)],
                    spread_type=SpreadType.SINGLE,
                )
                await self.broker.place_option_order(order)
                self.log.info(f"Closed position: {pos.symbol}")
            except Exception as e:
                self.log.error(f"Failed to close {pos.symbol}: {e}")

    def get_performance_summary(self) -> dict[str, Any]:
        """Get a summary of agent performance for the arena."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self.state.value,
            "cycle_start_equity": self.cycle_start_equity,
            "current_equity": self.current_equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_pnl": self.total_pnl,
            "pnl_pct": self.pnl_pct,
            "total_trades": len(self.trade_history),
            "open_positions": len(self.open_positions),
            "win_rate": self.knowledge.win_rate,
        }
