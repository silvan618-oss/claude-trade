# Insider- & Congress-Signale (Analyse des QuiverQuant-Videos)

Dieses Dokument ordnet das Video ein, auf dem [`bot/insider.py`](../bot/insider.py)
basiert: Claude wird per **MCP-Connector** an **QuiverQuant** angebunden und
wertet Trades von Unternehmensinsidern und US-Kongressmitgliedern aus.

## Was im Video gezeigt wird

Kurz zusammengefasst, in der Reihenfolge des Videos:

1. In Claude unter *Settings → Connectors* einen QuiverQuant-MCP-Connector
   anlegen (QuiverQuant-Account vorausgesetzt).
2. In einem neuen Chat Claude anweisen, Quiver zu benutzen.
3. Beispiel-Prompts, u. a. sinngemaess: *"Finde Unternehmen, bei denen zuletzt
   3 oder mehr verschiedene Insider im selben Monat Aktien gekauft haben — mit
   Namen und Positionen"* und *"Welche Aktien haben Kongressmitglieder letztes
   Quartal am meisten gekauft, in welchen Ausschuessen sitzen sie, und wo
   ueberschneiden sich Sektoren?"*
4. Ausblick: ein Bot, der bei neuen Meldungen pingt, plus ein *Execution Layer*,
   der automatisch handelt (im Video als laufende 10.000-$-Challenge angeteasert).
5. Der eigentliche Guide wird nur per DM gegen Kommentar + Follow herausgegeben.

Die ersten Sekunden sind bewusst als starker Hook gebaut ("hunderttausende
Dollar"), das Video selbst ist Engagement-Bait. Die **Technik dahinter ist
trotzdem echt** — nur die Ertragsversprechen sind Marketing.

## Der Realitaetscheck — und wie er hier im Code landet

| Behauptung im Video | Realitaet | Umsetzung im Code |
|---|---|---|
| "Insider Trading" | Es ist legales Auswerten von **Pflichtveroeffentlichungen** (SEC Form 4, STOCK Act Reports), kein Handel mit nicht-oeffentlichen Informationen | Modul-Docstring in `bot/insider.py` benennt beide Quellen explizit |
| "in Echtzeit" | Gemeldet wird mit Verzug: Form 4 i. d. R. 2 Boersentage, Kongress-Reports bis zu 45 Tage. Ein Bot reagiert auf die **Meldung**, nie auf den Trade | `insider_max_filing_lag_days` (Default 21) verwirft zu spaet gemeldete Trades, statt sie als frisches Signal zu behandeln |
| "Politiker-Portfolios schlagen den Markt" | Historisch teils zutreffend — aber genau der Meldeverzug frisst die Kante fuer Nachahmer auf | `InsiderTx.filing_lag_days` wandert in den Ledger (`params.insider_max_filing_lag_days`), damit sich im Nachhinein auswerten laesst, ob spaete Meldungen schlechter performen |
| "einfach an einen Execution Layer haengen" | Technisch machbar, aber riskant: LLMs halluzinieren, Feldformate aendern sich, ein falsch geparster Betrag ist ein falscher Trade | Kein LLM ordert hier direkt. Das Signal entsteht **deterministisch in Python**, Claude darf nur zusaetzlich vetoen ([`bot/brain.py`](../bot/brain.py)); Ordergroesse bleibt an `RISK_PCT` gebunden |
| ein einzelner Insider-Kauf als Signal | Einzelkaeufe sind verrauscht (Ausuebung von Optionen, Steuerplanung, Diversifikation) | Gewertet wird nur **Cluster Buying**: mehrere *verschiedene* Kaeufer, Verkaeufer werden gegengerechnet, Doppelrollen (kauft und verkauft) fallen raus |

## Prompts fuer die manuelle Recherche in Claude

Diese Prompts brauchen **keinen** Bot — nur den QuiverQuant-Connector in Claude.
Die ersten beiden entsprechen sinngemaess denen aus dem Video, die uebrigen sind
Ergaenzungen, die zu den Filtern in `bot/insider.py` passen:

1. *Find companies where 3 or more different insiders bought shares in the same
   month recently. Show me who they are and their job titles.*
2. *Which stocks did members of Congress buy most last quarter, and which
   committees do they sit on? Flag any sector overlaps.*
3. *For every cluster buy you found, show the gap between transaction date and
   filing date, and how the stock moved between those two dates. Which of these
   signals were already priced in before the public could see them?*
4. *Separate open-market purchases from option exercises and 10%-owner
   transactions. Rank what is left by dollar value relative to the insider's
   known holdings.*
5. *Compare the last 12 months of cluster buys in this sector against a
   buy-and-hold of the sector ETF, assuming entry on the filing date, not the
   trade date. What was the actual edge after that delay?*

Prompt 3 und 5 sind die unbequemen: Sie messen genau die Verzoegerung, die im
Video unter den Tisch faellt. Wer die Ebene ernsthaft nutzen will, sollte mit
ihnen anfangen.

## Wie das Signal hier berechnet wird

`cluster_buy_signal()` in [`bot/insider.py`](../bot/insider.py) liefert `buy`, wenn
**alle** Bedingungen erfuellt sind:

- der Trade liegt innerhalb von `INSIDER_LOOKBACK_DAYS` (Default 30 Tage),
- die Meldung erfolgte hoechstens `INSIDER_MAX_FILING_LAG_DAYS` nach dem Trade,
- mindestens `INSIDER_MIN_BUYERS` **verschiedene** Personen haben gekauft,
- es gibt mehr Kaeufer als Verkaeufer,
- das Netto-Volumen (Kaeufe minus Verkaeufe in USD) ist positiv.

Zusaetzlich gewichtet `ROLE_WEIGHTS` die Rollen: ein CEO- oder CFO-Kauf zaehlt
mehr als der eines 10-%-Grossaktionaers, dessen Umschichtungen oft nichts ueber
die Geschaeftslage aussagen. Das Ergebnis steht als `score` im Signal und im
Ledger — als Auswertungsgroesse, nicht als Multiplikator fuer die Positionsgroesse.

**Ausstiege kommen weiterhin vom MA-Crossover.** Meldedaten taugen als
Einstiegs-, aber nicht als Ausstiegssignal: Insider-Verkaeufe sind noch
verrauschter als Kaeufe (Vesting, Steuern, 10b5-1-Plaene).

## Nutzung

```bash
# Scanner: einmal ueber eine Symbolliste, nur Treffer ausgeben
python -m bot.insider AAPL MSFT NVDA
python -m bot.insider --all          # auch Symbole ohne Signal

# Im Loop als Bestaetigung fuer das Crossover
SIGNAL_MODE=combined python -m bot.main --once
```

Ohne `QUIVER_API_KEY` laeuft die Ebene mit simulierten Meldungen — dieselbe
Logik wie beim `SimulatedBroker`, damit der Pfad ohne Account testbar bleibt.
Die "Ping mich bei neuen Meldungen"-Idee aus dem Video ist bewusst **nicht** als
Dauer-Daemon gebaut: `python -m bot.insider` per Cron alle paar Stunden und die
Ausgabe an einen Notifier gehaengt reicht voellig — Form-4-Meldungen erscheinen
in Schueben nach Boersenschluss, nicht sekuendlich.

## Grenzen, die bleiben

- **Die Endpunkte koennen sich aendern.** `QuiverQuantSource` parst tolerant
  (mehrere moegliche Feldnamen pro Wert). Kommen leere Werte zurueck, zuerst die
  aktuelle API-Doku im QuiverQuant-Account gegen die Konstanten oben im Client
  pruefen.
- **Cluster Buying ist ein schwaches Signal, kein Orakel.** Es ist ein Filter
  gegen Rauschen, keine Gewinngarantie.
- **Backtest vor Live.** Prompt 5 oben ist die Mindestpruefung: Einstieg am
  Meldetag, nicht am Handelstag — sonst backtestet man eine Information, die man
  nie hatte.
