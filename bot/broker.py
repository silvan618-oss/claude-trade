"""Broker-Anbindung — die "Haende" des Bots.

AlpacaBroker: echtes Paper-Trading-Konto via Alpaca API.
SimulatedBroker: lokaler Fallback ohne Keys (synthetische Kurse),
damit sich Loop und Memory-System risikofrei testen lassen.
"""

import random
from datetime import datetime, timedelta, timezone


class AlpacaBroker:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient

        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.data = StockHistoricalDataClient(api_key, secret_key)

    def equity(self) -> float:
        return float(self.trading.get_account().equity)

    def get_closes(self, symbol: str, lookback_days: int) -> list[float]:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        start = datetime.now(timezone.utc) - timedelta(days=lookback_days * 2)
        request = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start
        )
        bars = self.data.get_stock_bars(request)
        return [bar.close for bar in bars[symbol]]

    def buy(self, symbol: str, qty: float) -> None:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        self.trading.submit_order(
            MarketOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY
            )
        )

    def sell(self, symbol: str, qty: float) -> None:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        self.trading.submit_order(
            MarketOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY
            )
        )


class SimulatedBroker:
    """Random-Walk-Kurse, Orders werden nur bestaetigt — reines Trockentraining."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self._prices: dict[str, list[float]] = {}

    def equity(self) -> float:
        return 100_000.0

    def get_closes(self, symbol: str, lookback_days: int) -> list[float]:
        closes = self._prices.setdefault(
            symbol, self._random_walk(start=100 + self.rng.random() * 100, n=lookback_days)
        )
        # Pro Abruf einen neuen "Tag" anhaengen, damit sich Signale entwickeln
        closes.append(self._next_price(closes[-1]))
        return closes[-lookback_days:]

    def buy(self, symbol: str, qty: float) -> None:
        print(f"[sim] BUY {qty} {symbol}")

    def sell(self, symbol: str, qty: float) -> None:
        print(f"[sim] SELL {qty} {symbol}")

    def _next_price(self, price: float) -> float:
        return round(max(1.0, price * (1 + self.rng.gauss(0, 0.02))), 2)

    def _random_walk(self, start: float, n: int) -> list[float]:
        closes = [round(start, 2)]
        for _ in range(n - 1):
            closes.append(self._next_price(closes[-1]))
        return closes
