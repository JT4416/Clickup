"""Risk management engine - position sizing, exposure limits, circuit breakers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from src.broker.models import AccountInfo, OptionOrder, OrderStatus
from src.config import settings
from src.utils.exceptions import RiskLimitExceededError


class RiskManager:
    """Enforces risk limits and position sizing rules.

    This is the hard safety layer that CANNOT be overridden by agents.
    Both agents share the same account, so risk must be managed holistically.
    """

    def __init__(self):
        self.max_position_size_pct = settings.max_position_size_pct
        self.max_total_exposure_pct = settings.max_total_exposure_pct
        self.max_single_loss_pct = settings.max_single_loss_pct
        self.daily_loss_limit_pct = settings.daily_loss_limit_pct

        # Track daily losses per agent
        self._daily_losses: dict[str, float] = {}
        self._daily_reset_date: str = ""
        self._blocked_agents: set[str] = set()

        # Track total exposure per agent
        self._agent_exposure: dict[str, float] = {}

    def check_order(self, order: OptionOrder, account: AccountInfo) -> bool:
        """Validate an order against all risk rules. Raises on violation."""
        self._reset_daily_if_needed()

        agent_id = order.agent_id

        if agent_id in self._blocked_agents:
            raise RiskLimitExceededError(
                f"Agent {agent_id} is blocked for the day (daily loss limit hit)"
            )

        equity = account.total_equity
        if equity <= 0:
            raise RiskLimitExceededError("Account equity is zero or negative")

        # 1. Max single position size
        max_loss = order.max_loss
        if max_loss == float("inf"):
            raise RiskLimitExceededError(
                "Naked/undefined-risk positions are not allowed"
            )

        max_allowed = equity * self.max_position_size_pct
        if max_loss > max_allowed:
            raise RiskLimitExceededError(
                f"Position max loss ${max_loss:,.0f} exceeds limit ${max_allowed:,.0f} "
                f"({self.max_position_size_pct:.0%} of equity)"
            )

        # 2. Max total exposure per agent
        current_exposure = self._agent_exposure.get(agent_id, 0)
        max_total = equity * self.max_total_exposure_pct
        if current_exposure + max_loss > max_total:
            raise RiskLimitExceededError(
                f"Total exposure ${current_exposure + max_loss:,.0f} would exceed "
                f"limit ${max_total:,.0f} ({self.max_total_exposure_pct:.0%} of equity)"
            )

        # 3. Buying power check
        if max_loss > account.buying_power:
            raise RiskLimitExceededError(
                f"Insufficient buying power: need ${max_loss:,.0f}, "
                f"have ${account.buying_power:,.0f}"
            )

        # 4. Max single loss limit
        max_single = equity * self.max_single_loss_pct
        if max_loss > max_single * 100:  # per contract
            logger.warning(
                f"Large position for {agent_id}: max loss ${max_loss:,.0f} "
                f"vs preferred limit ${max_single:,.0f}"
            )

        # 5. Daily loss limit
        daily_loss = self._daily_losses.get(agent_id, 0)
        daily_limit = equity * self.daily_loss_limit_pct
        if daily_loss >= daily_limit:
            self._blocked_agents.add(agent_id)
            raise RiskLimitExceededError(
                f"Agent {agent_id} hit daily loss limit: "
                f"${daily_loss:,.0f} >= ${daily_limit:,.0f}"
            )

        return True

    def record_fill(self, order: OptionOrder) -> None:
        """Record a filled order for exposure tracking."""
        if order.status == OrderStatus.FILLED:
            max_loss = order.max_loss
            agent_id = order.agent_id
            self._agent_exposure[agent_id] = (
                self._agent_exposure.get(agent_id, 0) + max_loss
            )

    def record_close(self, agent_id: str, pnl: float, max_loss_freed: float) -> None:
        """Record a position close, updating exposure and daily loss."""
        self._agent_exposure[agent_id] = max(
            0, self._agent_exposure.get(agent_id, 0) - max_loss_freed
        )

        if pnl < 0:
            self._daily_losses[agent_id] = (
                self._daily_losses.get(agent_id, 0) + abs(pnl)
            )

    def get_available_risk_budget(self, agent_id: str, equity: float) -> float:
        """How much risk budget does this agent have left?"""
        current = self._agent_exposure.get(agent_id, 0)
        max_total = equity * self.max_total_exposure_pct
        return max(0, max_total - current)

    def get_position_size(
        self,
        agent_id: str,
        equity: float,
        max_loss_per_contract: float,
    ) -> int:
        """Calculate the number of contracts to trade."""
        budget = self.get_available_risk_budget(agent_id, equity)
        max_single = equity * self.max_position_size_pct

        allowable = min(budget, max_single)
        if max_loss_per_contract <= 0:
            return 0

        contracts = int(allowable / max_loss_per_contract)
        return max(0, min(contracts, 10))  # Hard cap at 10 contracts

    def _reset_daily_if_needed(self) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if today != self._daily_reset_date:
            self._daily_losses.clear()
            self._blocked_agents.clear()
            self._daily_reset_date = today

    def get_risk_report(self, equity: float) -> dict[str, Any]:
        """Generate a risk report for display."""
        return {
            "equity": equity,
            "max_position_size": equity * self.max_position_size_pct,
            "max_total_exposure": equity * self.max_total_exposure_pct,
            "daily_loss_limit": equity * self.daily_loss_limit_pct,
            "agent_exposure": dict(self._agent_exposure),
            "daily_losses": dict(self._daily_losses),
            "blocked_agents": list(self._blocked_agents),
        }
