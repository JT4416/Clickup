"""Schwab API client wrapping schwab-py for options trading."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from src.broker.models import (
    AccountInfo,
    OptionContract,
    OptionOrder,
    OptionType,
    OrderAction,
    OrderStatus,
    Position,
    SpreadType,
)
from src.config import settings
from src.utils.exceptions import BrokerConnectionError, InsufficientFundsError, OrderRejectedError


class SchwabClient:
    """Async client for Schwab's Trader API.

    Uses schwab-py for authentication and wraps API calls
    for options-specific operations.
    """

    def __init__(self):
        self._client = None
        self._token_path = Path(settings.schwab_token_path)
        self._account_hash = settings.schwab_account_hash

    async def connect(self) -> None:
        """Establish authenticated connection to Schwab API."""
        try:
            import schwab

            self._client = schwab.auth.client_from_token_file(
                token_path=str(self._token_path),
                api_key=settings.schwab_api_key,
                app_secret=settings.schwab_app_secret,
            )
            logger.info("Connected to Schwab API")
        except FileNotFoundError:
            logger.warning(
                "No token file found. Run initial auth flow first: "
                "python -m scripts.schwab_auth"
            )
            raise BrokerConnectionError("No Schwab token file. Run schwab_auth script first.")
        except Exception as e:
            raise BrokerConnectionError(f"Failed to connect to Schwab: {e}")

    async def get_account_info(self) -> AccountInfo:
        """Fetch current account information and positions."""
        resp = self._client.get_account(
            self._account_hash,
            fields=[self._client.Account.Fields.POSITIONS],
        )
        data = resp.json()
        acct = data["securitiesAccount"]

        positions = []
        for pos in acct.get("positions", []):
            inst = pos["instrument"]
            if inst.get("assetType") == "OPTION":
                positions.append(
                    Position(
                        symbol=inst["symbol"],
                        underlying=inst.get("underlyingSymbol", ""),
                        option_type=OptionType(inst.get("putCall", "CALL")),
                        strike=float(inst.get("strikePrice", 0)),
                        expiration=datetime.fromisoformat(
                            inst.get("expirationDate", datetime.utcnow().isoformat())
                        ),
                        quantity=int(pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)),
                        avg_price=float(pos.get("averagePrice", 0)),
                        current_price=float(pos.get("marketValue", 0))
                        / max(1, abs(int(pos.get("longQuantity", 0) - pos.get("shortQuantity", 0))) * 100),
                    )
                )

        return AccountInfo(
            account_hash=self._account_hash,
            buying_power=float(acct.get("currentBalances", {}).get("buyingPower", 0)),
            cash_balance=float(acct.get("currentBalances", {}).get("cashBalance", 0)),
            total_equity=float(acct.get("currentBalances", {}).get("liquidationValue", 0)),
            positions=positions,
            day_pnl=float(acct.get("currentBalances", {}).get("dayTradingBuyingPower", 0)),
        )

    async def get_option_chain(
        self,
        symbol: str,
        contract_type: str = "ALL",
        strike_count: int = 20,
        days_to_expiration: int | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[OptionContract]:
        """Fetch options chain for a symbol."""
        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "contract_type": self._client.Options.ContractType[contract_type],
            "strike_count": strike_count,
            "include_underlying_quote": True,
            "strategy": self._client.Options.Strategy.ANALYTICAL,
        }

        if from_date:
            kwargs["from_date"] = from_date
        if to_date:
            kwargs["to_date"] = to_date
        elif days_to_expiration:
            kwargs["from_date"] = datetime.utcnow()
            kwargs["to_date"] = datetime.utcnow() + timedelta(days=days_to_expiration)

        resp = self._client.get_option_chain(**kwargs)
        data = resp.json()

        contracts = []
        for map_type in ("callExpDateMap", "putExpDateMap"):
            option_type = OptionType.CALL if "call" in map_type.lower() else OptionType.PUT
            exp_map = data.get(map_type, {})
            for exp_date_str, strikes in exp_map.items():
                for strike_str, chain_list in strikes.items():
                    for opt in chain_list:
                        contracts.append(
                            OptionContract(
                                symbol=opt.get("symbol", ""),
                                underlying=symbol,
                                option_type=option_type,
                                strike=float(strike_str),
                                expiration=datetime.fromisoformat(
                                    exp_date_str.split(":")[0]
                                ),
                                bid=float(opt.get("bid", 0)),
                                ask=float(opt.get("ask", 0)),
                                last=float(opt.get("last", 0)),
                                volume=int(opt.get("totalVolume", 0)),
                                open_interest=int(opt.get("openInterest", 0)),
                                implied_volatility=float(opt.get("volatility", 0)),
                                delta=float(opt.get("delta", 0)),
                                gamma=float(opt.get("gamma", 0)),
                                theta=float(opt.get("theta", 0)),
                                vega=float(opt.get("vega", 0)),
                                rho=float(opt.get("rho", 0)),
                            )
                        )
        return contracts

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get current quote for a symbol."""
        resp = self._client.get_quote(symbol)
        return resp.json().get(symbol, {}).get("quote", {})

    async def place_option_order(self, order: OptionOrder) -> OptionOrder:
        """Place an options order on Schwab."""
        import schwab.orders.options as opts

        if settings.paper_trade:
            logger.info(f"[PAPER] Would place order: {order.spread_type} on {order.contracts[0].underlying}")
            order.status = OrderStatus.FILLED
            order.filled_price = order.limit_price or order.contracts[0].mid
            order.filled_at = datetime.utcnow()
            order.order_id = f"PAPER-{datetime.utcnow().timestamp()}"
            return order

        # Build order spec based on spread type
        order_spec = self._build_order_spec(order)

        try:
            resp = self._client.place_order(self._account_hash, order_spec)
            if resp.status_code in (200, 201):
                order_id = resp.headers.get("Location", "").split("/")[-1]
                order.order_id = order_id
                order.status = OrderStatus.PENDING
                logger.info(f"Order placed: {order_id}")
            else:
                raise OrderRejectedError(f"Order rejected: {resp.status_code} {resp.text}")
        except OrderRejectedError:
            raise
        except Exception as e:
            raise OrderRejectedError(f"Failed to place order: {e}")

        return order

    def _build_order_spec(self, order: OptionOrder) -> dict:
        """Build Schwab order specification from our order model."""
        import schwab.orders.options as opts

        contract = order.contracts[0]

        if order.spread_type == SpreadType.SINGLE:
            action = order.actions[0]
            quantity = order.quantities[0]

            if action == OrderAction.BUY_TO_OPEN:
                builder = opts.option_buy_to_open_limit(
                    contract.symbol, quantity, order.limit_price or contract.ask
                )
            elif action == OrderAction.SELL_TO_OPEN:
                builder = opts.option_sell_to_open_limit(
                    contract.symbol, quantity, order.limit_price or contract.bid
                )
            elif action == OrderAction.BUY_TO_CLOSE:
                builder = opts.option_buy_to_close_limit(
                    contract.symbol, quantity, order.limit_price or contract.ask
                )
            else:
                builder = opts.option_sell_to_close_limit(
                    contract.symbol, quantity, order.limit_price or contract.bid
                )
            return builder.build()

        if order.spread_type == SpreadType.VERTICAL:
            return self._build_vertical_spread(order)

        # For complex spreads, build a generic multi-leg order
        return self._build_multi_leg_order(order)

    def _build_vertical_spread(self, order: OptionOrder) -> dict:
        """Build a vertical spread order."""
        legs = []
        for contract, action, qty in zip(order.contracts, order.actions, order.quantities):
            instruction = action.value
            legs.append({
                "instruction": instruction,
                "quantity": qty,
                "instrument": {
                    "symbol": contract.symbol,
                    "assetType": "OPTION",
                },
            })

        return {
            "orderType": "NET_DEBIT" if order.limit_price and order.limit_price > 0 else "NET_CREDIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": str(abs(order.limit_price or 0)),
            "orderLegCollection": legs,
        }

    def _build_multi_leg_order(self, order: OptionOrder) -> dict:
        """Build a generic multi-leg options order."""
        legs = []
        for contract, action, qty in zip(order.contracts, order.actions, order.quantities):
            legs.append({
                "instruction": action.value,
                "quantity": qty,
                "instrument": {
                    "symbol": contract.symbol,
                    "assetType": "OPTION",
                },
            })

        return {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "price": str(abs(order.limit_price or 0)),
            "orderLegCollection": legs,
        }

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if settings.paper_trade:
            logger.info(f"[PAPER] Would cancel order: {order_id}")
            return True

        try:
            resp = self._client.cancel_order(order_id, self._account_hash)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str) -> OrderStatus:
        """Check the status of an existing order."""
        if settings.paper_trade:
            return OrderStatus.FILLED

        resp = self._client.get_order(order_id, self._account_hash)
        data = resp.json()
        status_str = data.get("status", "PENDING")
        return OrderStatus(status_str)

    async def disconnect(self) -> None:
        """Clean up client resources."""
        self._client = None
        logger.info("Disconnected from Schwab API")
