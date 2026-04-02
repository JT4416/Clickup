"""Crypto payout engine - rewards the winning agent's owner."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from src.config import settings
from src.utils.exceptions import CryptoPayoutError


class PayoutRecord(BaseModel):
    """Record of a crypto payout."""
    amount_usd: float
    amount_crypto: float
    coin: str
    wallet_address: str
    tx_id: str
    exchange: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"


class CryptoPayoutEngine:
    """Handles crypto payouts to the designated wallet.

    Uses CCXT for exchange-agnostic crypto operations.
    Converts USD profit amount to the chosen cryptocurrency
    and sends it to the configured wallet.
    """

    def __init__(self):
        self._exchange = None
        self._payout_history: list[PayoutRecord] = []

    async def initialize(self) -> None:
        """Initialize the exchange connection."""
        if not settings.crypto_exchange_api_key:
            logger.warning("No crypto exchange credentials configured. Payouts will be simulated.")
            return

        try:
            import ccxt.async_support as ccxt

            exchange_class = getattr(ccxt, settings.crypto_exchange, None)
            if not exchange_class:
                raise CryptoPayoutError(f"Unknown exchange: {settings.crypto_exchange}")

            self._exchange = exchange_class({
                "apiKey": settings.crypto_exchange_api_key,
                "secret": settings.crypto_exchange_secret,
                "enableRateLimit": True,
            })

            # Verify connection
            await self._exchange.load_markets()
            logger.info(f"Connected to {settings.crypto_exchange} for payouts")

        except ImportError:
            logger.warning("ccxt not installed. Payouts will be simulated.")
        except Exception as e:
            logger.error(f"Failed to initialize crypto exchange: {e}")

    async def execute_payout(self, amount_usd: float) -> str:
        """Execute a crypto payout for the given USD amount.

        Returns the transaction ID.
        """
        if amount_usd <= 0:
            logger.info("No payout needed (no profit)")
            return ""

        coin = settings.payout_coin
        wallet = settings.payout_wallet_address

        if not wallet:
            logger.warning("No payout wallet configured")
            return "NO_WALLET_CONFIGURED"

        # Get crypto price and calculate amount
        crypto_amount = await self._usd_to_crypto(amount_usd, coin)

        if not self._exchange:
            # Simulated payout
            tx_id = f"SIM-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            logger.info(
                f"[SIMULATED] Payout: ${amount_usd:,.2f} -> "
                f"{crypto_amount:.8f} {coin} -> {wallet[:16]}..."
            )
            record = PayoutRecord(
                amount_usd=amount_usd,
                amount_crypto=crypto_amount,
                coin=coin,
                wallet_address=wallet,
                tx_id=tx_id,
                exchange="simulated",
                status="simulated",
            )
            self._payout_history.append(record)
            return tx_id

        # Real payout via exchange withdrawal
        try:
            withdrawal = await self._exchange.withdraw(
                code=coin,
                amount=crypto_amount,
                address=wallet,
            )
            tx_id = withdrawal.get("id", "unknown")

            record = PayoutRecord(
                amount_usd=amount_usd,
                amount_crypto=crypto_amount,
                coin=coin,
                wallet_address=wallet,
                tx_id=tx_id,
                exchange=settings.crypto_exchange,
                status="submitted",
            )
            self._payout_history.append(record)

            logger.info(
                f"Payout submitted: ${amount_usd:,.2f} -> "
                f"{crypto_amount:.8f} {coin} -> {wallet[:16]}... TX: {tx_id}"
            )
            return tx_id

        except Exception as e:
            raise CryptoPayoutError(f"Payout failed: {e}")

    async def _usd_to_crypto(self, usd_amount: float, coin: str) -> float:
        """Convert USD amount to crypto amount at current market price."""
        if not self._exchange:
            # Fallback estimates
            estimates = {"BTC": 65000, "ETH": 3500, "SOL": 150, "USDC": 1.0, "USDT": 1.0}
            price = estimates.get(coin, 1.0)
            return usd_amount / price

        try:
            ticker = await self._exchange.fetch_ticker(f"{coin}/USDT")
            price = ticker.get("last", 0)
            if price <= 0:
                raise CryptoPayoutError(f"Invalid price for {coin}/USDT: {price}")
            return usd_amount / price
        except Exception as e:
            raise CryptoPayoutError(f"Failed to get {coin} price: {e}")

    def get_payout_history(self) -> list[dict[str, Any]]:
        """Get history of all payouts."""
        return [p.model_dump(mode="json") for p in self._payout_history]

    async def shutdown(self) -> None:
        """Clean up exchange connection."""
        if self._exchange:
            await self._exchange.close()
            logger.info("Crypto exchange connection closed")
