"""Skew-Map — die Rechenschicht (reine Funktionen, keine Datenquelle).

Idee (nach "Build Your Own Skew Map", berttrading): Der Optionsmarkt verraet
nicht, wohin eine Aktie laeuft, sondern wofuer Leute gerade zahlen. Ist der
OTM-Put teurer als der spiegelbildliche OTM-Call, ist Absicherung gefragt.

    Skew = (OTM-Put-IV - OTM-Call-IV) / ATM-IV

    positiv  -> Puts teurer -> Absicherung ist bid
    negativ  -> Calls teurer -> jemand zahlt fuer Aufwaerts-Exposure

Zwei Grundsaetze aus dem Artikel, die hier fest verdrahtet sind:

  1. Skew ist Positionierung, keine Prognose. Ergebnis ist eine Watchlist-
     Ebene ("wo hinschauen"), kein Entry-Signal.
  2. Das Level ist strukturell, die Veraenderung ist das Signal. Deshalb
     schreibt skew_map.py jeden Lauf als datierten Snapshot weg.

Alle sieben Entscheidungen aus Teil 4 stehen explizit in SkewSettings —
bewusst nicht als stille Defaults im Code verstreut, damit man weiss, an
welchem Rad man gedreht hat, wenn das Board seltsam aussieht.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Quadranten (Teil 2)
# ---------------------------------------------------------------------------

CONTRARIAN_BID = "CONTRARIAN BID"
CHASE = "CHASE"
HEDGED_RALLY = "HEDGED RALLY"
FEAR = "FEAR"

QUADRANT_MEANING: dict[str, str] = {
    CONTRARIAN_BID: "Kurs faellt, Calls sind trotzdem bid — Tape und Optionskette "
                    "widersprechen sich.",
    CHASE: "Kurs steigt und Calls sind bid — alle einig, der Einstieg ist nur "
           "schlechter als er war.",
    HEDGED_RALLY: "Kurs steigt, aber Puts sind bid — der Rally wird nicht getraut.",
    FEAR: "Kurs faellt und Puts sind bid — alle einig, in die andere Richtung.",
}

QUADRANT_ACTION: dict[str, str] = {
    CONTRARIAN_BID: "Watchlist — beobachten, nicht kaufen.",
    CHASE: "Crowded — nicht hinterherlaufen.",
    HEDGED_RALLY: "Stops nachziehen bei allem, was hier schon im Depot liegt.",
    FEAR: "Liegen lassen. Billig und fallend ist kein Schnaeppchen.",
}


# ---------------------------------------------------------------------------
# Die sieben Entscheidungen (Teil 4)
# ---------------------------------------------------------------------------

@dataclass
class SkewSettings:
    """Jede dieser Zahlen ist eine Entscheidung, kein Naturgesetz.

    Der Artikel ist an einem Punkt kompromisslos: eine Zahl, die man nicht
    selbst gewaehlt hat, kann man spaeter nicht debuggen. Also einmal
    festlegen, aufschreiben — und nicht mitten in der Woche verschieben.
    """

    # 1. Welche zwei Strikes definieren den Skew? Delta-verankert, gespiegelt.
    delta_target: float = 0.25
    delta_tolerance: float = 0.10  # weiter weg -> Kette taugt nicht

    # 2. Welche Expiry — und ist sie fix? Monatliche, ~1-2 Monate raus.
    target_dte: int = 45
    min_dte: int = 25
    max_dte: int = 75
    prefer_monthly: bool = True

    # 3. Normalisieren oder nicht? Beide Spalten werden immer gerechnet:
    #    normalisiert fuers Ranking *innerhalb* eines Sektors, Vol-Punkte fuer
    #    den Vergleich *zwischen* Sektoren (Falle #2).
    normalize: bool = True

    # 4. Universum vs. Sektor-Benchmark — muessen zwei verschiedene Listen sein.
    min_names_per_sector: int = 5
    min_sector_agreement: float = 0.60

    # 5. Qualitaetsschwelle fuer duenne Ketten: nicht droppen, abwerten.
    min_open_interest: int = 100
    thin_chain_weight: float = 0.25

    # 6. Sanity-Ceiling: ab hier glaubt man der eigenen Zahl nicht mehr und
    #    unterstellt einen kaputten Mark (Falle #4 — Duke bei -1.43).
    sanity_ceiling: float = 0.75

    # 7. Was wird gespeichert, ab wann? -> skew_map.py, datierte Snapshots.
    history_dir: str = "skew_history"

    # Darstellung: Fadenkreuz bei 0 oder beim Median der eigenen Liste.
    center_mode: str = "zero"  # "zero" | "median"

    # Sprachliche Abstufungen fuer den Satz aus Teil 5.
    magnitude_bands: tuple[float, float] = (0.05, 0.15)  # leicht | deutlich | massiv
    rvol_bands: tuple[float, float] = (0.70, 1.50)       # niedrig | normal | hoch

    def validate(self) -> None:
        if not 0 < self.delta_target < 0.5:
            raise ValueError("delta_target muss zwischen 0 und 0.5 liegen")
        if not self.min_dte <= self.target_dte <= self.max_dte:
            raise ValueError("target_dte muss in [min_dte, max_dte] liegen")
        if self.center_mode not in ("zero", "median"):
            raise ValueError("center_mode muss 'zero' oder 'median' sein")
        if self.sanity_ceiling <= 0:
            raise ValueError("sanity_ceiling muss positiv sein")
        if self.magnitude_bands[0] >= self.magnitude_bands[1]:
            raise ValueError("magnitude_bands muss aufsteigend sein")
        if self.rvol_bands[0] >= self.rvol_bands[1]:
            raise ValueError("rvol_bands muss aufsteigend sein")


# ---------------------------------------------------------------------------
# Eingabe: was pro Name aus der Kette kommt
# ---------------------------------------------------------------------------

@dataclass
class ChainReading:
    """Die drei IVs plus Kontext — egal ob per Hand, CSV oder API geholt.

    IVs als Dezimalzahl (0.32 == 32 %). Renditen in Prozentpunkten (6.4 == +6,4 %).
    """

    ticker: str
    sector: str
    atm_iv: float
    put_iv: float
    call_iv: float
    return_1m: float
    spy_return_1m: float = 0.0
    rvol: float = 1.0
    put_delta: float | None = None   # als Betrag, z. B. 0.24
    call_delta: float | None = None
    dte: int | None = None
    expiry: str = ""
    open_interest: int | None = None
    earnings_date: str | None = None
    price: float | None = None


# ---------------------------------------------------------------------------
# Ausgabe: eine Zeile des Boards ("The sheet", Teil 4)
# ---------------------------------------------------------------------------

@dataclass
class SkewRow:
    ticker: str
    sector: str
    skew: float                 # normalisiert
    vol_points: float           # un-normalisiert, cross-sector-tauglich
    atm_iv: float
    return_1m: float
    return_vs_spy: float
    rvol: float
    quadrant: str = ""
    action: str = ""
    sector_rank: float | None = None    # Perzentil innerhalb des eigenen Sektors
    weight: float = 1.0                 # abgewertet bei duenner Kette
    chain_ok: bool = True
    flags: list[str] = field(default_factory=list)
    dte: int | None = None
    expiry: str = ""
    earnings_date: str | None = None
    delta_change: float | None = None    # vs. letzter Snapshot

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Kernrechnung
# ---------------------------------------------------------------------------

def compute_skew(atm_iv: float, put_iv: float, call_iv: float) -> tuple[float, float]:
    """Gibt (normalisierter Skew, Vol-Punkte) zurueck.

    Vol-Punkte = rohe IV-Differenz in Volatilitaetspunkten. Die Spalte ist die,
    die einen Sektorvergleich ueberlebt — dividiert man durch eine kleine
    ATM-IV, kommt automatisch ein grosser Prozentsatz heraus (Falle #2).
    """
    if atm_iv <= 0:
        raise ValueError("atm_iv muss positiv sein")
    if put_iv <= 0 or call_iv <= 0:
        raise ValueError("put_iv und call_iv muessen positiv sein")
    diff = put_iv - call_iv
    return diff / atm_iv, diff * 100.0


def classify_quadrant(skew: float, return_1m: float,
                      skew_center: float = 0.0,
                      return_center: float = 0.0) -> str:
    """Die vier Boxen aus Teil 2, relativ zum gewaehlten Fadenkreuz."""
    puts_bid = skew >= skew_center
    up = return_1m >= return_center
    if up:
        return HEDGED_RALLY if puts_bid else CHASE
    return FEAR if puts_bid else CONTRARIAN_BID


def quality_flags(reading: ChainReading, settings: SkewSettings,
                  skew: float) -> list[str]:
    """Die Fallen #4 und #5 als harte Pruefungen, nicht als Bauchgefuehl."""
    flags: list[str] = []

    if abs(skew) > settings.sanity_ceiling:
        flags.append(
            f"sanity_ceiling: |{skew:.2f}| > {settings.sanity_ceiling:.2f} — "
            "vermutlich ein kaputter Mark, nicht handeln"
        )

    if reading.open_interest is not None and reading.open_interest < settings.min_open_interest:
        flags.append(
            f"thin_chain: OI {reading.open_interest} < {settings.min_open_interest} — "
            "Zahl als Rauschen behandeln"
        )

    for delta, label in ((reading.put_delta, "put"), (reading.call_delta, "call")):
        if delta is None:
            continue
        if abs(abs(delta) - settings.delta_target) > settings.delta_tolerance:
            flags.append(
                f"delta_mismatch: {label} bei {abs(delta):.2f} statt "
                f"{settings.delta_target:.2f} — Strikes nicht gespiegelt"
            )

    if reading.dte is not None and not (settings.min_dte <= reading.dte <= settings.max_dte):
        flags.append(
            f"expiry_drift: {reading.dte} DTE ausserhalb "
            f"[{settings.min_dte}, {settings.max_dte}] — nicht vergleichbar"
        )

    if _earnings_inside_expiry(reading):
        flags.append(
            "earnings_in_expiry: Termin liegt in der gemessenen Laufzeit — "
            "das ist Event-Praemie, keine Positionierung (Falle #5)"
        )

    return flags


def _earnings_inside_expiry(reading: ChainReading, today: "date | None" = None) -> bool:
    """Falle #5: liegt ein datierter Katalysator in der gemessenen Laufzeit?

    Nur Termine zwischen heute und der Expiry zaehlen — ein Datum vom letzten
    Quartal, das im Blatt stehen geblieben ist, ist keine Event-Praemie.
    """
    if not reading.earnings_date or not reading.expiry:
        return False

    today = today or date.today()
    try:
        earnings = date.fromisoformat(reading.earnings_date)
        expiry = date.fromisoformat(reading.expiry)
    except ValueError:
        return False
    return today <= earnings <= expiry


def build_row(reading: ChainReading, settings: SkewSettings) -> SkewRow:
    """Eine ChainReading -> eine fertige Board-Zeile (ohne Quadrant/Rank).

    Quadrant und Sektor-Rang brauchen die ganze Liste und werden in
    finalize_rows() nachgetragen.
    """
    skew, vol_points = compute_skew(reading.atm_iv, reading.put_iv, reading.call_iv)
    flags = quality_flags(reading, settings, skew)
    thin = any(f.startswith(("thin_chain", "sanity_ceiling")) for f in flags)

    return SkewRow(
        ticker=reading.ticker,
        sector=reading.sector,
        skew=round(skew, 4),
        vol_points=round(vol_points, 2),
        atm_iv=round(reading.atm_iv, 4),
        return_1m=round(reading.return_1m, 2),
        return_vs_spy=round(reading.return_1m - reading.spy_return_1m, 2),
        rvol=round(reading.rvol, 2),
        weight=settings.thin_chain_weight if thin else 1.0,
        chain_ok=not thin,
        flags=flags,
        dte=reading.dte,
        expiry=reading.expiry,
        earnings_date=reading.earnings_date,
    )


def finalize_rows(rows: list[SkewRow], settings: SkewSettings) -> list[SkewRow]:
    """Traegt Fadenkreuz, Quadrant, Aktion und Sektor-Rang nach.

    Wichtig fuer das Fadenkreuz: positiver Put-Skew ist der Normalzustand.
    Bei center_mode="zero" landet die Mehrheit deshalb in der oberen Haelfte —
    das ist kein Bug, sondern genau der Grund, warum die beiden negativen
    Boxen die interessanten sind. "median" zentriert stattdessen auf die
    eigene Liste. Beides vertretbar, nur eben unterschiedliche Aussagen.
    """
    if not rows:
        return rows

    if settings.center_mode == "median":
        skew_center = statistics.median(r.skew for r in rows)
        return_center = statistics.median(r.return_1m for r in rows)
    else:
        skew_center = 0.0
        return_center = 0.0

    for row in rows:
        row.quadrant = classify_quadrant(row.skew, row.return_1m,
                                         skew_center, return_center)
        row.action = QUADRANT_ACTION[row.quadrant]

    for sector in {r.sector for r in rows}:
        peers = [r for r in rows if r.sector == sector]
        for row in peers:
            row.sector_rank = _percentile(row.skew, [p.skew for p in peers])

    return rows


def _percentile(value: float, population: list[float]) -> float:
    """Anteil der Peers, die unter diesem Wert liegen (0..1)."""
    if len(population) <= 1:
        return 0.5
    below = sum(1 for v in population if v < value)
    ties = sum(1 for v in population if v == value)
    return round((below + 0.5 * ties) / len(population), 3)


# ---------------------------------------------------------------------------
# Sektor-Lesart (Falle #2 und #3)
# ---------------------------------------------------------------------------

@dataclass
class SectorReading:
    sector: str
    names: int
    avg_vol_points: float       # cross-sector-tauglich, un-normalisiert
    avg_skew: float             # normalisiert, nur innerhalb des Sektors
    agreement: float            # Anteil der Namen auf der Mehrheitsseite
    trustworthy: bool
    caveat: str = ""

    def describe(self) -> str:
        side = "Puts" if self.avg_vol_points >= 0 else "Calls"
        text = (
            f"{self.sector}: {self.avg_vol_points:+.2f} Vol-Punkte ({side} teurer), "
            f"{self.names} Namen, Agreement {self.agreement:.0%}"
        )
        return f"{text} — {self.caveat}" if self.caveat else text


def sector_readings(rows: list[SkewRow], settings: SkewSettings) -> list[SectorReading]:
    """Sektor-Durchschnitte plus die Agreement-Pruefung aus Falle #3.

    Ein Durchschnitt versteckt Dinge. Bevor "Energie wird abgesichert" gesagt
    wird, muss geprueft sein, wie viele Namen des Sektors ueberhaupt in diese
    Richtung lehnen — sonst zieht ein lauter Ausreisser den Schnitt.

    Gemittelt wird ueber Vol-Punkte, nicht ueber den normalisierten Skew:
    ATM-IV schwankt zwischen Versorgern und Semis um Faktor ~3, und wer durch
    eine kleine Zahl teilt, bekommt automatisch ein grosses Ergebnis. Genau
    deshalb stehen Utilities, Real Estate und Staples in naiven Fear-Rankings
    jeden Tag oben.
    """
    readings: list[SectorReading] = []

    for sector in sorted({r.sector for r in rows}):
        peers = [r for r in rows if r.sector == sector and r.chain_ok]
        if not peers:
            continue

        total_weight = sum(p.weight for p in peers)
        avg_vp = sum(p.vol_points * p.weight for p in peers) / total_weight
        avg_skew = sum(p.skew * p.weight for p in peers) / total_weight

        majority_side = 1 if avg_vp >= 0 else -1
        agreeing = sum(1 for p in peers
                       if (1 if p.vol_points >= 0 else -1) == majority_side)
        agreement = agreeing / len(peers)

        caveat = ""
        trustworthy = True
        if len(peers) < settings.min_names_per_sector:
            trustworthy = False
            caveat = (f"nur {len(peers)} Namen (Minimum "
                      f"{settings.min_names_per_sector}) — kein Sektor-Read")
        elif agreement < settings.min_sector_agreement:
            trustworthy = False
            caveat = (f"Agreement unter {settings.min_sector_agreement:.0%} — "
                      "der Sektor lehnt nicht gemeinsam, das ist die Information")

        readings.append(SectorReading(
            sector=sector,
            names=len(peers),
            avg_vol_points=round(avg_vp, 2),
            avg_skew=round(avg_skew, 4),
            agreement=round(agreement, 3),
            trustworthy=trustworthy,
            caveat=caveat,
        ))

    readings.sort(key=lambda r: r.avg_vol_points, reverse=True)
    return readings


# ---------------------------------------------------------------------------
# Der feste Satz (Teil 5)
# ---------------------------------------------------------------------------

def describe_row(row: SkewRow, settings: SkewSettings) -> str:
    """Immer dieselbe Reihenfolge, immer dieselben Worte.

    Nicht weil das elegant waere, sondern weil eine feste Schablone daran
    hindert, sich ueber die Namen, die man ohnehin mag, eine Geschichte zu
    erzaehlen: wofuer wird gezahlt -> wie rankt das im eigenen Sektor ->
    Kurs -> Volumen -> Verdikt.
    """
    low, high = settings.magnitude_bands
    strength = abs(row.skew)
    magnitude = "leicht" if strength < low else ("deutlich" if strength < high else "massiv")
    side = "Puts" if row.skew >= 0 else "Calls"
    kind = "Absicherung" if row.skew >= 0 else "Aufwaerts-Exposure"

    rank_part = ""
    if row.sector_rank is not None:
        # Der Rang ist ein Perzentil des Put-Skews. Bei einem Call-Bid muss er
        # gespiegelt werden, sonst liest sich "am staerksten Calls bid" als
        # "8 % des Sektors" statt als "92 %".
        share = row.sector_rank if row.skew >= 0 else 1 - row.sector_rank
        rank_part = f", das ist mehr {kind} als bei {share:.0%} seines Sektors"

    quiet, loud = settings.rvol_bands
    volume = "niedrigem" if row.rvol < quiet else ("hohem" if row.rvol >= loud else "normalem")

    sentence = (
        f"{row.ticker} — Trader zahlen {magnitude} mehr fuer {side}{rank_part}. "
        f"Die Aktie steht {row.return_1m:+.1f} % auf Monatssicht "
        f"({row.return_vs_spy:+.1f} % vs. SPY), bei {volume} Volumen. "
        f"Quadrant: {row.quadrant} -> {row.action}"
    )

    if row.flags:
        sentence += "  [" + " | ".join(f.split(":")[0] for f in row.flags) + "]"
    return sentence


def quadrant_card() -> str:
    """Die vier Verdikte einmal aufgeschrieben, damit man sie nicht um 16 Uhr
    an einem roten Tag neu verhandelt."""
    lines = ["Die vier Quadranten:"]
    for q in (CONTRARIAN_BID, CHASE, HEDGED_RALLY, FEAR):
        lines.append(f"  {q:<15} {QUADRANT_MEANING[q]}")
        lines.append(f"  {'':<15} -> {QUADRANT_ACTION[q]}")
    return "\n".join(lines)
