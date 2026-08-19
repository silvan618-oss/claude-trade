"""Kursdaten laden und lokal zwischenspeichern.

Nutzt die oeffentliche Yahoo-Chart-API ueber ``requests``. Bewusst kein
``yfinance``: dessen TLS-Impersonation bricht hinter Proxies, und wir brauchen
hier nur einen einzigen Endpunkt.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data_cache"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
BENCHMARK = "SPY"

# Wie weit Yahoo pro Aufloesung zurueckreicht. Das ist eine harte Grenze der
# Datenquelle, keine Einstellung: Intraday-Historie gibt es schlicht nicht laenger.
INTERVALS = {
    "1m": "7d",      # ~8 Handelstage
    "5m": "60d",     # ~88 Kalendertage
    "15m": "60d",    # ~88 Kalendertage
    "30m": "60d",
    "1h": "730d",    # ~3 Jahre
    "1d": "10y",     # volle Historie
}

# Liquide US-Werte quer ueber die Sektoren. WICHTIG: Das ist die Zusammensetzung
# von heute, nicht von damals. Firmen, die in der Zwischenzeit pleitegegangen
# oder uebernommen worden sind, fehlen -- klassischer Survivorship Bias. Fuer die
# Frage "wie verhalten sich Kurse NACH einem Ereignis" verzerrt das weniger als
# bei einer Renditestudie, aber es ist da und wird im Bericht ausgewiesen.
UNIVERSE = [
    # Technologie
    "AAPL", "MSFT", "NVDA", "AMD", "INTC", "CSCO", "ORCL", "CRM", "ADBE", "QCOM",
    "AVGO", "TXN", "MU", "AMAT", "NOW", "PANW", "SNOW", "PLTR", "SHOP", "UBER",
    # Kommunikation und Konsum
    "GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "AMZN", "TSLA", "HD",
    "MCD", "NKE", "SBUX", "TGT", "LOW", "BKNG", "ABNB", "F", "GM", "RIVN",
    # Basiskonsum und Gesundheit
    "PG", "KO", "PEP", "WMT", "COST", "MDLZ", "CL", "JNJ", "PFE", "MRK",
    "ABBV", "LLY", "UNH", "CVS", "AMGN", "GILD", "BIIB", "MRNA", "VRTX", "REGN",
    # Finanzen
    "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK", "SCHW", "COF",
    "V", "MA", "PYPL", "SQ", "COIN", "HOOD",
    # Industrie, Energie, Rohstoffe
    "BA", "CAT", "DE", "GE", "HON", "LMT", "RTX", "UPS", "FDX", "UNP",
    "XOM", "CVX", "COP", "SLB", "OXY", "FCX", "NEM", "DOW", "LIN", "NUE",
]


class DataError(RuntimeError):
    pass


def _cache_path(symbol: str, interval: str = "1d") -> Path:
    if interval == "1d":
        return CACHE_DIR / f"{symbol.upper()}.csv"
    return CACHE_DIR / interval / f"{symbol.upper()}.csv"


def _fetch_yahoo(symbol: str, start: dt.date, end: dt.date,
                 session: requests.Session) -> pd.DataFrame:
    params = {
        "period1": int(dt.datetime.combine(start, dt.time()).timestamp()),
        "period2": int(dt.datetime.combine(end, dt.time()).timestamp()),
        "interval": "1d",
        "events": "div,split",
    }
    resp = session.get(CHART_URL.format(symbol=symbol), params=params, timeout=30)
    if resp.status_code != 200:
        raise DataError(f"{symbol}: HTTP {resp.status_code}")

    payload = resp.json().get("chart", {})
    if payload.get("error"):
        raise DataError(f"{symbol}: {payload['error']}")
    results = payload.get("result") or []
    if not results:
        raise DataError(f"{symbol}: leere Antwort")

    result = results[0]
    stamps = result.get("timestamp") or []
    if not stamps:
        raise DataError(f"{symbol}: keine Kursdaten im Zeitraum")

    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(stamps, unit="s", utc=True).tz_convert(None).normalize(),
            "open": quote["open"],
            "high": quote["high"],
            "low": quote["low"],
            "close": quote["close"],
            "volume": quote["volume"],
        }
    )

    adj = result["indicators"].get("adjclose")
    frame["adjclose"] = adj[0]["adjclose"] if adj else frame["close"]

    # Zeilen ohne Kurs sind Handelspausen oder Luecken im Feed -- raus damit,
    # bevor sie als Nullbewegung in die Statistik wandern.
    frame = frame.dropna(subset=["open", "high", "low", "close", "adjclose"])
    return frame.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)


def load_prices(symbol: str, start: dt.date, end: dt.date, *,
                session: requests.Session | None = None,
                refresh: bool = False) -> pd.DataFrame:
    """Tageskurse fuer ein Symbol, aus dem Cache oder frisch von Yahoo."""
    symbol = symbol.upper()
    path = _cache_path(symbol)

    if path.exists() and not refresh:
        cached = pd.read_csv(path, parse_dates=["date"])
        if not cached.empty:
            covered = (cached["date"].min().date() <= start
                       and cached["date"].max().date() >= end - dt.timedelta(days=7))
            if covered:
                mask = (cached["date"] >= pd.Timestamp(start)) & (cached["date"] <= pd.Timestamp(end))
                return cached.loc[mask].reset_index(drop=True)

    owned = session is None
    session = session or make_session()
    try:
        frame = _fetch_yahoo(symbol, start, end, session)
    finally:
        if owned:
            session.close()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def load_intraday(symbol: str, interval: str, *,
                  session: requests.Session | None = None,
                  refresh: bool = False,
                  max_age_minutes: int = 30) -> pd.DataFrame:
    """Feinere Aufloesungen als Tagesdaten.

    Anders als bei Tagesdaten wird hier ueber ``range`` geladen, nicht ueber
    einen Zeitraum -- Yahoo liefert Intraday nur als gleitendes Fenster.
    Zeitstempel bleiben in UTC, damit Sommerzeit keine Luecken erzeugt.
    """
    if interval not in INTERVALS:
        raise DataError(f"Aufloesung {interval!r} nicht unterstuetzt: {sorted(INTERVALS)}")

    symbol = symbol.upper()
    path = _cache_path(symbol, interval)

    if path.exists() and not refresh:
        age = (dt.datetime.now() - dt.datetime.fromtimestamp(path.stat().st_mtime))
        if age < dt.timedelta(minutes=max_age_minutes):
            cached = pd.read_csv(path, parse_dates=["date"])
            if not cached.empty:
                return cached

    owned = session is None
    session = session or make_session()
    try:
        resp = session.get(
            CHART_URL.format(symbol=symbol),
            params={"range": INTERVALS[interval], "interval": interval},
            timeout=30,
        )
        if resp.status_code != 200:
            raise DataError(f"{symbol} {interval}: HTTP {resp.status_code}")
        payload = resp.json().get("chart", {})
        if payload.get("error"):
            raise DataError(f"{symbol} {interval}: {payload['error']}")
        results = payload.get("result") or []
        if not results:
            raise DataError(f"{symbol} {interval}: leere Antwort")

        result = results[0]
        stamps = result.get("timestamp") or []
        if not stamps:
            raise DataError(f"{symbol} {interval}: keine Balken")

        quote = result["indicators"]["quote"][0]
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(stamps, unit="s", utc=True),
                "open": quote["open"],
                "high": quote["high"],
                "low": quote["low"],
                "close": quote["close"],
                "volume": quote["volume"],
            }
        )
    finally:
        if owned:
            session.close()

    # Intraday kennt keine Dividenden-/Split-Bereinigung im Feed. Fuer Fenster
    # von Tagen bis wenigen Jahren ist das vertretbar, muss aber bewusst sein.
    frame["adjclose"] = frame["close"]
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def load_timeframes(symbol: str, intervals: tuple[str, ...] = ("15m", "1h", "1d"), *,
                    session: requests.Session | None = None,
                    refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Laedt dieselbe Aktie in mehreren Aufloesungen."""
    owned = session is None
    session = session or make_session()
    out: dict[str, pd.DataFrame] = {}
    try:
        for interval in intervals:
            if interval == "1d":
                today = dt.date.today()
                frame = load_prices(symbol, today - dt.timedelta(days=3650), today,
                                    session=session, refresh=refresh)
                frame = frame.copy()
                frame["date"] = pd.to_datetime(frame["date"], utc=True)
            else:
                frame = load_intraday(symbol, interval, session=session, refresh=refresh)
            out[interval] = frame
            time.sleep(0.12)
    finally:
        if owned:
            session.close()
    return out


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (kursstudie; research)"
    return session


def load_universe(symbols: list[str], start: dt.date, end: dt.date, *,
                  refresh: bool = False, pause: float = 0.12,
                  verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Laedt alle Symbole. Einzelne Ausfaelle beenden den Lauf nicht."""
    session = make_session()
    frames: dict[str, pd.DataFrame] = {}
    failed: list[str] = []
    try:
        for i, symbol in enumerate(symbols, 1):
            try:
                frame = load_prices(symbol, start, end, session=session, refresh=refresh)
                if len(frame) < 250:
                    failed.append(f"{symbol} (nur {len(frame)} Tage)")
                    continue
                frames[symbol.upper()] = frame
            except (DataError, requests.RequestException, ValueError, KeyError) as exc:
                failed.append(f"{symbol} ({type(exc).__name__})")
            if verbose and i % 20 == 0:
                print(f"  ... {i}/{len(symbols)} Symbole geladen")
            time.sleep(pause)
    finally:
        session.close()

    if verbose and failed:
        print(f"  uebersprungen ({len(failed)}): {', '.join(failed)}")
    if not frames:
        raise DataError("kein einziges Symbol konnte geladen werden")
    return frames
