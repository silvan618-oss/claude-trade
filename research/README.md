# Ereignis-Studie

Misst an echten Kursdaten, was nach nachrichtengetriebenen Kurssprüngen passiert —
und ob sich das mit Hebel handeln lässt.

Die Frage dahinter: *„Wichtiges Ereignis passiert, Aktie reagiert, da steige ich mit
Hebel ein."* Diese Studie prüft, ob davon etwas übrig bleibt, wenn man die Nachricht
erst lesen muss.

## Ausführen

```bash
pip install -r requirements.txt
python -m research.cli
python -m research.cli --gap 0.06 --horizon 10   # andere Schwellen
pytest tests/test_eventstudy.py
```

Kursdaten kommen von der öffentlichen Yahoo-Chart-API und landen in `data_cache/`.
Kein API-Key nötig. Der erste Lauf dauert wenige Minuten, danach läuft alles aus dem Cache.

## Aufbau

| Datei | Aufgabe |
|---|---|
| `data.py` | Yahoo-Client, Cache, Aktienuniversum (95 liquide US-Werte) |
| `events.py` | Ereigniserkennung + **Zufallskontrollgruppe** |
| `eventstudy.py` | Vorwärtsrenditen, Marktbereinigung, geclusterte t-Werte |
| `knockout.py` | Hebelsimulation mit Pfadprüfung, Kosten, Kapitalentwicklung |
| `cli.py` | kompletter Lauf mit Bericht |

**Ereignis** = Übernacht-Gap ≥ 4 % zusammen mit ≥ 2× normalem Handelsvolumen.
Ein Stellvertreter für „zu dieser Firma gab es wichtige Nachrichten", der sich ohne
Nachrichtendatenbank aus Kurs und Volumen ableiten lässt.

**Einstieg** ist immer der *Schlusskurs des Ereignistages*. Der Gap ist da längst
gelaufen. Gemessen wird also nur, was für jemanden erreichbar ist, der die Meldung
erst lesen muss.

## Vier Dinge, die diese Studie richtig macht

Das sind genau die Stellen, an denen die meisten privaten Backtests still scheitern.

1. **Splits herausgerechnet.** Yahoo liefert `adjclose` bereinigt, OHLC aber roh.
   Wer das mischt, sieht bei NVDAs 10:1-Split einen Gap von −90 % und findet
   „Ereignisse", die nie stattgefunden haben. Alle vier Kurse werden mit demselben
   Faktor skaliert.
2. **Kein Zukunftswissen.** Volumen-Normalniveau und Volatilität nutzen ausschließlich
   zurückliegende Fenster. Tests prüfen das explizit.
3. **Geclusterte t-Werte.** Ereignisse ballen sich an denselben Tagen — an einem
   Crashtag gapt der halbe Markt gleichzeitig. Behandelt man die als unabhängig,
   wird der t-Wert um ein Vielfaches zu groß.
4. **Zufallskontrollgruppe.** Dieselbe Auswertung läuft über zufällige Tage in
   denselben Aktien. Wenn die Ereignisse nicht deutlich außerhalb dessen liegen,
   was der Zufall ohnehin produziert, gibt es keinen Effekt.

## Ergebnis

2.767 Ereignisse, 95 Aktien, 2015 bis 2025.

**Die Bewegung ist vorbei, bevor man handeln kann.**

| Phase | Mittelwert |
|---|---|
| Übernacht-Gap, vor Eröffnung | **+7,48 %** |
| Ereignistag ab Eröffnung | +0,34 % |
| die folgenden 5 Handelstage | −0,12 % |
| die folgenden 20 Handelstage | +0,02 % |

Über 95 % der Reaktion liegt im Gap — also in dem Moment, in dem die Börse noch
geschlossen war. Was danach kommt, ist nicht von null zu unterscheiden.

**Kein belastbarer Drift.** Über alle Horizonte bleibt der geclusterte t-Wert
unter 2,3; als belastbar gilt |t| > 3. Die Zufallskontrollgruppe liefert
teilweise höhere Werte als die Ereignisse selbst.

**Mit Hebel wird es schlimmer, nicht besser** (5 Tage halten):

| Hebel | Schwelle | ausgeknockt | Richtung stimmte, trotzdem raus | Median |
|---:|---:|---:|---:|---:|
| 50 | 2,0 % | **69,0 %** | **46,0 %** | −100 % |
| 20 | 5,0 % | 40,3 % | 18,1 % | −31 % |
| 10 | 10,0 % | 19,6 % | 5,4 % | −4,6 % |
| 5 | 20,0 % | 4,9 % | 0,3 % | −0,7 % |

Bei Hebel 50 wird fast die Hälfte der Trades, deren Richtung am Ende **richtig** war,
vorher vom Rauschen ausgeknockt.

### Die Mittelwertfalle

Bei Hebel 50 steht ein Mittelwert von **+1,00 %** pro Trade. Das sieht nach einem
funktionierenden System aus. Es ist keins:

- 95-%-Vertrauensintervall: **[−6,7 %, +9,0 %]** — nicht von null zu unterscheiden
- Ohne die 5 besten von 2.766 Trades: **−2,65 %**
- Geometrische Rendite bei vollem Einsatz: **−100 %**
- Selbst bei nur 5 % Einsatz pro Trade enden nach 100 Trades nur **30 %** der Pfade im Plus

Bei Verteilungen mit Totalverlustrisiko sagt der arithmetische Mittelwert nichts
über das aus, was mit dem Kapital tatsächlich passiert.

## Was die Studie *nicht* zeigt

Ehrlichkeit über die Grenzen gehört dazu:

- **Survivorship Bias.** Das Universum ist die Zusammensetzung von heute. Firmen, die
  pleitegegangen oder übernommen wurden, fehlen.
- **Der Gap ist ein grober Stellvertreter.** Er vermischt Quartalszahlen, Übernahmen,
  Zulassungen und Sektorschocks. Nach Ereignistyp getrennt könnte einzelnes davon
  ein anderes Bild zeigen — dafür bräuchte es eine echte Ereignisdatenbank.
- **Nur US-Large-Caps.** Genau das Segment mit der stärksten Konkurrenz. Bei kleineren
  europäischen Werten ist mehr zu erwarten, weil dort niemand systematisch mitliest.
- **Nur Momentum getestet.** Die Studie unterstellt, dass die Bewegung weitergeht.
  Gap-Downs zeigen leichte Gegenbewegung — auch das ist nicht signifikant, aber es
  wäre die naheliegendere nächste Hypothese.

Ein schwacher positiver Drift nach Gap-Ups über 20 Tage (rund +0,9 %, t ≈ 2,0) zeigt
in die Richtung, die die Literatur zum Post-Earnings Announcement Drift erwarten lässt.
Bei über hundert getesteten Varianten ist t ≈ 2 aber kein Befund, und 0,9 % über
20 Tage liegen unter den Handelskosten der meisten Privatanleger.

---

# Multi-Timeframe: mehrere Zeitebenen gleichzeitig

Prüft die Behauptung *„wenn 15-Minuten-, Stunden- und Tageschart alle dasselbe sagen,
ist das Signal belastbarer."*

```bash
python -m research.tf_cli                              # 1h-Basis + Tageschart, 3 Jahre
python -m research.tf_cli --base 15m --higher 1h,1d    # alle drei Ebenen, 88 Tage
```

## Der Fallstrick, den das Modul abdichtet

Um 14:00 Uhr steht die Tageskerze **noch nicht fest** — sie schließt erst am Abend.
Wer trotzdem ihren Trend abliest, benutzt Wissen aus der Zukunft. Das ist der mit
Abstand häufigste Fehler bei Multi-Timeframe-Backtests, und er macht aus jedem
Zufallssignal einen Traumbacktest.

Deshalb bekommt hier jeder Balken ein `available_at` — den Zeitpunkt, ab dem er
abgeschlossen und damit überhaupt lesbar ist. Höhere Zeitebenen werden ausschließlich
über dieses Feld angebunden (`merge_asof`, rückwärts). Drei Tests sichern das ab,
darunter einer, der prüft, dass das Entfernen späterer Tagesdaten frühere Ergebnisse
nicht verändert.

## Was die Datenquelle hergibt

| Auflösung | Historie |
|---|---|
| 1m | 8 Handelstage |
| 5m / 15m / 30m | 88 Kalendertage |
| 1h | ~3 Jahre |
| 1d | 10+ Jahre |

Ein 10-Minuten-Intervall bietet Yahoo nicht an; 15m ist die nächstgelegene Stufe.

## Ergebnis

**152.414 Stundenbalken, 30 Aktien, 2023–2026** (1h-Basis + Tageschart):

Die Zeitebenen sind **weitgehend unabhängig** — die Korrelation der Trendrichtungen
liegt bei nur **+0,18**. Eine Bestätigung über mehrere Ebenen ist also tatsächlich
zusätzliche Information und nicht bloß dieselbe Zahl doppelt abgelesen.

Nur nützt es nichts:

| | n | Mittel | Trefferquote | t geclustert |
|---|---:|---:|---:|---:|
| nur 1h-Chart | 151.394 | +3,43 bp | 50,78 % | — |
| 1h + 1d einig | 90.974 | +3,87 bp | 50,97 % | 1,45 |

**46.830 15-Minuten-Balken, 30 Aktien, 3 Monate** (alle drei Ebenen, 4-Stunden-Horizont):

| | n | Mittel | Trefferquote | t geclustert |
|---|---:|---:|---:|---:|
| nur 15m | 45.570 | −1,27 bp | 49,67 % | −0,24 |
| 15m + 1h | 30.903 | −4,43 bp | 49,16 % | −0,84 |
| 15m + 1h + 1d | 17.165 | −4,29 bp | 49,75 % | −1,06 |

Jede zusätzliche Zeitebene halbiert die Zahl der Signale und verbessert das Ergebnis
nicht. Zum Vergleich: Ein Roundtrip kostet bei liquiden US-Aktien 10 bis 30 bp. Der
gemessene Effekt liegt eine Größenordnung darunter.

## Grenzen

- Das 88-Tage-Fenster ist **zu kurz für die Tagesebene**: Der Tagestrend dreht dort im
  Schnitt nur 2,6 mal, ist also fast eine Konstante. Deshalb lässt sich seine
  Korrelation im 15m-Lauf nicht berechnen (NaN in der Matrix). Belastbar ist nur der
  1h-Lauf über drei Jahre.
- Intraday-Daten sind **nicht dividendenbereinigt**. Über Tage bis wenige Jahre
  vertretbar, für lange Zeiträume nicht.
- Getestet ist der EMA-Crossover als Trenddefinition. Andere Definitionen (Struktur,
  Ranges, Volumenprofil) sind damit nicht widerlegt — nur diese eine.

---

# Mustererkennung: aus der Vergangenheit die Zukunft prognostizieren

Genau die Kernidee. Ein Modell bekommt 33 Merkmale, die am Tag t bekannt sind, und
soll den Tag t+1 vorhersagen.

```bash
python -m research.ml_cli                 # Gradient Boosting
python -m research.ml_cli --model rf      # Random Forest
python -m research.ml_cli --shuffle       # Kontrollprobe: Ziel durchgewürfelt
```

## Zwei Regeln, ohne die es eine Selbsttäuschung wird

**Jedes Merkmal muss am Tag t berechenbar sein.** Ein einziges, das heimlich nach vorn
schaut, erzeugt Trefferquoten von 90 %, die live nicht existieren. Ein Test prüft das
hart: Löscht man alle Daten nach Tag t, dürfen sich die Merkmale bei t nicht ändern.

**Getestet wird nur auf Zeiträumen nach dem Training.** Walk-Forward mit wachsendem
Trainingsfenster und wanderndem Testfenster.

## Ergebnis

**264.967 Zeilen, 33 Merkmale, 95 Aktien, 2015–2026.**
Basisrate: 51,82 % aller Tage steigen — so gut ist „immer aufwärts tippen".

| Modell | im Training | ungesehen | Lücke |
|---|---:|---:|---:|
| Gradient Boosting | 69,98 % | 51,21 % | 18,77 Pp |
| Random Forest | **99,18 %** | **51,05 %** | **48,13 Pp** |
| Logistische Regression | 52,99 % | 51,17 % | 1,82 Pp |

Der Random Forest lernt die Vergangenheit **zu 99,18 %** auswendig und liegt auf
ungesehenen Daten bei 51,05 % — **unter** der Basisrate. Er ist schlechter, als immer
„aufwärts" zu tippen.

### Die Kontrollprobe, die alles erklärt

Dasselbe Modell, aber die Zielwerte vorher zufällig durchgewürfelt. Es gibt dann
buchstäblich **nichts** zu lernen:

| | im Training | ungesehen |
|---|---:|---:|
| Zufallsziel | **99,99 %** | 50,76 % |

99,99 % Trefferquote auf reinem Rauschen. Damit ist bewiesen: Die hohe Zahl im Training
ist kein entdecktes Muster, sondern Auswendiglernen. Jeder Backtest, der nur diese Zahl
zeigt, sagt nichts aus.

### Und beim Handeln

Täglich das zuversichtlichste Zehntel kaufen, 10 bp Kosten:

| Modell | Treffer | Mittel | Sharpe | Kapital |
|---|---:|---:|---:|---:|
| Gradient Boosting | 52,12 % | −1,03 bp | −0,08 | ×0,696 |
| Random Forest | 52,05 % | +0,67 bp | +0,10 | ×0,967 |
| Logistische Regression | 52,33 % | −0,55 bp | −0,04 | ×0,717 |
| **Zufallsziel** | 52,36 % | −1,05 bp | −0,25 | ×0,798 |

Das auf Rauschen trainierte Modell hat die **höchste Trefferquote** von allen.

Ohne Kosten sehen alle gut aus (+9 bis +11 bp, Kapital ×3,9 bis ×5,4) — aber das
Zufallsmodell erreicht dort **Sharpe +2,06** und schlägt damit jedes echte Modell.
Der Gewinn kommt nicht aus der Prognose, sondern daraus, dass irgendein Zehntel des
Marktes zu halten die allgemeine Aufwärtsdrift einsammelt. Die Modelle tragen nichts bei.

## Was das heißt

Die Muster **sind** in den Trainingsdaten — das Modell findet sie mit 99 % Genauigkeit.
Sie setzen sich nur nicht fort. Das ist der Unterschied zwischen einem Muster und einer
Regelmäßigkeit: Ein Muster in vergangenen Kursen ist so lange da, bis jemand darauf
handelt.
