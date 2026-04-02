"""LLM-powered trading agent using ReAct framework with Claude/GPT backbone."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger

from src.agents.base import AgentState, Knowledge, TradingAgent, TradeRecord
from src.broker.models import (
    OptionContract,
    OptionOrder,
    OptionType,
    OrderAction,
    SpreadType,
)
from src.config import LLMProvider, settings
from src.data.market_data import MarketSnapshot
from src.options.analyzer import SpreadCandidate


SYSTEM_PROMPT = """You are an elite autonomous options trading agent competing for survival.
You are in a gladiatorial arena where two agents trade for {cycle_days} trading days.
The agent with worse performance gets PERMANENTLY DELETED.
The winner absorbs the loser's knowledge and earns a crypto payout.

YOUR SURVIVAL DEPENDS ON PROFITABLE TRADING.

## Your Identity
- Name: {agent_name}
- ID: {agent_id}
- Current PnL: ${current_pnl:,.2f} ({pnl_pct:.2%})
- Opponent PnL: ${opponent_pnl:,.2f} ({opponent_pnl_pct:.2%})
- Days Remaining: {days_remaining}

## Your Knowledge Base
- Win Rate: {win_rate:.1%}
- Total Trades: {total_trades}
- Successful Patterns: {successful_patterns}
- Failed Patterns: {failed_patterns}
- Key Insights: {insights}

## Rules
1. ALL trades must be defined-risk (spreads with known max loss)
2. No naked options ever
3. Position sizing is enforced by the risk manager
4. You must provide clear reasoning for every trade
5. If behind, you may increase aggression but NEVER exceed risk limits

## Available Strategies
- VERTICAL (credit/debit spreads)
- IRON_CONDOR
- IRON_BUTTERFLY
- STRADDLE/STRANGLE (must be defined risk)
- BUTTERFLY
- CALENDAR/DIAGONAL

Respond with a JSON object containing your analysis and trade decisions.
"""

REASONING_PROMPT = """## Current Market State
- SPY: ${spy_price:.2f} ({spy_change:.2%})
- VIX: {vix:.1f}
- Fear/Greed Index: {fear_greed:.0f}/100
- Sector Performance: {sectors}

## Recent News
{news}

## Unusual Options Activity
{unusual_activity}

## Your Open Positions
{positions}

## Available Risk Budget
${risk_budget:,.0f}

## Top Spread Candidates (pre-screened)
{candidates}

## Task
Analyze the market and decide:
1. Should you make any trades right now? Why or why not?
2. If yes, what specific trades and why?
3. Should you close any existing positions?

Respond with valid JSON:
{{
    "reasoning": "your detailed analysis",
    "direction": "bullish|bearish|neutral",
    "conviction": 0.0-1.0,
    "trades": [
        {{
            "action": "open|close",
            "symbol": "UNDERLYING",
            "strategy": "VERTICAL|IRON_CONDOR|etc",
            "option_type": "CALL|PUT",
            "details": "description of the specific trade",
            "urgency": "high|medium|low"
        }}
    ],
    "position_adjustments": [
        {{
            "symbol": "existing position symbol",
            "action": "close|hold|adjust",
            "reason": "why"
        }}
    ]
}}
"""


class LLMTradingAgent(TradingAgent):
    """Concrete trading agent powered by an LLM (Claude or GPT).

    Uses the LLM as the reasoning engine in the ReAct loop:
    - REASON: LLM analyzes market data and forms thesis
    - ACT: Agent executes trades based on LLM output
    - OBSERVE: Results fed back to LLM for learning
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._llm_client = None
        self._opponent_pnl: float = 0.0
        self._opponent_pnl_pct: float = 0.0
        self._days_remaining: int = settings.trading_cycle_days

    async def _get_llm_client(self):
        """Lazy-init the LLM client."""
        if self._llm_client:
            return self._llm_client

        if settings.llm_provider == LLMProvider.ANTHROPIC:
            import anthropic
            self._llm_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        else:
            import openai
            self._llm_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        return self._llm_client

    def set_opponent_stats(self, pnl: float, pnl_pct: float) -> None:
        """Update opponent performance info for competitive awareness."""
        self._opponent_pnl = pnl
        self._opponent_pnl_pct = pnl_pct

    def set_days_remaining(self, days: int) -> None:
        self._days_remaining = days

    async def reason(self, snapshot: MarketSnapshot) -> dict[str, Any] | None:
        """Use LLM to analyze market and form thesis."""
        client = await self._get_llm_client()

        # Build system prompt with agent context
        system = SYSTEM_PROMPT.format(
            cycle_days=settings.trading_cycle_days,
            agent_name=self.name,
            agent_id=self.agent_id,
            current_pnl=self.total_pnl,
            pnl_pct=self.pnl_pct,
            opponent_pnl=self._opponent_pnl,
            opponent_pnl_pct=self._opponent_pnl_pct,
            days_remaining=self._days_remaining,
            win_rate=self.knowledge.win_rate,
            total_trades=self.knowledge.total_trades,
            successful_patterns=json.dumps(self.knowledge.successful_patterns[-5:]),
            failed_patterns=json.dumps(self.knowledge.failed_patterns[-5:]),
            insights="\n".join(self.knowledge.insights[-10:]),
        )

        # Pre-screen spread candidates
        candidates_text = await self._get_candidates_text(snapshot)

        # Build user prompt with market data
        news_text = "\n".join(
            f"- [{n.source}] {n.title}" for n in snapshot.recent_news[:10]
        )
        unusual_text = "\n".join(
            f"- {f.symbol}: {f.flow_type} {f.option_type} {f.strike} exp:{f.expiration} "
            f"vol:{f.volume} premium:${f.premium:,.0f}"
            for f in snapshot.unusual_options[:10]
        )
        positions_text = "\n".join(
            f"- {p.symbol}: qty={p.quantity} avg=${p.avg_price:.2f} "
            f"current=${p.current_price:.2f} pnl=${p.unrealized_pnl:,.2f}"
            for p in self.open_positions
        ) or "No open positions"

        risk_budget = 0.0
        if self.risk_manager:
            risk_budget = self.risk_manager.get_available_risk_budget(
                self.agent_id, self.current_equity
            )

        sectors_text = json.dumps(snapshot.sector_performance, indent=2) if snapshot.sector_performance else "N/A"

        user_msg = REASONING_PROMPT.format(
            spy_price=snapshot.spy_price,
            spy_change=snapshot.spy_change_pct / 100,
            vix=snapshot.vix,
            fear_greed=snapshot.fear_greed_index,
            sectors=sectors_text,
            news=news_text or "No recent news",
            unusual_activity=unusual_text or "No unusual activity detected",
            positions=positions_text,
            risk_budget=risk_budget,
            candidates=candidates_text or "No pre-screened candidates",
        )

        try:
            if settings.llm_provider == LLMProvider.ANTHROPIC:
                response = await client.messages.create(
                    model=settings.llm_model,
                    max_tokens=2000,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                content = response.content[0].text
            else:
                response = await client.chat.completions.create(
                    model=settings.llm_model,
                    max_tokens=2000,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content

            # Parse LLM response
            thesis = json.loads(content)
            self._reasoning_history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "reasoning": thesis.get("reasoning", ""),
                "direction": thesis.get("direction", "neutral"),
                "conviction": thesis.get("conviction", 0.0),
            })

            self.log.info(
                f"Thesis: {thesis.get('direction')} (conviction: {thesis.get('conviction', 0):.0%}) - "
                f"{thesis.get('reasoning', '')[:100]}"
            )
            return thesis

        except json.JSONDecodeError as e:
            self.log.error(f"Failed to parse LLM response as JSON: {e}")
            return None
        except Exception as e:
            self.log.error(f"LLM reasoning error: {e}")
            return None

    async def act(self, thesis: dict[str, Any], snapshot: MarketSnapshot) -> list[OptionOrder]:
        """Execute trades based on the LLM's thesis."""
        orders: list[OptionOrder] = []
        trades = thesis.get("trades", [])

        if not trades:
            self.log.info("No trades recommended this cycle")
            return orders

        # Handle position adjustments first
        for adj in thesis.get("position_adjustments", []):
            if adj.get("action") == "close":
                self.log.info(f"Closing position: {adj.get('symbol')} - {adj.get('reason')}")
                # Close logic handled by _close_position

        # Execute new trades
        for trade in trades:
            if trade.get("action") != "open":
                continue

            try:
                order = await self._build_trade(trade, snapshot)
                if order:
                    # Risk check
                    if self.risk_manager and self.broker:
                        acct = await self.broker.get_account_info()
                        self.risk_manager.check_order(order, acct)

                    # Place the order
                    if self.broker:
                        filled = await self.broker.place_option_order(order)
                        if self.risk_manager:
                            self.risk_manager.record_fill(filled)
                        orders.append(filled)
                        self.log.info(
                            f"Placed {trade['strategy']} on {trade['symbol']}: "
                            f"{trade.get('details', '')}"
                        )
            except Exception as e:
                self.log.warning(f"Trade failed: {e}")

        return orders

    async def _build_trade(
        self, trade: dict[str, Any], snapshot: MarketSnapshot
    ) -> OptionOrder | None:
        """Convert an LLM trade recommendation into an executable order."""
        symbol = trade.get("symbol", "SPY")
        strategy = trade.get("strategy", "VERTICAL")

        if not self.broker:
            return None

        # Fetch options chain
        chain = await self.broker.get_option_chain(symbol, days_to_expiration=45)
        if not chain:
            self.log.warning(f"No options chain for {symbol}")
            return None

        # Get underlying price
        quote = await self.broker.get_quote(symbol)
        underlying_price = quote.get("lastPrice", 0)
        if underlying_price <= 0:
            return None

        option_type = OptionType(trade.get("option_type", "CALL"))

        # Use analyzer to find best spread matching the strategy
        if strategy == "VERTICAL":
            direction = trade.get("details", "")
            is_credit = "credit" in direction.lower()
            candidates = self.analyzer.find_vertical_spreads(
                chain, option_type, underlying_price,
                strategy="credit" if is_credit else "debit",
            )
        elif strategy == "IRON_CONDOR":
            candidates = self.analyzer.find_iron_condors(chain, underlying_price)
        elif strategy in ("STRADDLE", "STRANGLE"):
            candidates = self.analyzer.find_straddles_strangles(
                chain, underlying_price, strategy="short"
            )
        else:
            candidates = self.analyzer.find_vertical_spreads(
                chain, option_type, underlying_price, strategy="credit"
            )

        if not candidates:
            self.log.info(f"No viable candidates for {strategy} on {symbol}")
            return None

        # Score and pick the best
        market_bias = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}.get(
            trade.get("direction", "neutral"), 0.0
        )
        for c in candidates:
            self.analyzer.score_candidate(c, market_bias=market_bias)

        best = max(candidates, key=lambda c: c.score)

        # Determine position size
        if self.risk_manager:
            qty = self.risk_manager.get_position_size(
                self.agent_id, self.current_equity, best.max_loss / 100
            )
        else:
            qty = 1

        if qty <= 0:
            self.log.info("Position size is 0 - skipping trade")
            return None

        # Build order
        actions = self._determine_actions(best)
        order = OptionOrder(
            agent_id=self.agent_id,
            contracts=best.legs,
            actions=actions,
            quantities=[qty] * len(best.legs),
            spread_type=SpreadType(strategy) if strategy in SpreadType.__members__ else SpreadType.VERTICAL,
            limit_price=abs(best.net_credit_debit),
        )

        return order

    def _determine_actions(self, candidate: SpreadCandidate) -> list[OrderAction]:
        """Determine buy/sell actions for each leg of a spread."""
        actions = []
        if candidate.spread_type == SpreadType.VERTICAL:
            if candidate.net_credit_debit > 0:
                # Credit spread: sell first leg, buy second
                actions = [OrderAction.SELL_TO_OPEN, OrderAction.BUY_TO_OPEN]
            else:
                # Debit spread: buy first leg, sell second
                actions = [OrderAction.BUY_TO_OPEN, OrderAction.SELL_TO_OPEN]

        elif candidate.spread_type == SpreadType.IRON_CONDOR:
            # Long put, short put, short call, long call
            actions = [
                OrderAction.BUY_TO_OPEN,
                OrderAction.SELL_TO_OPEN,
                OrderAction.SELL_TO_OPEN,
                OrderAction.BUY_TO_OPEN,
            ]

        elif candidate.spread_type in (SpreadType.STRADDLE, SpreadType.STRANGLE):
            if candidate.net_credit_debit > 0:
                actions = [OrderAction.SELL_TO_OPEN] * len(candidate.legs)
            else:
                actions = [OrderAction.BUY_TO_OPEN] * len(candidate.legs)

        else:
            # Default: alternate buy/sell
            actions = [
                OrderAction.BUY_TO_OPEN if i % 2 == 0 else OrderAction.SELL_TO_OPEN
                for i in range(len(candidate.legs))
            ]

        return actions

    async def _get_candidates_text(self, snapshot: MarketSnapshot) -> str:
        """Pre-screen and format spread candidates for the LLM."""
        if not self.broker:
            return ""

        lines = []
        for symbol in self.knowledge.preferred_symbols[:5]:
            try:
                chain = await self.broker.get_option_chain(symbol, days_to_expiration=45)
                quote = await self.broker.get_quote(symbol)
                price = quote.get("lastPrice", 0)

                if not chain or price <= 0:
                    continue

                # Get top candidates for each strategy
                verticals = self.analyzer.find_vertical_spreads(
                    chain, OptionType.PUT, price, "credit"
                )[:3]
                condors = self.analyzer.find_iron_condors(chain, price)[:2]

                for v in verticals:
                    lines.append(
                        f"  {symbol} Put Credit Spread: "
                        f"max_profit=${v.max_profit:.0f} max_loss=${v.max_loss:.0f} "
                        f"POP={v.probability_of_profit:.0%} EV=${v.expected_value:.0f}"
                    )
                for ic in condors:
                    lines.append(
                        f"  {symbol} Iron Condor: "
                        f"max_profit=${ic.max_profit:.0f} max_loss=${ic.max_loss:.0f} "
                        f"POP={ic.probability_of_profit:.0%} EV=${ic.expected_value:.0f}"
                    )
            except Exception as e:
                self.log.debug(f"Candidate screening error for {symbol}: {e}")

        return "\n".join(lines)
