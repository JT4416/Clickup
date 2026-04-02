"""Data models for broker operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class OrderAction(str, Enum):
    BUY_TO_OPEN = "BUY_TO_OPEN"
    BUY_TO_CLOSE = "BUY_TO_CLOSE"
    SELL_TO_OPEN = "SELL_TO_OPEN"
    SELL_TO_CLOSE = "SELL_TO_CLOSE"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class SpreadType(str, Enum):
    SINGLE = "SINGLE"
    VERTICAL = "VERTICAL"
    CALENDAR = "CALENDAR"
    DIAGONAL = "DIAGONAL"
    STRADDLE = "STRADDLE"
    STRANGLE = "STRANGLE"
    BUTTERFLY = "BUTTERFLY"
    CONDOR = "CONDOR"
    IRON_CONDOR = "IRON_CONDOR"
    IRON_BUTTERFLY = "IRON_BUTTERFLY"


class OptionContract(BaseModel):
    symbol: str
    underlying: str
    option_type: OptionType
    strike: float
    expiration: datetime
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: int = 0
    open_interest: int = 0
    implied_volatility: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_width(self) -> float:
        return self.ask - self.bid


class OptionOrder(BaseModel):
    order_id: str | None = None
    agent_id: str
    contracts: list[OptionContract]
    actions: list[OrderAction]
    quantities: list[int]
    spread_type: SpreadType = SpreadType.SINGLE
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float | None = None
    filled_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def max_loss(self) -> float:
        """Calculate maximum possible loss for this order."""
        if self.spread_type == SpreadType.SINGLE:
            if self.actions[0] in (OrderAction.BUY_TO_OPEN, OrderAction.BUY_TO_CLOSE):
                return self.contracts[0].ask * self.quantities[0] * 100
            else:
                return float("inf")  # Naked short - theoretically unlimited

        if self.spread_type in (SpreadType.VERTICAL, SpreadType.IRON_CONDOR, SpreadType.IRON_BUTTERFLY):
            # Defined risk spread
            strikes = sorted(c.strike for c in self.contracts)
            width = strikes[-1] - strikes[0]
            credit = sum(
                c.mid * (-1 if a in (OrderAction.SELL_TO_OPEN, OrderAction.SELL_TO_CLOSE) else 1)
                for c, a in zip(self.contracts, self.actions)
            )
            return (width - abs(credit)) * self.quantities[0] * 100

        # Conservative fallback
        return sum(c.ask * q * 100 for c, q in zip(self.contracts, self.quantities))


class Position(BaseModel):
    symbol: str
    underlying: str
    option_type: OptionType
    strike: float
    expiration: datetime
    quantity: int
    avg_price: float
    current_price: float = 0.0
    agent_id: str = ""

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity * 100

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_price) * self.quantity * 100

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.avg_price == 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price


class AccountInfo(BaseModel):
    account_hash: str
    buying_power: float = 0.0
    cash_balance: float = 0.0
    total_equity: float = 0.0
    positions: list[Position] = Field(default_factory=list)
    day_pnl: float = 0.0
