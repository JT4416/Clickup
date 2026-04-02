"""CLI interface for the Gladiator Options trading system."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from src.config import settings

console = Console()


@click.group()
def cli():
    """Gladiator Options - Autonomous Competing Trading Agents"""
    pass


@cli.command()
def auth():
    """Run Schwab OAuth2 authentication flow."""
    console.print("[bold]Starting Schwab OAuth2 flow...[/bold]")
    console.print(f"Callback URL: {settings.schwab_callback_url}")

    try:
        import schwab
        client = schwab.auth.client_from_manual_flow(
            api_key=settings.schwab_api_key,
            app_secret=settings.schwab_app_secret,
            callback_url=settings.schwab_callback_url,
            token_path=settings.schwab_token_path,
        )
        console.print("[green]Authentication successful! Token saved.[/green]")
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        sys.exit(1)


@cli.command()
def start():
    """Start the arena - two agents begin trading."""
    console.print(
        Panel(
            "[bold yellow]GLADIATOR OPTIONS ARENA[/bold yellow]\n"
            "Two agents enter. One survives.\n"
            f"Cycle duration: {settings.trading_cycle_days} trading days\n"
            f"Paper trading: {'YES' if settings.paper_trade else 'NO - LIVE MONEY'}",
            title="[red]Fight![/red]",
        )
    )

    if not settings.paper_trade:
        if not click.confirm(
            "WARNING: Paper trading is OFF. Real money will be used. Continue?"
        ):
            sys.exit(0)

    asyncio.run(_run_arena())


async def _run_arena():
    """Main async entry point for the arena."""
    from src.arena.arena import Arena
    from src.arena.persistence import Database
    from src.broker.schwab_client import SchwabClient
    from src.crypto.payout import CryptoPayoutEngine
    from src.data.market_data import MarketDataEngine
    from src.risk.manager import RiskManager

    # Initialize all components
    broker = SchwabClient()
    market_data = MarketDataEngine()
    risk_manager = RiskManager()
    payout_engine = CryptoPayoutEngine()
    db = Database()

    try:
        await broker.connect()
        market_data.set_schwab_client(broker)
        await market_data.start()
        await payout_engine.initialize()
        await db.initialize()

        arena = Arena(
            broker=broker,
            market_data=market_data,
            risk_manager=risk_manager,
            payout_engine=payout_engine,
        )

        await arena.initialize()
        await arena.start_cycle()

        # Keep running until interrupted
        console.print("[green]Arena is live. Press Ctrl+C to stop.[/green]")
        while True:
            await asyncio.sleep(60)
            standings = arena.get_standings()
            _print_standings(standings)

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down arena...[/yellow]")
    finally:
        await market_data.stop()
        await payout_engine.shutdown()
        await broker.disconnect()
        await db.shutdown()


@cli.command()
def status():
    """Show current arena status and standings."""
    import json
    from pathlib import Path

    state_path = Path("config/arena_state.json")
    if not state_path.exists():
        console.print("[yellow]No active arena found. Run 'gladiator start' first.[/yellow]")
        return

    state = json.loads(state_path.read_text())
    console.print(
        Panel(
            f"Cycle: {state.get('cycle_number', 0)}\n"
            f"Started: {state.get('cycle_start', 'N/A')}",
            title="Arena Status",
        )
    )

    if "history" in state:
        table = Table(title="Cycle History")
        table.add_column("Cycle", style="cyan")
        table.add_column("Winner", style="green")
        table.add_column("Winner PnL", style="green")
        table.add_column("Loser", style="red")
        table.add_column("Loser PnL", style="red")
        table.add_column("Payout", style="yellow")

        for record in state["history"][-10:]:
            table.add_row(
                str(record["cycle"]),
                record["winner"],
                f"${record['winner_pnl']:,.2f}",
                record["loser"],
                f"${record['loser_pnl']:,.2f}",
                f"${record.get('payout_amount', 0):,.2f}",
            )

        console.print(table)


@cli.command()
@click.option("--symbol", default="SPY", help="Symbol to analyze")
def scan(symbol: str):
    """Run a market scan for a symbol."""
    asyncio.run(_scan(symbol))


async def _scan(symbol: str):
    from src.broker.schwab_client import SchwabClient
    from src.data.market_data import MarketDataEngine
    from src.options.analyzer import OptionsAnalyzer

    broker = SchwabClient()
    try:
        await broker.connect()
        market_data = MarketDataEngine()
        market_data.set_schwab_client(broker)

        analysis = await market_data.get_symbol_analysis(symbol)
        console.print(Panel(str(analysis), title=f"Analysis: {symbol}"))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    finally:
        await broker.disconnect()


@cli.command()
def config():
    """Show current configuration."""
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Paper Trading", str(settings.paper_trade))
    table.add_row("Cycle Days", str(settings.trading_cycle_days))
    table.add_row("Max Position Size", f"{settings.max_position_size_pct:.0%}")
    table.add_row("Max Exposure", f"{settings.max_total_exposure_pct:.0%}")
    table.add_row("Daily Loss Limit", f"{settings.daily_loss_limit_pct:.0%}")
    table.add_row("LLM Provider", settings.llm_provider.value)
    table.add_row("Payout Coin", settings.payout_coin)
    table.add_row("Payout %", f"{settings.payout_percentage:.0%}")
    table.add_row(
        "Schwab Connected",
        "Yes" if settings.schwab_api_key else "No credentials",
    )

    console.print(table)


def _print_standings(standings: dict):
    """Print live standings to console."""
    table = Table(title=f"Cycle {standings.get('cycle', '?')} Standings")
    table.add_column("Agent", style="bold")
    table.add_column("PnL", justify="right")
    table.add_column("PnL %", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("State", style="dim")

    for agent in standings.get("agents", []):
        pnl = agent.get("total_pnl", 0)
        pnl_style = "green" if pnl >= 0 else "red"
        table.add_row(
            agent.get("name", "?"),
            f"[{pnl_style}]${pnl:,.2f}[/{pnl_style}]",
            f"[{pnl_style}]{agent.get('pnl_pct', 0):.2%}[/{pnl_style}]",
            str(agent.get("total_trades", 0)),
            f"{agent.get('win_rate', 0):.0%}",
            agent.get("state", "?"),
        )

    console.print(table)


def main():
    cli()


if __name__ == "__main__":
    main()
