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

## Ereignis-Studie: rechnet nach, ob die Idee überhaupt trägt

Bevor man einen Bot mit Geld laufen lässt, sollte man wissen, ob das Signal, auf das
er wettet, überhaupt existiert. Genau dafür ist [`research/`](research/README.md) da.

Die Studie misst an 2.767 echten Ereignissen über zehn Jahre, was nach
nachrichtengetriebenen Kurssprüngen passiert. Kurzergebnis: Über 95 % der Bewegung
liegt im Übernacht-Gap und ist damit vorbei, bevor man handeln kann. Danach ist kein
belastbarer Drift messbar. Mit Hebel 50 werden 69 % der Positionen ausgeknockt —
darunter fast die Hälfte derer, deren Richtung am Ende richtig war.

```bash
python -m research.cli      # Ereignisse: was passiert nach Nachrichten
python -m research.tf_cli   # Multi-Timeframe: bringt Einigkeit der Zeitebenen etwas
python -m research.ml_cli   # Mustererkennung: lernt ein Modell die Zukunft?
```

Der wichtigere Teil ist aber nicht das Ergebnis, sondern das Werkzeug: eine
Zufallskontrollgruppe, geclusterte t-Werte und eine Pfadsimulation für Hebelprodukte.
Damit lässt sich **jede** neue Idee prüfen, statt sie zu glauben.


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

## Projektstruktur

```
bot/
  config.py     # Konfiguration aus .env
  strategy.py   # MA-Crossover-Signal
  memory.py     # Zwei-Datei-Gedächtnis (Ledger + Lessons)
  brain.py      # Claude: Pre-Trade-Check + Post-Trade-Lektionen
  broker.py     # Alpaca (Paper/Live) + Simulations-Broker
  main.py       # Der Loop
memory/
  ledger.jsonl  # entsteht beim ersten Trade
  lessons.md    # wächst mit jedem Verlust-Trade
tests/          # Strategie- und Memory-Tests
```
