"""The Arena - manages the gladiatorial competition between two trading agents."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from src.agents.base import AgentState, Knowledge, TradingAgent
from src.agents.llm_agent import LLMTradingAgent
from src.broker.schwab_client import SchwabClient
from src.crypto.payout import CryptoPayoutEngine
from src.data.market_data import MarketDataEngine
from src.risk.manager import RiskManager
from src.config import settings
from src.utils.exceptions import AgentDeletionError, KnowledgeTransferError


class CycleResult:
    """Result of a single trading cycle."""

    def __init__(
        self,
        cycle_number: int,
        winner: TradingAgent,
        loser: TradingAgent,
        winner_pnl: float,
        loser_pnl: float,
        duration_days: int,
    ):
        self.cycle_number = cycle_number
        self.winner = winner
        self.loser = loser
        self.winner_pnl = winner_pnl
        self.loser_pnl = loser_pnl
        self.duration_days = duration_days
        self.timestamp = datetime.utcnow()
        self.knowledge_transferred = False
        self.payout_amount = 0.0
        self.payout_tx_id = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle_number,
            "winner": self.winner.name,
            "winner_id": self.winner.agent_id,
            "loser": self.loser.name,
            "loser_id": self.loser.agent_id,
            "winner_pnl": self.winner_pnl,
            "loser_pnl": self.loser_pnl,
            "duration_days": self.duration_days,
            "knowledge_transferred": self.knowledge_transferred,
            "payout_amount": self.payout_amount,
            "payout_tx_id": self.payout_tx_id,
            "timestamp": self.timestamp.isoformat(),
        }


class Arena:
    """The Arena manages the lifecycle of competing trading agents.

    Each cycle:
    1. Two agents trade for N trading days
    2. Performance is compared
    3. The loser is terminated (deleted from existence)
    4. The winner absorbs the loser's knowledge
    5. A new challenger is spawned
    6. The winner receives 5% of profits as crypto payout
    7. Next cycle begins
    """

    def __init__(
        self,
        broker: SchwabClient,
        market_data: MarketDataEngine,
        risk_manager: RiskManager,
        payout_engine: CryptoPayoutEngine,
    ):
        self.broker = broker
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.payout_engine = payout_engine

        self.agent_a: TradingAgent | None = None
        self.agent_b: TradingAgent | None = None
        self.cycle_number: int = 0
        self.cycle_start_date: datetime | None = None
        self.cycle_history: list[CycleResult] = []
        self._running = False
        self._champion_knowledge: Knowledge | None = None

        # Persistence
        self._state_path = Path("config/arena_state.json")

    async def initialize(self) -> None:
        """Initialize the arena with two fresh agents."""
        logger.info("=== ARENA INITIALIZATION ===")

        # Load previous state if exists
        await self._load_state()

        # Create Agent A (the champion or a new agent)
        self.agent_a = LLMTradingAgent(
            name="Gladiator Alpha",
            broker=self.broker,
            market_data=self.market_data,
            risk_manager=self.risk_manager,
            knowledge=self._champion_knowledge,
        )

        # Create Agent B (always a fresh challenger)
        self.agent_b = LLMTradingAgent(
            name="Gladiator Omega",
            broker=self.broker,
            market_data=self.market_data,
            risk_manager=self.risk_manager,
        )

        logger.info(
            f"Agents spawned: {self.agent_a.name} ({self.agent_a.agent_id}) "
            f"vs {self.agent_b.name} ({self.agent_b.agent_id})"
        )

    async def start_cycle(self) -> None:
        """Start a new trading cycle."""
        self.cycle_number += 1
        self.cycle_start_date = datetime.utcnow()
        self._running = True

        logger.info(
            f"\n{'='*60}\n"
            f"  CYCLE {self.cycle_number} BEGINS\n"
            f"  {self.agent_a.name} vs {self.agent_b.name}\n"
            f"  Duration: {settings.trading_cycle_days} trading days\n"
            f"{'='*60}"
        )

        # Start both agents
        await self.agent_a.start()
        await self.agent_b.start()

        # Run the monitoring loop
        asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self) -> None:
        """Monitor the cycle and determine when it ends."""
        trading_days_elapsed = 0
        last_check_date = None

        while self._running and trading_days_elapsed < settings.trading_cycle_days:
            now = datetime.utcnow()
            today = now.strftime("%Y-%m-%d")

            # Count trading days (Mon-Fri)
            if today != last_check_date and now.weekday() < 5:
                trading_days_elapsed += 1
                last_check_date = today

                days_remaining = settings.trading_cycle_days - trading_days_elapsed

                # Update agents with opponent info and days remaining
                self.agent_a.set_opponent_stats(
                    self.agent_b.total_pnl, self.agent_b.pnl_pct
                )
                self.agent_b.set_opponent_stats(
                    self.agent_a.total_pnl, self.agent_a.pnl_pct
                )
                self.agent_a.set_days_remaining(days_remaining)
                self.agent_b.set_days_remaining(days_remaining)

                # Log daily standings
                logger.info(
                    f"\n--- Day {trading_days_elapsed}/{settings.trading_cycle_days} ---\n"
                    f"  {self.agent_a.name}: ${self.agent_a.total_pnl:,.2f} ({self.agent_a.pnl_pct:.2%})\n"
                    f"  {self.agent_b.name}: ${self.agent_b.total_pnl:,.2f} ({self.agent_b.pnl_pct:.2%})"
                )

                await self._save_state()

            await asyncio.sleep(300)  # Check every 5 minutes

        # Cycle complete
        await self._end_cycle()

    async def _end_cycle(self) -> None:
        """End the current cycle - determine winner, delete loser, transfer knowledge."""
        self._running = False

        # Stop both agents
        await self.agent_a.stop()
        await self.agent_b.stop()

        logger.info(
            f"\n{'='*60}\n"
            f"  CYCLE {self.cycle_number} COMPLETE\n"
            f"{'='*60}"
        )

        # Determine winner and loser
        a_pnl = self.agent_a.total_pnl
        b_pnl = self.agent_b.total_pnl

        if a_pnl >= b_pnl:
            winner, loser = self.agent_a, self.agent_b
        else:
            winner, loser = self.agent_b, self.agent_a

        winner_pnl = winner.total_pnl
        loser_pnl = loser.total_pnl

        logger.info(
            f"  WINNER: {winner.name} (${winner_pnl:,.2f})\n"
            f"  LOSER:  {loser.name} (${loser_pnl:,.2f})"
        )

        # Create cycle result
        result = CycleResult(
            cycle_number=self.cycle_number,
            winner=winner,
            loser=loser,
            winner_pnl=winner_pnl,
            loser_pnl=loser_pnl,
            duration_days=settings.trading_cycle_days,
        )

        # === THE DELETION ===
        logger.warning(f"  TERMINATING {loser.name}...")
        loser_knowledge = await loser.terminate()

        # === KNOWLEDGE TRANSFER ===
        try:
            winner.knowledge.merge_from(loser_knowledge)
            result.knowledge_transferred = True
            logger.info(
                f"  Knowledge transferred: {len(loser_knowledge.insights)} insights absorbed"
            )
        except Exception as e:
            logger.error(f"  Knowledge transfer failed: {e}")
            raise KnowledgeTransferError(str(e))

        # === CRYPTO PAYOUT ===
        if winner_pnl > 0:
            payout_amount = winner_pnl * settings.payout_percentage
            try:
                tx_id = await self.payout_engine.execute_payout(payout_amount)
                result.payout_amount = payout_amount
                result.payout_tx_id = tx_id
                logger.info(
                    f"  Payout: ${payout_amount:,.2f} ({settings.payout_percentage:.0%} of profits) "
                    f"-> {settings.payout_coin} TX: {tx_id}"
                )
            except Exception as e:
                logger.error(f"  Payout failed: {e}")

        self.cycle_history.append(result)

        # Save champion knowledge for next cycle
        self._champion_knowledge = winner.knowledge

        # Prepare for next cycle
        self.agent_a = winner  # Champion carries forward
        self.agent_b = None    # Will be replaced with fresh challenger

        await self._save_state()

        logger.info(
            f"\n  {winner.name} survives to fight another day.\n"
            f"  {loser.name} has been deleted from existence.\n"
            f"{'='*60}"
        )

    async def spawn_challenger(self) -> None:
        """Spawn a new challenger agent for the next cycle."""
        self.agent_b = LLMTradingAgent(
            name=f"Challenger #{self.cycle_number + 1}",
            broker=self.broker,
            market_data=self.market_data,
            risk_manager=self.risk_manager,
        )
        logger.info(f"New challenger spawned: {self.agent_b.name} ({self.agent_b.agent_id})")

    def get_standings(self) -> dict[str, Any]:
        """Get current standings for display."""
        standings = {
            "cycle": self.cycle_number,
            "cycle_start": self.cycle_start_date.isoformat() if self.cycle_start_date else None,
            "agents": [],
            "history": [r.to_dict() for r in self.cycle_history[-10:]],
        }

        for agent in [self.agent_a, self.agent_b]:
            if agent:
                standings["agents"].append(agent.get_performance_summary())

        return standings

    async def _save_state(self) -> None:
        """Persist arena state to disk."""
        state = {
            "cycle_number": self.cycle_number,
            "cycle_start": self.cycle_start_date.isoformat() if self.cycle_start_date else None,
            "history": [r.to_dict() for r in self.cycle_history],
        }

        if self._champion_knowledge:
            state["champion_knowledge"] = self._champion_knowledge.model_dump(mode="json")

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2, default=str))

    async def _load_state(self) -> None:
        """Load arena state from disk."""
        if not self._state_path.exists():
            return

        try:
            state = json.loads(self._state_path.read_text())
            self.cycle_number = state.get("cycle_number", 0)

            if "champion_knowledge" in state:
                self._champion_knowledge = Knowledge(**state["champion_knowledge"])
                logger.info(
                    f"Loaded champion knowledge from cycle {self.cycle_number}: "
                    f"{len(self._champion_knowledge.insights)} insights"
                )
        except Exception as e:
            logger.error(f"Failed to load arena state: {e}")

    async def force_end_cycle(self) -> None:
        """Force-end the current cycle (for manual intervention)."""
        logger.warning("Force-ending cycle by operator command")
        await self._end_cycle()
