# claude-trade — Lernfähiger AI Trading Bot

Ein Trading-Bot nach dem 3-Schritte-System aus *"how to actually build an AI trading bot"* (Miles Deutscher): Ein LLM (Claude) als **Gehirn**, eine Broker-Anbindung als **Hände** — und vor allem ein **Zwei-Datei-Gedächtnis**, damit der Bot aus Fehlern lernt, statt denselben Fehler zweimal zu machen.

> ⚠️ **Immer erst mit Paper Trading (Spielgeld) starten.** Erst wenn das Memory-System nachweislich greift und der Bot profitable von schlechten Setups unterscheidet, mit kleinen Beträgen (1–3 % des Kapitals) weitermachen. Kein Anlage-Rat.

## Architektur (die 3 Schritte aus dem Video)

### 1. Plattform & Architektur

- **Gehirn:** Claude via `anthropic`-SDK ([`bot/brain.py`](bot/brain.py)) — prüft jedes Setup gegen die Lern-Datei und schreibt nach Verlusten neue Lektionen.
- **Hände:** Alpaca mit eingebauter **Paper-Trading-Umgebung** ([`bot/broker.py`](bot/broker.py)). Ohne API-Keys läuft ein simulierter Broker mit synthetischen Kursen — ideal zum risikofreien Testen des Loops.
- Alternativ lässt sich Claude auch direkt über den **Alpaca MCP Server** mit der Börse verbinden — siehe [`mcp.json.example`](mcp.json.example).

### 2. Strategie & Loop

Startstrategie ist ein simpler **Moving Average Crossover** ([`bot/strategy.py`](bot/strategy.py)): Kauf, wenn der schnelle MA den langsamen von unten kreuzt; Verkauf beim Gegenteil. Der Loop in [`bot/main.py`](bot/main.py) läuft kontinuierlich:

```
Markt prüfen → Setup entscheiden (inkl. Lektionen-Check durch Claude) → Trade ausführen → loggen
```

### 3. Das Zwei-Datei-Gedächtnis ([`bot/memory.py`](bot/memory.py))

| Datei | Zweck |
|---|---|
| `memory/ledger.jsonl` | **Ledger:** loggt jeden Trade mit allen Parametern (append-only, eine JSON-Zeile pro Eintrag) |
| `memory/lessons.md` | **Lern-Datei:** Klartext-Regeln, die sich der Bot nach fehlgeschlagenen Trades selbst schreibt |

Der Kreislauf: Vor jedem Einstieg liest der Bot `lessons.md` und lässt Claude das Setup dagegen prüfen (Veto möglich). Schließt ein Trade im Minus, formuliert Claude eine neue, konkrete Regel und hängt sie an die Lern-Datei an. Für High-Frequency-Setups mit vielen Daten lässt sich diese Schicht 1:1 gegen eine Cloud-Datenbank wie **Supabase** tauschen — die `Memory`-Schnittstelle bleibt gleich.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Keys eintragen
```

In der `.env`:

- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` — Paper-Trading-Keys von [alpaca.markets](https://app.alpaca.markets). Ohne Keys läuft der Simulationsmodus.
- `ANTHROPIC_API_KEY` — Claude-Key von [platform.claude.com](https://platform.claude.com). Ohne Key läuft ein regelbasierter Fallback (kein LLM-Lernen).
- `SYMBOLS`, `FAST_MA`, `SLOW_MA`, `RISK_PCT`, `LOOP_INTERVAL_SECONDS` — Strategie-Parameter.

## Starten

```bash
python -m bot.main --once   # eine einzelne Iteration (zum Testen)
python -m bot.main          # Endlos-Loop
```

Tests:

```bash
pytest
```

## Der empfohlene Weg zum Live-Trading

1. **Simulationsmodus** (keine Keys): Loop, Ledger und Lern-Datei beobachten.
2. **Alpaca Paper Trading**: echte Marktdaten, Spielgeld. So lange laufen lassen, bis `memory/lessons.md` sinnvolle Regeln enthält und die Statistik (`memory/ledger.jsonl`) stimmt.
3. **Live mit Kleinbeträgen** (`ALPACA_PAPER=false`): nur 1–3 % des Kapitals pro Position (`RISK_PCT`).

## Skew-Map — was Optionshändler gerade bezahlen

Zweite, unabhängige Ebene neben dem MA-Crossover, gebaut nach *"Build Your Own Skew Map"* (berttrading). Der Kurs sagt, was eine Aktie **getan** hat; die Optionskette sagt, wofür Leute gerade **zahlen**, um gegen das Nächste geschützt zu sein.

```
Skew = (OTM-Put-IV − OTM-Call-IV) ÷ ATM-IV

positiv → Puts teurer  → Absicherung ist bid
negativ → Calls teurer → jemand zahlt für Aufwärts-Exposure
```

Zwei Grundsätze, die im Code verdrahtet sind:

- **Skew ist Positionierung, keine Prognose.** Das Ergebnis ist eine Watchlist-Ebene — *wo* hinschauen. *Wann* und auf *welchem Level* kommt vom Chart, nicht von hier.
- **Das Level ist strukturell, die Veränderung ist das Signal.** MUs Skew gegen KOs Skew sagt fast nichts; MU heute gegen MU vor fünf Tagen sagt viel. Deshalb schreibt jeder Lauf einen datierten Snapshot.

### Die vier Quadranten

Skew auf die eine Achse, 1-Monats-Rendite auf die andere — jeder Name landet in genau einer Box:

| Quadrant | Bild | Aussage | Aktion |
|---|---|---|---|
| **CONTRARIAN BID** | Kurs runter, Calls bid | Tape und Optionskette widersprechen sich | Watchlist — die einzige Box, in der zwei Quellen uneins sind |
| **CHASE** | Kurs rauf, Calls bid | Alle einig | Crowded. Nicht falsch, nur spät |
| **HEDGED RALLY** | Kurs rauf, Puts bid | Dem Rally wird nicht getraut | Stops nachziehen, nicht verkaufen |
| **FEAR** | Kurs runter, Puts bid | Alle einig, andere Richtung | Liegen lassen. Kein Schnäppchen |

### Oberfläche

Ein dunkles Board für die Auswertung liegt unter [`gui/skew_terminal.html`](gui/skew_terminal.html) — einzelne Datei, kein Server, keine Installation: im Browser öffnen. Vier Quadranten-Kacheln als Filter, die Karte mit umschaltbarem Fadenkreuz (Null oder Median), Sektor-Balken samt Agreement-Prüfung, sortierbares Board, und der feste Satz zu jedem angeklickten Namen.

Über **Snapshot laden** liest sie eine Datei aus `skew_history/` ein und zeigt deine eigenen Zahlen statt der Demo. Die Datei wird nur im Browser gelesen und nirgendwohin geschickt. Die Rechenlogik ist dieselbe wie in `bot/skew.py` — Quadranten, Sektor-Reads und Satzschablone werden im Browser identisch nachgerechnet, damit Terminal und Oberfläche nie auseinanderlaufen.

### Starten

```bash
python -m bot.skew_map --demo               # synthetische Daten, keine Keys nötig
python -m bot.skew_map --card               # nur die Quadranten-Karte
python -m bot.skew_map --template sheet.csv # leeres Blatt für den Handbetrieb
python -m bot.skew_map --csv sheet.csv      # das ausgefüllte Blatt auswerten
python -m bot.skew_map --alpaca             # Optionsketten mit IV + Greeks
```

Ausgegeben werden: Board-Tabelle, ASCII-Streudiagramm mit Fadenkreuz, Sektor-Zeilen inklusive Agreement-Prüfung, pro Quadrant der feste Satz je Name — und am Ende die Namen, die eine Qualitätsprüfung nicht bestanden haben, **einzeln benannt statt still gedroppt**.

### Die drei Datenwege

| Weg | Umfang | Aufwand |
|---|---|---|
| `--csv` | 15–25 Namen, einmal die Woche von Hand aus der Broker-Kette | kostenlos; ein Nachmittag Setup, dann 15–20 Min./Woche |
| `--alpaca` | so viele Namen wie das Datenabo hergibt, täglich | braucht IV **und** Greeks je Kontrakt — gratis Feeds liefern das nicht |
| `--demo` | 22 Fantasienamen, deterministisch | keine Keys, sofort sichtbar |

Der Handbetrieb ist keine abgespeckte Demo: auf 20 Namen liefert er denselben Read. Was er nicht liefert, sind die anderen paar hundert Namen und ein Sektor-Benchmark, der breit genug ist, um sich darauf zu stützen.

### Die sieben Entscheidungen

Alle sieben stehen explizit in `SkewSettings` ([`bot/skew.py`](bot/skew.py)) — bewusst an einer Stelle, nicht als stille Defaults im Code verstreut. **Eine Zahl, die man nicht selbst gewählt hat, kann man später nicht debuggen.**

| # | Entscheidung | Feld | Default |
|---|---|---|---|
| 1 | Welche zwei Strikes? Delta-verankert, gespiegelt | `delta_target` | 0.25 |
| 2 | Welche Expiry — und ist sie fix? | `target_dte` / `min_dte` / `max_dte` / `prefer_monthly` | 45 / 25 / 75 / monatlich |
| 3 | Normalisieren oder nicht? | `normalize` (beide Spalten werden immer gerechnet) | — |
| 4 | Universum ≠ Sektor-Benchmark | `min_names_per_sector`, `min_sector_agreement` | 5, 60 % |
| 5 | Dünne Ketten: droppen oder abwerten? | `min_open_interest`, `thin_chain_weight` | 100, 0.25 |
| 6 | Sanity-Ceiling gegen kaputte Marks | `sanity_ceiling` | 0.75 |
| 7 | Was wird gespeichert, ab wann? | `history_dir` | `skew_history/` |

Überschreibbar per `.env` (`SKEW_DELTA_TARGET`, `SKEW_TARGET_DTE`, `SKEW_SANITY_CEILING`, `SKEW_MIN_AGREEMENT`, `SKEW_CENTER_MODE`, …). Die Defaults sind vertretbar, aber nicht heilig — einmal festlegen, aufschreiben, und nicht mitten in der Woche verschieben, weil eine Story, die man mag, knapp unter der Schwelle liegt.

### Die fünf Fallen — als Code, nicht als Fußnote

1. **Nie eine Index-Put/Call-Ratio zitieren.** Das ist eine Fenster-Entscheidung im Sentiment-Kostüm — rund 86 % des SPY-Put-OI liegt unter 0.10 Delta. Je nach gewähltem Delta-Band kommt 3.8 oder 2.0 heraus. Deshalb gibt es hier bewusst *keine* Put/Call-Ratio.
2. **Sektoren nie über den normalisierten Skew vergleichen.** ATM-IV schwankt zwischen Versorgern und Semis um Faktor ~3; wer durch eine kleine Zahl teilt, bekommt automatisch ein großes Ergebnis. `sector_readings()` mittelt deshalb **Vol-Punkte**, das Ranking innerhalb eines Sektors nutzt die normalisierte Spalte.
3. **Vor jedem Sektor-Read das Agreement prüfen.** Ein Durchschnitt versteckt Dinge. Liegt der Anteil der Namen auf der Mehrheitsseite unter `min_sector_agreement`, hängt die Zeile automatisch einen Caveat an und gilt nicht als Sektor-Read. „Tech ist ängstlich" ist fast immer der falsche Satz — die Spaltung *ist* die Information.
4. **Ein kaputter Mark kippt einen ganzen Namen.** Im Artikel druckte das System Duke Energy bei −1.43, richtig waren ~+0.20 — und dieser eine Name zog die Validierungs-Korrelation von 0.90 auf 0.14. `sanity_ceiling` lehnt so etwas hart ab, dünne Ketten werden abgewertet statt gelöscht, und beides steht am Ende der Ausgabe namentlich.
5. **Ein datierter Katalysator ist kein Sentiment.** Liegt ein Earnings-Termin zwischen heute und der gemessenen Expiry, wird die Zeile geflaggt: das ist Event-Prämie, korrekt bepreist, keine Positionierung.

### Der feste Satz

Jeder Name wird durch dieselbe Schablone gezwungen — nicht weil das elegant wäre, sondern weil eine feste Reihenfolge daran hindert, sich über die Namen, die man ohnehin mag, eine Geschichte zu erzählen:

```
NVDA — Trader zahlen massiv mehr fuer Puts, das ist mehr Absicherung als bei 92%
seines Sektors. Die Aktie steht +8.0 % auf Monatssicht (+6.0 % vs. SPY), bei hohem
Volumen. Quadrant: HEDGED RALLY -> Stops nachziehen bei allem, was hier schon im
Depot liegt.
```

Reihenfolge: wofür wird gezahlt → wie rankt das im **eigenen** Sektor → Kurs → Volumen → Verdikt. Der Quadrant wird ausgesprochen, weil das ein Urteil erzwingt statt eines Gefühls.

### Historie

Jeder Lauf schreibt `skew_history/JJJJ-MM-TT.json` (Settings + alle Zeilen). Ab dem zweiten Lauf füllt sich die Δ-Spalte, nach rund sechs Läufen sagt sie etwas aus. Ohne Historie bleibt sie leer — es wird nichts erfunden.

### Was diese Ebene nicht kann

Sie liefert eine Shortlist, und eine Shortlist ist kein Trade. Sie sagt, dass ein Name heute interessant ist — nicht das Level, nicht die Invalidierung, nicht ob heute der Tag ist. Genau in dieser Lücke verliert man Geld mit richtigen Ideen.

## Projektstruktur

```
bot/
  config.py     # Konfiguration aus .env
  strategy.py   # MA-Crossover-Signal
  memory.py     # Zwei-Datei-Gedächtnis (Ledger + Lessons)
  brain.py      # Claude: Pre-Trade-Check + Post-Trade-Lektionen
  broker.py     # Alpaca (Paper/Live) + Simulations-Broker
  main.py       # Der Loop
  skew.py       # Skew-Map: Formel, Quadranten, Qualitätsprüfungen, Satzschablone
  skew_data.py  # Datenwege: CSV (Handbetrieb), Alpaca-Optionsketten, Demo
  skew_map.py   # Skew-Lauf: Board, Streudiagramm, Sektoren, Snapshot-Historie
gui/
  skew_terminal.html  # interaktives Board, lädt Snapshots aus skew_history/
memory/
  ledger.jsonl  # entsteht beim ersten Trade
  lessons.md    # wächst mit jedem Verlust-Trade
skew_history/   # datierte Skew-Snapshots (entstehen beim ersten Lauf)
tests/          # Strategie-, Memory- und Skew-Tests
```
