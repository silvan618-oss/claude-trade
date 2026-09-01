"""Datenquellen fuer die Skew-Map — drei Wege, ein Format.

Alle drei liefern ChainReading-Objekte, die skew.py dann identisch verrechnet:

  CsvChainProvider        Der Weg aus dem Artikel: 15-25 Namen, einmal die
                          Woche von Hand aus der Broker-Kette abgetippt.
                          Kostet nichts und liefert auf 20 Namen denselben
                          Read wie die grosse Version.
  AlpacaChainProvider     Option-Chain-Snapshots mit IV und Greeks pro
                          Kontrakt. Das ist der Punkt, an dem es aufhoert,
                          eine Tabelle zu sein — gratis Feeds liefern nur
                          einen Preis und vielleicht eine gemischte Vola,
                          delta-verankertes Arbeiten braucht IV je Kontrakt.
  DemoChainProvider       Deterministische Fantasiedaten, damit sich Board,
                          Satzschablone und Snapshot-Logik ohne Keys und
                          ohne Marktzeiten testen lassen.
"""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta, timezone

from bot.skew import ChainReading, SkewSettings

# ---------------------------------------------------------------------------
# CSV — der Tabellen-Weg
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "ticker", "sector", "atm_iv", "put_iv", "call_iv",
    "return_1m", "spy_return_1m", "rvol",
    "put_delta", "call_delta", "dte", "expiry", "open_interest", "earnings_date",
]


class CsvChainProvider:
    """Liest das handgefuellte Blatt ein.

    IVs duerfen als 0.32 oder als 32 notiert sein — beides kommt in Broker-
    Ketten vor. Umgerechnet wird auf Dezimal, sobald ein Wert > 3 ist.
    """

    def __init__(self, path: str):
        self.path = path

    def fetch(self, tickers: list[str] | None = None) -> list[ChainReading]:
        readings: list[ChainReading] = []
        with open(self.path, newline="", encoding="utf-8") as f:
            for line_no, raw in enumerate(csv.DictReader(f), start=2):
                row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
                ticker = row.get("ticker", "").upper()
                if not ticker:
                    continue
                if tickers and ticker not in tickers:
                    continue
                if not all(row.get(c) for c in ("atm_iv", "put_iv", "call_iv", "return_1m")):
                    continue  # noch nicht ausgefuellte Vorlagenzeile
                try:
                    readings.append(ChainReading(
                        ticker=ticker,
                        sector=row.get("sector") or "Unclassified",
                        atm_iv=_as_decimal_iv(row["atm_iv"]),
                        put_iv=_as_decimal_iv(row["put_iv"]),
                        call_iv=_as_decimal_iv(row["call_iv"]),
                        return_1m=float(row["return_1m"]),
                        spy_return_1m=float(row.get("spy_return_1m") or 0.0),
                        rvol=float(row.get("rvol") or 1.0),
                        put_delta=_opt_float(row.get("put_delta")),
                        call_delta=_opt_float(row.get("call_delta")),
                        dte=_opt_int(row.get("dte")),
                        expiry=row.get("expiry", ""),
                        open_interest=_opt_int(row.get("open_interest")),
                        earnings_date=row.get("earnings_date") or None,
                    ))
                except (KeyError, ValueError) as exc:
                    raise ValueError(f"{self.path}:{line_no}: {exc}") from exc
        return readings


def write_csv_template(path: str, tickers: list[str], sectors: dict[str, str] | None = None) -> None:
    """Legt ein leeres Blatt mit den richtigen Spalten an."""
    sectors = sectors or {}
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for ticker in tickers:
            writer.writerow({"ticker": ticker, "sector": sectors.get(ticker, "")})


def _as_decimal_iv(value: str | float) -> float:
    iv = float(value)
    return iv / 100.0 if iv > 3 else iv


def _opt_float(value: str | None) -> float | None:
    return float(value) if value else None


def _opt_int(value: str | None) -> int | None:
    return int(float(value)) if value else None


# ---------------------------------------------------------------------------
# Alpaca — Option-Chain-Snapshots mit Greeks
# ---------------------------------------------------------------------------

class AlpacaChainProvider:
    """Holt pro Name genau drei IVs: ATM, Put und Call am Ziel-Delta.

    Die Expiry-Regel (Entscheidung #2) wird fuer jeden Namen ohne Ausnahme
    gleich angewendet — sonst misst man den Kalender statt die Positionierung.
    """

    def __init__(self, api_key: str, secret_key: str, settings: SkewSettings,
                 sectors: dict[str, str] | None = None):
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.historical.stock import StockHistoricalDataClient

        self.options = OptionHistoricalDataClient(api_key, secret_key)
        self.stocks = StockHistoricalDataClient(api_key, secret_key)
        self.settings = settings
        self.sectors = sectors or {}

    def fetch(self, tickers: list[str]) -> list[ChainReading]:
        spy_return = self._monthly_return("SPY")[0]
        readings: list[ChainReading] = []
        for ticker in tickers:
            try:
                readings.append(self._fetch_one(ticker, spy_return))
            except Exception as exc:  # eine kaputte Kette kippt nicht den Lauf
                print(f"[{ticker}] Kette uebersprungen: {exc}")
        return readings

    def _fetch_one(self, ticker: str, spy_return: float) -> ChainReading:
        from alpaca.data.requests import OptionChainRequest

        chain = self.options.get_option_chain(OptionChainRequest(underlying_symbol=ticker))
        if not chain:
            raise ValueError("leere Optionskette")

        contracts = [c for c in (_parse_contract(sym, snap) for sym, snap in chain.items())
                     if c is not None]
        if not contracts:
            raise ValueError("keine Kontrakte mit IV und Greeks")

        expiry = self._pick_expiry({c["expiry"] for c in contracts})
        leg = [c for c in contracts if c["expiry"] == expiry]

        return_1m, spot, rvol = self._monthly_return(ticker)
        if spot is None:
            spot = _median([c["strike"] for c in leg])

        atm_iv = _atm_iv(leg, spot)
        put = _closest_delta([c for c in leg if c["type"] == "P"], self.settings.delta_target)
        call = _closest_delta([c for c in leg if c["type"] == "C"], self.settings.delta_target)
        if put is None or call is None:
            raise ValueError("kein gespiegeltes Delta-Paar in dieser Expiry")

        return ChainReading(
            ticker=ticker,
            sector=self.sectors.get(ticker, "Unclassified"),
            atm_iv=atm_iv,
            put_iv=put["iv"],
            call_iv=call["iv"],
            return_1m=return_1m,
            spy_return_1m=spy_return,
            rvol=rvol,
            put_delta=abs(put["delta"]),
            call_delta=abs(call["delta"]),
            dte=(expiry - date.today()).days,
            expiry=expiry.isoformat(),
            open_interest=min(put["oi"], call["oi"]) if put["oi"] and call["oi"] else None,
            price=spot,
        )

    def _pick_expiry(self, expiries: set[date]) -> date:
        """Naechstliegende Expiry zum Ziel-DTE, monatliche bevorzugt."""
        today = date.today()
        candidates = [
            e for e in expiries
            if self.settings.min_dte <= (e - today).days <= self.settings.max_dte
        ]
        if not candidates:
            raise ValueError(
                f"keine Expiry in [{self.settings.min_dte}, {self.settings.max_dte}] DTE"
            )
        monthly = [e for e in candidates if _is_monthly(e)]
        if self.settings.prefer_monthly and monthly:
            candidates = monthly
        return min(candidates, key=lambda e: abs((e - today).days - self.settings.target_dte))

    def _monthly_return(self, ticker: str) -> tuple[float, float | None, float]:
        """(1M-Rendite in %, letzter Kurs, RVOL)."""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        start = datetime.now(timezone.utc) - timedelta(days=90)
        bars = self.stocks.get_stock_bars(
            StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Day, start=start)
        )
        series = list(bars[ticker])
        if len(series) < 22:
            raise ValueError(f"nur {len(series)} Tagesbars — zu wenig fuer 1M")

        closes = [b.close for b in series]
        volumes = [b.volume for b in series]
        return_1m = (closes[-1] / closes[-22] - 1) * 100
        avg_volume = sum(volumes[-21:]) / 21
        rvol = volumes[-1] / avg_volume if avg_volume else 1.0
        return round(return_1m, 2), closes[-1], round(rvol, 2)


def _parse_contract(symbol: str, snapshot) -> dict | None:
    """OCC-Symbol + Snapshot -> flaches Dict. Ohne IV oder Delta: unbrauchbar."""
    parsed = parse_occ_symbol(symbol)
    if parsed is None:
        return None
    expiry, right, strike = parsed

    iv = getattr(snapshot, "implied_volatility", None)
    greeks = getattr(snapshot, "greeks", None)
    delta = getattr(greeks, "delta", None) if greeks else None
    if iv is None or delta is None or iv <= 0:
        return None

    return {
        "expiry": expiry,
        "type": right,
        "strike": strike,
        "iv": float(iv),
        "delta": float(delta),
        "oi": int(getattr(snapshot, "open_interest", 0) or 0),
    }


def parse_occ_symbol(symbol: str) -> tuple[date, str, float] | None:
    """'AAPL251017C00230000' -> (2025-10-17, 'C', 230.0).

    Der Root ist variabel lang, die letzten 15 Zeichen sind es nicht:
    6 Ziffern Datum, 1 Zeichen Typ, 8 Ziffern Strike * 1000.
    """
    if len(symbol) < 16:
        return None
    tail = symbol[-15:]
    yy, mm, dd, right, strike = tail[0:2], tail[2:4], tail[4:6], tail[6], tail[7:]
    if right not in ("C", "P") or not (yy + mm + dd + strike).isdigit():
        return None
    try:
        expiry = date(2000 + int(yy), int(mm), int(dd))
    except ValueError:
        return None
    return expiry, right, int(strike) / 1000.0


def _is_monthly(expiry: date) -> bool:
    """Dritter Freitag im Monat — die Standard-Monatsexpiry."""
    return expiry.weekday() == 4 and 15 <= expiry.day <= 21


def _atm_iv(leg: list[dict], spot: float) -> float:
    """IV am Geld: der Strike, der dem Kurs am naechsten liegt, Call und Put gemittelt."""
    strike = min({c["strike"] for c in leg}, key=lambda s: abs(s - spot))
    at_strike = [c["iv"] for c in leg if c["strike"] == strike]
    if not at_strike:
        raise ValueError("keine ATM-IV")
    return sum(at_strike) / len(at_strike)


def _closest_delta(contracts: list[dict], target: float) -> dict | None:
    if not contracts:
        return None
    return min(contracts, key=lambda c: abs(abs(c["delta"]) - target))


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


# ---------------------------------------------------------------------------
# Demo — deterministisch, ohne Keys
# ---------------------------------------------------------------------------

DEMO_UNIVERSE: list[tuple[str, str]] = [
    ("NVDA", "Semiconductors"), ("AMD", "Semiconductors"), ("MU", "Semiconductors"),
    ("AVGO", "Semiconductors"), ("INTC", "Semiconductors"), ("TXN", "Semiconductors"),
    ("MSFT", "Software"), ("CRM", "Software"), ("NOW", "Software"),
    ("ADBE", "Software"), ("ORCL", "Software"), ("SNOW", "Software"),
    ("XOM", "Energy"), ("CVX", "Energy"), ("SLB", "Energy"),
    ("COP", "Energy"), ("OXY", "Energy"),
    ("DUK", "Utilities"), ("SO", "Utilities"), ("NEE", "Utilities"),
    ("AEP", "Utilities"), ("XEL", "Utilities"),
]


class DemoChainProvider:
    """Synthetische, aber plausible Ketten — inklusive eines kaputten Marks.

    Ein Name (DUK) bekommt bewusst einen unmoeglichen Put-Mark, damit das
    Sanity-Ceiling aus Falle #4 im Demo-Lauf auch wirklich anschlaegt statt
    nur im Test zu existieren.
    """

    def __init__(self, seed: int = 17):
        self.seed = seed

    def fetch(self, tickers: list[str] | None = None) -> list[ChainReading]:
        rng = random.Random(self.seed)
        universe = [(t, s) for t, s in DEMO_UNIVERSE if not tickers or t in tickers]
        expiry = _next_monthly(date.today(), 45)
        spy_return = 2.4

        readings: list[ChainReading] = []
        for ticker, sector in universe:
            base_iv = {"Semiconductors": 0.46, "Software": 0.34,
                       "Energy": 0.29, "Utilities": 0.18}[sector]
            atm_iv = round(base_iv * rng.uniform(0.85, 1.15), 4)
            lean = rng.gauss(0.06, 0.09)          # Put-Skew ist der Normalzustand
            put_iv = round(atm_iv * (1 + max(lean, -0.35)), 4)
            call_iv = round(atm_iv * (1 - max(lean, -0.35) * 0.55), 4)

            if ticker == "DUK":
                # Falle #4: ein einzelnes kaputtes Bein laesst einen Versorger
                # wie einen schreienden Aufwaerts-Bid aussehen (Artikel: -1.43).
                call_iv = round(atm_iv * 1.55, 4)
                put_iv = round(atm_iv * 0.15, 4)

            readings.append(ChainReading(
                ticker=ticker,
                sector=sector,
                atm_iv=atm_iv,
                put_iv=put_iv,
                call_iv=call_iv,
                return_1m=round(rng.gauss(1.5, 7.0), 2),
                spy_return_1m=spy_return,
                rvol=round(abs(rng.gauss(1.05, 0.4)) + 0.2, 2),
                put_delta=round(rng.uniform(0.22, 0.28), 3),
                call_delta=round(rng.uniform(0.22, 0.28), 3),
                dte=(expiry - date.today()).days,
                expiry=expiry.isoformat(),
                open_interest=int(abs(rng.gauss(2500, 2000))) + 40,
                earnings_date=None,
            ))
        return readings


def _next_monthly(today: date, target_dte: int) -> date:
    """Naechster dritter Freitag ab ungefaehr target_dte Tagen."""
    cursor = today + timedelta(days=target_dte)
    for _ in range(60):
        if _is_monthly(cursor):
            return cursor
        cursor += timedelta(days=1)
    return today + timedelta(days=target_dte)
