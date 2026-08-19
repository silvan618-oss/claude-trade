"""Fundamentaldaten von SEC EDGAR -- die Zahlen, nach denen Menschen Aktien auswaehlen.

Alle bisherigen Studien haben ausschliesslich Kurse benutzt. Das ist eine echte
Luecke, denn niemand waehlt Aktien nach Kerzenformen aus. Man schaut auf Umsatz,
Gewinn, Marge, Eigenkapitalrendite -- also darauf, wie das Unternehmen
aufgestellt ist.

EDGAR liefert zu jeder Kennzahl das Feld ``filed``: das Datum, an dem sie
eingereicht und damit oeffentlich wurde. Das ist entscheidend. Der Quartals-
gewinn zum 31.03. ist nicht am 31.03. bekannt, sondern erst Wochen spaeter mit
der Einreichung. Wer das Quartalsende statt des Einreichungsdatums benutzt,
handelt mit Wissen aus der Zukunft und bekommt Traumergebnisse, die live nicht
existieren.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

CACHE = Path(__file__).resolve().parent.parent / "data_cache" / "edgar"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Welche Bilanzposten wir brauchen. EDGAR fuehrt teils mehrere Bezeichnungen
# fuer dieselbe Groesse -- die Liste wird der Reihe nach durchprobiert.
CONCEPTS = {
    "umsatz": ["RevenueFromContractWithCustomerExcludingAssessedTax",
               "Revenues", "SalesRevenueNet"],
    "gewinn": ["NetIncomeLoss"],
    "eigenkapital": ["StockholdersEquity"],
    "bilanzsumme": ["Assets"],
    "op_gewinn": ["OperatingIncomeLoss"],
}

# Stromgroessen (Umsatz, Gewinn) beziehen sich auf einen ZEITRAUM, Bestandsgroessen
# (Eigenkapital, Bilanzsumme) auf einen STICHTAG. EDGAR liefert bei Stromgroessen
# sowohl Quartals- als auch Jahreswerte in derselben Liste. Wer beides mischt,
# zaehlt beim Aufsummieren das Jahr doppelt -- deshalb werden bei Stromgroessen
# nur Perioden von rund einem Quartal behalten.
STROMGROESSEN = {"umsatz", "gewinn", "op_gewinn"}
QUARTAL_TAGE = (80, 100)


def make_session() -> requests.Session:
    session = requests.Session()
    # Die SEC verlangt eine identifizierende Kennung im User-Agent.
    session.headers["User-Agent"] = "claude-trade research (silvan618@gmail.com)"
    return session


def ticker_to_cik(session: requests.Session | None = None) -> dict[str, str]:
    """Zuordnung Boersenkuerzel -> SEC-Kennnummer."""
    path = CACHE / "tickers.json"
    if path.exists():
        return json.loads(path.read_text())

    owned = session is None
    session = session or make_session()
    try:
        resp = session.get(TICKER_URL, timeout=30)
        resp.raise_for_status()
        mapping = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                   for v in resp.json().values()}
    finally:
        if owned:
            session.close()

    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping))
    return mapping


def load_facts(symbol: str, cik: str, session: requests.Session, *,
               pause: float = 0.15) -> dict | None:
    """Alle Bilanzdaten einer Firma, lokal zwischengespeichert."""
    path = CACHE / f"{symbol}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            path.unlink()

    try:
        resp = session.get(FACTS_URL.format(cik=cik), timeout=60)
        if resp.status_code != 200:
            return None
        facts = resp.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None
    finally:
        time.sleep(pause)

    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(facts))
    return facts


def _extract(facts: dict, names: list[str], *, quarterly_only: bool = False) -> pd.DataFrame:
    """Holt eine Kennzahl als Zeitreihe, mit Einreichungsdatum.

    Firmen benutzen fuer dieselbe Groesse unterschiedliche XBRL-Bezeichner, und
    manche fuehren mehrere parallel -- NVDA etwa hat ``Revenues`` mit 276 Werten
    und ``RevenueFromContractWithCustomer...`` mit nur 28. Deshalb werden alle
    Kandidaten ausgewertet und der mit den meisten brauchbaren Werten gewaehlt,
    statt einfach den ersten zu nehmen.
    """
    gaap = facts.get("facts", {}).get("us-gaap", {})
    best = pd.DataFrame(columns=["end", "filed", "val"])

    for name in names:
        if name not in gaap:
            continue
        values = gaap[name].get("units", {}).get("USD")
        if not values:
            continue
        frame = pd.DataFrame(values)
        if not {"end", "filed", "val"} <= set(frame.columns):
            continue
        if "form" in frame.columns:
            frame = frame[frame["form"].isin(["10-K", "10-Q"])]
        if frame.empty:
            continue

        columns = ["end", "filed", "val"] + (["start"] if "start" in frame.columns else [])
        out = frame[columns].copy()
        out["end"] = pd.to_datetime(out["end"])
        out["filed"] = pd.to_datetime(out["filed"])

        if quarterly_only:
            if "start" not in out.columns:
                continue  # ohne Periodenanfang laesst sich die Laenge nicht pruefen
            out["start"] = pd.to_datetime(out["start"])
            dauer = (out["end"] - out["start"]).dt.days
            out = out[dauer.between(*QUARTAL_TAGE)]
            if out.empty:
                continue
            out = out.drop(columns=["start"])

        # Bei mehreren Einreichungen derselben Periode gilt die erste --
        # spaetere Korrekturen waren damals noch nicht bekannt.
        out = out.sort_values("filed").drop_duplicates(subset="end", keep="first")
        out = out.sort_values("end").reset_index(drop=True)
        if len(out) > len(best):
            best = out

    return best


def build_fundamentals(symbols: list[str], *, verbose: bool = True) -> pd.DataFrame:
    """Kennzahlen je Firma und Quartal, jeweils mit dem Datum ihrer Veroeffentlichung."""
    mapping = ticker_to_cik()
    session = make_session()
    parts = []
    missing = []
    try:
        for i, symbol in enumerate(symbols, 1):
            cik = mapping.get(symbol.upper())
            if not cik:
                missing.append(symbol)
                continue
            facts = load_facts(symbol.upper(), cik, session)
            if not facts:
                missing.append(symbol)
                continue

            series = {key: _extract(facts, names, quarterly_only=key in STROMGROESSEN)
                      for key, names in CONCEPTS.items()}
            if series["gewinn"].empty:
                missing.append(symbol)
                continue

            merged = series["gewinn"].rename(columns={"val": "gewinn"})
            for key in ("umsatz", "eigenkapital", "bilanzsumme", "op_gewinn"):
                other = series[key]
                if other.empty:
                    merged[key] = np.nan
                    continue
                merged = merged.merge(
                    other[["end", "val"]].rename(columns={"val": key}),
                    on="end", how="left")

            merged["symbol"] = symbol.upper()
            parts.append(merged)
            if verbose and i % 25 == 0:
                print(f"  ... {i}/{len(symbols)} Firmen")
    finally:
        session.close()

    if verbose and missing:
        print(f"  ohne Daten ({len(missing)}): {', '.join(missing[:12])}"
              f"{' ...' if len(missing) > 12 else ''}")
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values(["symbol", "end"]).reset_index(drop=True)


def add_ratios(fundamentals: pd.DataFrame) -> pd.DataFrame:
    """Die Kennzahlen, nach denen tatsaechlich ausgewaehlt wird."""
    out = fundamentals.copy()
    grouped = out.groupby("symbol")

    # Rollierende Vier-Quartals-Summen -- Quartalszahlen allein schwanken saisonal.
    out["gewinn_12m"] = grouped["gewinn"].transform(lambda s: s.rolling(4).sum())
    out["umsatz_12m"] = grouped["umsatz"].transform(lambda s: s.rolling(4).sum())

    out["eigenkapitalrendite"] = out["gewinn_12m"] / out["eigenkapital"].replace(0, np.nan)
    out["kapitalrendite"] = out["gewinn_12m"] / out["bilanzsumme"].replace(0, np.nan)
    out["marge"] = out["gewinn_12m"] / out["umsatz_12m"].replace(0, np.nan)

    out["umsatzwachstum"] = grouped["umsatz_12m"].transform(lambda s: s / s.shift(4) - 1.0)
    out["gewinnwachstum"] = grouped["gewinn_12m"].transform(
        lambda s: (s - s.shift(4)) / s.shift(4).abs())

    # Verschuldung: je niedriger, desto solider aufgestellt.
    out["eigenkapitalquote"] = out["eigenkapital"] / out["bilanzsumme"].replace(0, np.nan)

    for column in ("eigenkapitalrendite", "kapitalrendite", "marge",
                   "umsatzwachstum", "gewinnwachstum", "eigenkapitalquote"):
        out[column] = out[column].replace([np.inf, -np.inf], np.nan)
    return out


KENNZAHLEN = ["eigenkapitalrendite", "kapitalrendite", "marge",
              "umsatzwachstum", "gewinnwachstum", "eigenkapitalquote"]


def align_to_prices(fundamentals: pd.DataFrame, prepared: dict[str, pd.DataFrame],
                    horizon_days: int = 63) -> pd.DataFrame:
    """Verbindet Kennzahlen mit Kursen -- ueber das EINREICHUNGSdatum.

    Zu jedem Handelstag wird der zuletzt *veroeffentlichte* Abschluss gesucht.
    Damit ist ausgeschlossen, dass Zahlen benutzt werden, die es zu dem
    Zeitpunkt noch gar nicht gab.
    """
    parts = []
    for symbol, frame in prepared.items():
        facts = fundamentals[fundamentals["symbol"] == symbol]
        if facts.empty:
            continue

        prices = frame[["date", "close"]].copy().reset_index(drop=True)
        prices["fwd"] = prices["close"].shift(-horizon_days) / prices["close"] - 1.0
        prices = prices.dropna(subset=["fwd"]).sort_values("date")

        # merge_asof verlangt identische Zeitaufloesung auf beiden Seiten;
        # Kurse kommen aus CSV (Sekunden), EDGAR-Daten in Mikrosekunden.
        prices["date"] = prices["date"].astype("datetime64[ns]")
        facts = facts.copy()
        facts["filed"] = facts["filed"].astype("datetime64[ns]")
        facts = facts.sort_values("filed")
        merged = pd.merge_asof(prices, facts[["filed"] + KENNZAHLEN],
                               left_on="date", right_on="filed", direction="backward")
        merged["symbol"] = symbol
        # Zahlen, die aelter als ein Jahr sind, gelten als veraltet.
        merged = merged[(merged["date"] - merged["filed"]).dt.days <= 400]
        parts.append(merged)

    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).dropna(subset=["fwd"])
