# claude-trade — Lernfähiger AI Trading Bot

Ein Trading-Bot nach dem 3-Schritte-System aus *"how to actually build an AI trading bot"* (Miles Deutscher): Ein LLM (Claude) als **Gehirn**, eine Broker-Anbindung als **Hände** — und vor allem ein **Zwei-Datei-Gedächtnis**, damit der Bot aus Fehlern lernt, statt denselben Fehler zweimal zu machen.

Dazu kommt als optionale Signalebene die **Insider-/Congress-Auswertung** aus dem QuiverQuant-Video desselben Kanals — entschärft um die Punkte, die das Video verschweigt (siehe [`docs/insider-signale.md`](docs/insider-signale.md)).

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

### 4. Optional: Insider- & Congress-Signale ([`bot/insider.py`](bot/insider.py))

Ausgewertet werden **öffentliche Pflichtmeldungen** — SEC Form 4 (Directors, Officers, Großaktionäre) und STOCK-Act-Reports (US-Kongress), bezogen über [QuiverQuant](https://www.quiverquant.com). Das ist kein illegales Insider-Trading, sondern das Lesen von Dokumenten, die ohnehin jeder einsehen darf.

Das Signal ist **Cluster Buying**: nicht ein Einzelkauf, sondern mehrere *verschiedene* Insider, die im selben Fenster kaufen. Gefordert sind `INSIDER_MIN_BUYERS` verschiedene Käufer innerhalb von `INSIDER_LOOKBACK_DAYS`, mehr Käufer als Verkäufer und ein positives Netto-Volumen.

Der wichtigste Filter ist `INSIDER_MAX_FILING_LAG_DAYS`: Meldungen kommen **verzögert** (Form 4 ~2 Börsentage, Kongress-Reports bis zu 45 Tage). Ein Trade, der erst 40 Tage später gemeldet wird, ist längst eingepreist — solche Meldungen verwirft der Bot, statt sie als "Echtzeitsignal" zu behandeln.

`SIGNAL_MODE` steuert, was einen Einstieg auslöst:

| Modus | Einstieg |
|---|---|
| `ma` (Default) | nur MA-Crossover — Verhalten unverändert |
| `insider` | nur Cluster Buying |
| `combined` | Crossover **und** Insider-Bestätigung |

Ausstiege laufen in allen Modi über das bärische Crossover: Insider-*Verkäufe* sind zu verrauscht (Vesting, Steuern, 10b5-1-Pläne), um daraus ein Exit-Signal zu bauen.

```bash
python -m bot.insider AAPL MSFT NVDA   # Scanner: nur Treffer ausgeben
python -m bot.insider --all            # auch Symbole ohne Signal
SIGNAL_MODE=combined python -m bot.main --once
```

Ohne `QUIVER_API_KEY` läuft — wie beim Broker — eine Simulation mit synthetischen Meldungen.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Keys eintragen
```

In der `.env`:

- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` — Paper-Trading-Keys von [alpaca.markets](https://app.alpaca.markets). Ohne Keys läuft der Simulationsmodus.
- `ANTHROPIC_API_KEY` — Claude-Key von [platform.claude.com](https://platform.claude.com). Ohne Key läuft ein regelbasierter Fallback (kein LLM-Lernen).
- `QUIVER_API_KEY` — Token von [quiverquant.com](https://www.quiverquant.com) für die Insider-Ebene. Ohne Key laufen simulierte Meldungen.
- `SYMBOLS`, `FAST_MA`, `SLOW_MA`, `RISK_PCT`, `LOOP_INTERVAL_SECONDS` — Strategie-Parameter.
- `SIGNAL_MODE`, `INSIDER_MIN_BUYERS`, `INSIDER_LOOKBACK_DAYS`, `INSIDER_MAX_FILING_LAG_DAYS` — Insider-Ebene.

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

Für die Insider-Ebene gilt derselbe Weg zusätzlich rückwärts: erst per Scanner beobachten, ob die Cluster-Signale überhaupt etwas taugen — und zwar gemessen ab **Meldedatum**, nicht ab Handelsdatum des Insiders. Wer ab Handelsdatum backtestet, testet eine Information, die er nie hatte.

## Projektstruktur

```
bot/
  config.py     # Konfiguration aus .env
  strategy.py   # MA-Crossover-Signal
  memory.py     # Zwei-Datei-Gedächtnis (Ledger + Lessons)
  brain.py      # Claude: Pre-Trade-Check + Post-Trade-Lektionen
  broker.py     # Alpaca (Paper/Live) + Simulations-Broker
  insider.py    # Cluster Buying aus Form-4-/Kongress-Meldungen + Scanner-CLI
  main.py       # Der Loop
memory/
  ledger.jsonl  # entsteht beim ersten Trade
  lessons.md    # wächst mit jedem Verlust-Trade
docs/
  insider-signale.md  # Video-Analyse, Prompts, Realitaetscheck
tests/          # Strategie-, Memory-, Insider- und Signalmodus-Tests
```
