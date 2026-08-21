"""Insider- und Congress-Signale (die Ebene aus dem QuiverQuant-Video).

Wichtig zur Einordnung: Hier wird **kein illegales Insider-Trading**
betrieben. Ausgewertet werden ausschliesslich Pflichtveroeffentlichungen:

  * SEC Form 4 — Kaeufe/Verkaeufe von Directors, Officers und Grossaktionaeren
  * STOCK Act Periodic Transaction Reports — Trades von US-Kongressmitgliedern

Beide werden mit **Verzoegerung** publiziert (Form 4 in der Regel 2 Boersentage,
Kongress-Reports bis zu 45 Tage). Der Bot kann also nur auf die *Meldung*
reagieren, nie auf den Trade selbst. Genau deshalb hat dieses Modul einen
harten Filter auf den Filing-Lag: was zu lange her ist, wird verworfen,
statt so zu tun, als waere es ein Echtzeitsignal.

Die eigentliche Kante im Video ist **Cluster Buying**: nicht ein einzelner
Kauf, sondern mehrere unabhaengige Insider, die im selben Zeitfenster in
derselben Aktie kaufen.

Datenquellen:
  * QuiverQuantSource — REST-API von QuiverQuant (Token noetig)
  * SimulatedInsiderSource — deterministischer Fallback ohne Keys, damit
    sich der Loop wie beim SimulatedBroker trocken testen laesst

CLI (Scanner statt Dauer-Loop, siehe README):
    python -m bot.insider AAPL MSFT NVDA
"""

import json
import random
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

# Rollen, die als "informierte" Kaeufer zaehlen. Ein CFO-Kauf wiegt schwerer
# als der eines Grossaktionaers, der aus ganz anderen Gruenden aufstockt.
ROLE_WEIGHTS = {
    "ceo": 1.5,
    "chief executive": 1.5,
    "cfo": 1.5,
    "chief financial": 1.5,
    "president": 1.2,
    "coo": 1.2,
    "chief": 1.2,
    "officer": 1.1,
    "director": 1.0,
    "congress": 1.0,
    "senator": 1.0,
    "representative": 1.0,
    "10%": 0.6,  # Grossaktionaer — oft mechanische Umschichtung
}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except ValueError:
                continue
    return None


def _to_float(value) -> float:
    if value in (None, ""):
        return 0.0
    text = str(value).replace("$", "").replace(",", "").strip()
    # QuiverQuant liefert Kongress-Volumina teils als Spanne ("$1001 - $15000")
    if "-" in text[1:]:
        parts = [p for p in text.replace("–", "-").split("-") if p.strip()]
        try:
            nums = [float(p) for p in parts]
            return sum(nums) / len(nums)
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


@dataclass
class InsiderTx:
    """Eine gemeldete Transaktion — Form 4 oder Kongress-Report."""

    symbol: str
    person: str
    title: str = ""
    source: str = "insider"  # "insider" | "congress"
    action: str = "buy"  # "buy" | "sell"
    shares: float = 0.0
    value: float = 0.0
    traded_on: date | None = None
    filed_on: date | None = None

    @property
    def filing_lag_days(self) -> int | None:
        """Tage zwischen Trade und Veroeffentlichung — das ist der Nachteil."""
        if self.traded_on is None or self.filed_on is None:
            return None
        return (self.filed_on - self.traded_on).days

    def weight(self) -> float:
        haystack = f"{self.title} {self.source}".lower()
        for needle, weight in ROLE_WEIGHTS.items():
            if needle in haystack:
                return weight
        return 1.0


@dataclass
class InsiderSignal:
    symbol: str
    action: str  # "buy" | "hold"
    buyers: int = 0
    sellers: int = 0
    net_value: float = 0.0
    score: float = 0.0
    max_filing_lag_days: int | None = None
    people: list[str] = field(default_factory=list)
    reason: str = ""

    def describe(self) -> str:
        if self.action != "buy":
            return f"insider HOLD ({self.reason})"
        lag = "?" if self.max_filing_lag_days is None else self.max_filing_lag_days
        return (
            f"insider BUY — {self.buyers} Kaeufer / {self.sellers} Verkaeufer, "
            f"netto ${self.net_value:,.0f}, Score {self.score:.2f}, "
            f"Meldeverzug max. {lag}d: {', '.join(self.people)}"
        )


def cluster_buy_signal(
    transactions: list[InsiderTx],
    *,
    min_buyers: int = 3,
    lookback_days: int = 30,
    max_filing_lag_days: int = 21,
    today: date | None = None,
) -> InsiderSignal:
    """Cluster-Buying-Signal aus gemeldeten Transaktionen.

    BUY, wenn im Fenster `lookback_days` mindestens `min_buyers`
    *verschiedene* Personen gekauft haben, die Kaeufer die Verkaeufer
    ueberwiegen und das Netto-Volumen positiv ist. Meldungen, deren
    Veroeffentlichung laenger als `max_filing_lag_days` nach dem Trade
    erfolgte, werden verworfen — bei denen ist die Information bereits im Kurs.
    """
    today = today or _today()
    symbol = transactions[0].symbol.upper() if transactions else "?"
    cutoff = today - timedelta(days=lookback_days)

    fresh: list[InsiderTx] = []
    stale = 0
    for tx in transactions:
        if tx.traded_on is None or tx.traded_on < cutoff:
            continue
        lag = tx.filing_lag_days
        if lag is not None and lag > max_filing_lag_days:
            stale += 1
            continue
        fresh.append(tx)

    if not fresh:
        reason = (
            f"keine verwertbaren Meldungen in {lookback_days}d"
            + (f" ({stale} zu spaet gemeldet)" if stale else "")
        )
        return InsiderSignal(symbol=symbol, action="hold", reason=reason)

    buyers = {tx.person for tx in fresh if tx.action == "buy"}
    sellers = {tx.person for tx in fresh if tx.action == "sell"}
    # Wer im Fenster kauft *und* verkauft, ist kein Ueberzeugungstaeter.
    buyers -= sellers

    bought = sum(tx.value for tx in fresh if tx.action == "buy" and tx.person in buyers)
    sold = sum(tx.value for tx in fresh if tx.action == "sell")
    net_value = round(bought - sold, 2)
    score = round(
        sum(tx.weight() for tx in fresh if tx.action == "buy" and tx.person in buyers), 2
    )
    lags = [tx.filing_lag_days for tx in fresh if tx.filing_lag_days is not None]
    people = sorted(
        {f"{tx.person} ({tx.title})" if tx.title else tx.person
         for tx in fresh if tx.action == "buy" and tx.person in buyers}
    )

    signal = InsiderSignal(
        symbol=symbol,
        action="hold",
        buyers=len(buyers),
        sellers=len(sellers),
        net_value=net_value,
        score=score,
        max_filing_lag_days=max(lags) if lags else None,
        people=people,
    )

    if len(buyers) < min_buyers:
        signal.reason = f"nur {len(buyers)} Kaeufer, {min_buyers} noetig"
    elif len(sellers) >= len(buyers):
        signal.reason = f"{len(sellers)} Verkaeufer gegen {len(buyers)} Kaeufer"
    elif net_value <= 0:
        signal.reason = f"Netto-Volumen negativ (${net_value:,.0f})"
    else:
        signal.action = "buy"
        signal.reason = f"Cluster Buying: {len(buyers)} Insider, netto ${net_value:,.0f}"

    return signal


# ---------- Datenquellen ----------


class QuiverQuantSource:
    """REST-Client fuer QuiverQuant (Form 4 + Kongress-Trades).

    Die Endpunkt-Pfade und Feldnamen stehen bewusst als Konstanten hier oben:
    QuiverQuant aendert sie gelegentlich, und das Parsing unten ist absichtlich
    tolerant (mehrere moegliche Feldnamen pro Wert). Bei einem 404 zuerst die
    aktuelle API-Doku im QuiverQuant-Account gegenpruefen.
    """

    BASE_URL = "https://api.quiverquant.com/beta"
    INSIDER_PATH = "/historical/insiders/{symbol}"
    CONGRESS_PATH = "/historical/congresstrading/{symbol}"

    def __init__(self, token: str, timeout: int = 20):
        self.token = token
        self.timeout = timeout

    def _get(self, path: str) -> list[dict]:
        request = urllib.request.Request(
            self.BASE_URL + path,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, list) else payload.get("data", [])

    @staticmethod
    def _pick(row: dict, *names, default=""):
        for name in names:
            if row.get(name) not in (None, ""):
                return row[name]
        return default

    def transactions(self, symbol: str) -> list[InsiderTx]:
        """Form-4- und Kongress-Meldungen zu einem Symbol, zusammengefuehrt."""
        out: list[InsiderTx] = []
        for path, source in (
            (self.INSIDER_PATH, "insider"),
            (self.CONGRESS_PATH, "congress"),
        ):
            try:
                rows = self._get(path.format(symbol=symbol.upper()))
            except (urllib.error.URLError, ValueError) as exc:
                print(f"[{symbol}] QuiverQuant {source} nicht abrufbar: {exc}")
                continue
            out.extend(self._to_tx(row, symbol, source) for row in rows)
        return [tx for tx in out if tx.action in ("buy", "sell")]

    def _to_tx(self, row: dict, symbol: str, source: str) -> InsiderTx:
        raw_action = str(
            self._pick(row, "Transaction", "TransactionCode", "Type", "Trade_Type")
        ).lower()
        if raw_action.startswith(("p", "buy", "purchase")):
            action = "buy"
        elif raw_action.startswith(("s", "sell", "sale")):
            action = "sell"
        else:
            action = raw_action or "unknown"

        traded = _parse_date(
            self._pick(row, "Date", "TransactionDate", "TransactionDate")
        )
        filed = _parse_date(
            self._pick(row, "FileDate", "ReportDate", "Filed", "fileDate")
        ) or traded
        shares = _to_float(self._pick(row, "Shares", "SharesTraded", "Amount"))
        value = _to_float(self._pick(row, "Value", "Trade_Size_USD", "Range", "Amount"))
        if not value and shares:
            value = shares * _to_float(self._pick(row, "PricePerShare", "Price"))

        return InsiderTx(
            symbol=symbol.upper(),
            person=str(self._pick(row, "Name", "Representative", "Senator", default="?")),
            title=str(self._pick(row, "Title", "Position", "Office", "House")),
            source=source,
            action=action,
            shares=shares,
            value=round(value, 2),
            traded_on=traded,
            filed_on=filed,
        )


class SimulatedInsiderSource:
    """Synthetische Meldungen ohne API-Key — zum Trockentesten des Loops.

    Pro Symbol deterministisch (Seed aus dem Tickernamen), damit dasselbe
    Symbol im Loop nicht bei jeder Iteration ein anderes Bild liefert.
    Etwa jedes dritte Symbol erzeugt ein Cluster, sonst saehe man den
    Buy-Pfad nie.
    """

    TITLES = ["CEO", "CFO", "Director", "COO", "10% Owner", "Representative"]

    def __init__(self, seed: int = 7):
        self.seed = seed

    def transactions(self, symbol: str) -> list[InsiderTx]:
        rng = random.Random(f"{self.seed}:{symbol.upper()}")
        today = _today()
        out: list[InsiderTx] = []
        for i in range(rng.randint(1, 6)):
            traded = today - timedelta(days=rng.randint(0, 40))
            out.append(
                InsiderTx(
                    symbol=symbol.upper(),
                    person=f"Sim Insider {i + 1}",
                    title=rng.choice(self.TITLES),
                    source="insider",
                    action=rng.choice(["buy", "buy", "buy", "sell"]),
                    shares=float(rng.randint(500, 20_000)),
                    value=float(rng.randint(50_000, 2_000_000)),
                    traded_on=traded,
                    filed_on=traded + timedelta(days=rng.randint(1, 25)),
                )
            )
        return out


def build_insider_source(config):
    """Waehlt die Datenquelle analog zum Broker: echte API oder Simulation."""
    if getattr(config, "quiver_api_key", ""):
        return QuiverQuantSource(config.quiver_api_key)
    return SimulatedInsiderSource()


def signal_for(source, symbol: str, config) -> InsiderSignal:
    """Holt die Meldungen zu einem Symbol und wertet sie als Cluster-Signal."""
    return cluster_buy_signal(
        source.transactions(symbol),
        min_buyers=config.insider_min_buyers,
        lookback_days=config.insider_lookback_days,
        max_filing_lag_days=config.insider_max_filing_lag_days,
    )


def main() -> None:
    """Scanner-Modus: einmal ueber eine Symbolliste, Treffer ausgeben."""
    import argparse

    from bot.config import Config

    parser = argparse.ArgumentParser(description="Insider-/Congress-Cluster-Scanner")
    parser.add_argument("symbols", nargs="*", help="Default: SYMBOLS aus der .env")
    parser.add_argument("--all", action="store_true",
                        help="auch Symbole ohne Signal ausgeben")
    args = parser.parse_args()

    config = Config()
    source = build_insider_source(config)
    symbols = [s.upper() for s in args.symbols] or config.symbols
    print(f"Quelle: {'QuiverQuant' if config.has_quiver else 'Simulation (kein Key)'} | "
          f"min. {config.insider_min_buyers} Kaeufer in "
          f"{config.insider_lookback_days}d, Meldeverzug max. "
          f"{config.insider_max_filing_lag_days}d")

    for symbol in symbols:
        signal = signal_for(source, symbol, config)
        if signal.action == "buy" or args.all:
            print(f"[{symbol}] {signal.describe()}")


if __name__ == "__main__":
    main()
