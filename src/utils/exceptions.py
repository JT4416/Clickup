"""Custom exceptions for the trading system."""


class GladiatorError(Exception):
    """Base exception for all gladiator errors."""


class BrokerConnectionError(GladiatorError):
    """Failed to connect to Schwab API."""


class OrderRejectedError(GladiatorError):
    """Order was rejected by the broker."""


class RiskLimitExceededError(GladiatorError):
    """Trade would exceed risk limits."""


class InsufficientFundsError(GladiatorError):
    """Not enough buying power for the trade."""


class AgentDeletionError(GladiatorError):
    """Error during agent deletion process."""


class KnowledgeTransferError(GladiatorError):
    """Error transferring knowledge between agents."""


class DataFeedError(GladiatorError):
    """Error in market data feed."""


class CryptoPayoutError(GladiatorError):
    """Error executing crypto payout."""
