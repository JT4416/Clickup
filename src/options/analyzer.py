"""Options analysis engine - greeks, spreads, strategy evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.broker.models import OptionContract, OptionType, SpreadType


@dataclass
class SpreadCandidate:
    """A potential spread trade with computed metrics."""
    spread_type: SpreadType
    legs: list[OptionContract]
    max_profit: float
    max_loss: float
    breakeven: list[float]
    probability_of_profit: float
    risk_reward_ratio: float
    expected_value: float
    net_credit_debit: float  # positive = credit, negative = debit
    net_delta: float
    net_theta: float
    net_vega: float
    score: float = 0.0  # Overall attractiveness score

    @property
    def return_on_risk(self) -> float:
        if self.max_loss == 0:
            return 0.0
        return self.max_profit / self.max_loss


class OptionsAnalyzer:
    """Analyzes options chains and identifies optimal spread strategies."""

    def find_vertical_spreads(
        self,
        chain: list[OptionContract],
        option_type: OptionType,
        underlying_price: float,
        strategy: str = "credit",  # "credit" or "debit"
    ) -> list[SpreadCandidate]:
        """Find and rank vertical spread candidates."""
        contracts = sorted(
            [c for c in chain if c.option_type == option_type],
            key=lambda c: c.strike,
        )

        if len(contracts) < 2:
            return []

        candidates = []
        for i, short_leg in enumerate(contracts):
            for long_leg in contracts[i + 1 :]:
                if long_leg.strike - short_leg.strike > underlying_price * 0.1:
                    break  # Skip very wide spreads

                if strategy == "credit":
                    candidate = self._evaluate_credit_spread(
                        short_leg, long_leg, option_type, underlying_price
                    )
                else:
                    candidate = self._evaluate_debit_spread(
                        short_leg, long_leg, option_type, underlying_price
                    )

                if candidate and candidate.risk_reward_ratio > 0.2:
                    candidates.append(candidate)

        # Sort by expected value descending
        candidates.sort(key=lambda c: c.expected_value, reverse=True)
        return candidates[:20]

    def find_iron_condors(
        self,
        chain: list[OptionContract],
        underlying_price: float,
    ) -> list[SpreadCandidate]:
        """Find iron condor candidates."""
        calls = sorted(
            [c for c in chain if c.option_type == OptionType.CALL and c.strike > underlying_price],
            key=lambda c: c.strike,
        )
        puts = sorted(
            [c for c in chain if c.option_type == OptionType.PUT and c.strike < underlying_price],
            key=lambda c: c.strike,
            reverse=True,
        )

        if len(calls) < 2 or len(puts) < 2:
            return []

        candidates = []
        for i in range(min(5, len(puts) - 1)):
            for j in range(min(5, len(calls) - 1)):
                short_put = puts[i]
                long_put = puts[i + 1] if i + 1 < len(puts) else None
                short_call = calls[j]
                long_call = calls[j + 1] if j + 1 < len(calls) else None

                if not long_put or not long_call:
                    continue

                credit = (short_put.mid + short_call.mid) - (long_put.mid + long_call.mid)
                put_width = short_put.strike - long_put.strike
                call_width = long_call.strike - short_call.strike
                max_width = max(put_width, call_width)
                max_loss = (max_width - credit) * 100

                if credit <= 0 or max_loss <= 0:
                    continue

                # Estimate POP using delta
                pop = 1 - abs(short_put.delta) - abs(short_call.delta)
                pop = max(0.1, min(0.95, pop))

                ev = credit * 100 * pop - max_loss * (1 - pop)

                candidates.append(
                    SpreadCandidate(
                        spread_type=SpreadType.IRON_CONDOR,
                        legs=[long_put, short_put, short_call, long_call],
                        max_profit=credit * 100,
                        max_loss=max_loss,
                        breakeven=[short_put.strike - credit, short_call.strike + credit],
                        probability_of_profit=pop,
                        risk_reward_ratio=credit * 100 / max_loss,
                        expected_value=ev,
                        net_credit_debit=credit,
                        net_delta=sum(c.delta for c in [long_put, short_put, short_call, long_call]),
                        net_theta=sum(c.theta for c in [long_put, short_put, short_call, long_call]),
                        net_vega=sum(c.vega for c in [long_put, short_put, short_call, long_call]),
                    )
                )

        candidates.sort(key=lambda c: c.expected_value, reverse=True)
        return candidates[:10]

    def find_straddles_strangles(
        self,
        chain: list[OptionContract],
        underlying_price: float,
        strategy: str = "short",  # "long" or "short"
    ) -> list[SpreadCandidate]:
        """Find straddle/strangle candidates for volatility plays."""
        candidates = []

        calls = {c.strike: c for c in chain if c.option_type == OptionType.CALL}
        puts = {c.strike: c for c in chain if c.option_type == OptionType.PUT}

        common_strikes = set(calls.keys()) & set(puts.keys())

        for strike in sorted(common_strikes):
            call = calls[strike]
            put = puts[strike]

            # Straddle (same strike)
            total_premium = call.mid + put.mid
            if total_premium <= 0:
                continue

            if strategy == "short":
                max_profit = total_premium * 100
                max_loss = float("inf")
                pop = 1 - abs(call.delta) - abs(put.delta)
                pop = max(0.1, min(0.9, pop + 0.2))  # Short straddles have higher POP
                ev = max_profit * pop - max_profit * 2 * (1 - pop)  # Rough estimate
            else:
                max_profit = float("inf")
                max_loss = total_premium * 100
                pop = abs(call.delta) + abs(put.delta) - 1
                pop = max(0.1, min(0.6, pop))
                ev = max_loss * 2 * pop - max_loss * (1 - pop)

            candidates.append(
                SpreadCandidate(
                    spread_type=SpreadType.STRADDLE,
                    legs=[put, call],
                    max_profit=max_profit if max_profit != float("inf") else total_premium * 300,
                    max_loss=max_loss if max_loss != float("inf") else total_premium * 300,
                    breakeven=[strike - total_premium, strike + total_premium],
                    probability_of_profit=pop,
                    risk_reward_ratio=1.0 if max_loss == float("inf") else max_profit / max(1, max_loss),
                    expected_value=ev,
                    net_credit_debit=total_premium if strategy == "short" else -total_premium,
                    net_delta=call.delta + put.delta,
                    net_theta=call.theta + put.theta,
                    net_vega=call.vega + put.vega,
                )
            )

        candidates.sort(key=lambda c: c.expected_value, reverse=True)
        return candidates[:10]

    def _evaluate_credit_spread(
        self,
        short: OptionContract,
        long: OptionContract,
        option_type: OptionType,
        underlying_price: float,
    ) -> SpreadCandidate | None:
        """Evaluate a credit spread (sell near, buy far)."""
        if option_type == OptionType.PUT:
            # Bull put spread: sell higher strike put, buy lower
            credit = short.mid - long.mid
        else:
            # Bear call spread: sell lower strike call, buy higher
            credit = short.mid - long.mid

        if credit <= 0:
            return None

        width = abs(long.strike - short.strike)
        max_loss = (width - credit) * 100
        max_profit = credit * 100

        if max_loss <= 0:
            return None

        # POP estimated from short leg delta
        pop = 1 - abs(short.delta)
        pop = max(0.1, min(0.95, pop))

        ev = max_profit * pop - max_loss * (1 - pop)

        return SpreadCandidate(
            spread_type=SpreadType.VERTICAL,
            legs=[short, long],
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[short.strike - credit] if option_type == OptionType.PUT
            else [short.strike + credit],
            probability_of_profit=pop,
            risk_reward_ratio=max_profit / max_loss,
            expected_value=ev,
            net_credit_debit=credit,
            net_delta=short.delta + long.delta,
            net_theta=short.theta + long.theta,
            net_vega=short.vega + long.vega,
        )

    def _evaluate_debit_spread(
        self,
        lower: OptionContract,
        upper: OptionContract,
        option_type: OptionType,
        underlying_price: float,
    ) -> SpreadCandidate | None:
        """Evaluate a debit spread."""
        if option_type == OptionType.CALL:
            # Bull call: buy lower, sell upper
            debit = lower.mid - upper.mid
        else:
            # Bear put: buy upper, sell lower
            debit = upper.mid - lower.mid

        if debit <= 0:
            return None

        width = abs(upper.strike - lower.strike)
        max_profit = (width - debit) * 100
        max_loss = debit * 100

        if max_profit <= 0:
            return None

        pop = abs(lower.delta) if option_type == OptionType.CALL else abs(upper.delta)
        pop = max(0.1, min(0.9, pop))

        ev = max_profit * pop - max_loss * (1 - pop)

        return SpreadCandidate(
            spread_type=SpreadType.VERTICAL,
            legs=[lower, upper],
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven=[lower.strike + debit] if option_type == OptionType.CALL
            else [upper.strike - debit],
            probability_of_profit=pop,
            risk_reward_ratio=max_profit / max_loss,
            expected_value=ev,
            net_credit_debit=-debit,
            net_delta=lower.delta + upper.delta,
            net_theta=lower.theta + upper.theta,
            net_vega=lower.vega + upper.vega,
        )

    def score_candidate(
        self,
        candidate: SpreadCandidate,
        market_bias: float = 0.0,  # -1 bearish, 0 neutral, 1 bullish
        vol_outlook: float = 0.0,  # -1 vol crush, 0 neutral, 1 vol expansion
    ) -> float:
        """Score a spread candidate based on market conditions and metrics."""
        score = 0.0

        # Expected value weight (40%)
        if candidate.max_loss > 0:
            ev_ratio = candidate.expected_value / candidate.max_loss
            score += min(1.0, max(-1.0, ev_ratio)) * 40

        # Probability of profit (25%)
        score += candidate.probability_of_profit * 25

        # Risk/reward (15%)
        rr = min(2.0, candidate.risk_reward_ratio) / 2.0
        score += rr * 15

        # Delta alignment with market bias (10%)
        if market_bias != 0:
            delta_alignment = candidate.net_delta * market_bias
            score += min(1.0, max(-1.0, delta_alignment * 5)) * 10

        # Vega alignment with vol outlook (10%)
        if vol_outlook != 0:
            vega_alignment = candidate.net_vega * vol_outlook
            score += min(1.0, max(-1.0, vega_alignment * 2)) * 10

        candidate.score = score
        return score
