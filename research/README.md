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

---

# Knock-outs über Stunden statt Tage

Die Studie oben hält fünf Tage. Das ist nicht der Fall, um den es meistens geht: rein,
ein paar Stunden halten, vor Handelsschluss raus. Dieses Modul rechnet genau das,
auf 15-Minuten-Balken, damit der Pfad innerhalb des Tages sichtbar ist.

Zwei Dinge sprechen für die kurze Haltedauer, und beide stimmen:

- **Keine Finanzierung.** Wer vor Schluss glattstellt, zahlt keine Übernachtzinsen —
  bei Hebel 30 immerhin rund 0,48 % pro Tag.
- **Kaum Knock-out-Risiko.** Die Wahrscheinlichkeit, eine Schwelle zu berühren, wächst
  mit der Wurzel der Zeit. Über zwei Stunden ist das ein völlig anderes Risiko als über
  fünf Tage.

## Das Knock-out-Problem verschwindet tatsächlich

Hebel 30, 30 Aktien, 15-Minuten-Balken:

| Haltedauer | ausgeknockt | *5 Tage zum Vergleich* |
|---|---:|---:|
| 30 Minuten | 0,20 % | *69 %* |
| 1 Stunde | 0,47 % | |
| 2 Stunden | 1,09 % | |
| 3,2 Stunden | 1,97 % | |

Von 69 % auf 0,2 %. Das ist keine kleine Verbesserung, das ist die Beseitigung des
Problems.

## Nur war das Knock-out nie das eigentliche Problem

Bilanz **ohne jede Kosten**:

| Haltedauer | Gewinntrades | Mittelwert |
|---|---:|---:|
| 30 Minuten | 49,75 % | **−0,007 %** |
| 1 Stunde | 49,81 % | −0,024 % |
| 2 Stunden | 49,82 % | −0,078 % |
| 3,2 Stunden | 49,74 % | −0,195 % |

Der Erwartungswert ist null. Kein Vorteil, keine Richtung, ein Münzwurf. Das Knock-out
hat diese Tatsache nur überdeckt.

## Und damit entscheidet allein der Spread

Mittelwert je Trade, nach Kostenannahme:

| Spread | 0,5 h | 1 h | 2 h | 3,2 h |
|---|---:|---:|---:|---:|
| 0,0 % | −0,007 | −0,024 | −0,078 | −0,195 |
| 0,2 % | −0,207 | −0,223 | −0,275 | −0,391 |
| 0,5 % | −0,506 | −0,521 | −0,572 | −0,685 |
| 1,0 % | −1,005 | −1,019 | −1,067 | −1,175 |

Der Verlust ist **exakt der Spread**. Nichts anderes passiert bei diesem Trade.

Und weil kurze Haltedauern viele Trades bedeuten, zahlt man ihn oft. Bei 2 Stunden
Haltedauer und 1 % Spread, vollem Einsatz:

| Trades pro Tag | aus 1.000 € nach einem Jahr |
|---|---:|
| 1 | 68,50 € |
| 2 | 4,69 € |
| 3 | 0,32 € |

## Warum der Hebel den Spread mitvergrößert

Bei Hebel 30 muss der Kurs nur **+0,033 %** laufen, um 1 % Spread zu decken. Das klingt
nach nichts. Es ist aber ein Münzwurf, ob er in die richtige Richtung geht — im Mittel
bleibt der Spread stehen.

Der Hebel vervielfacht eben nicht nur den Gewinn, sondern die Kosten identisch mit.
Deshalb ist bei hohem Hebel und kurzer Haltedauer der Spread die gesamte Geschichte.

```bash
python -c "from research.intraday_ko import sweep_holds"   # siehe Modul
```

---

# Kerzenmuster einzeln vermessen

Nicht „was macht der Durchschnitt aller Kerzen", sondern: Wenn genau **dieses** Muster
auftritt — was macht die nächste Kerze dann?

```bash
python -m research.pattern_cli                 # 25 Muster, marktbereinigt
python -m research.pattern_cli --horizon 5     # fünf Kerzen vorwärts
python -m research.pattern_cli --raw           # ohne Marktbereinigung
```

25 Muster: Doji, Hammer, Shooting Star, Marubozu, Engulfing, Harami, Piercing Line,
Dark Cloud, Tweezer, Inside/Outside Bar, Morning/Evening Star, Three White Soldiers,
Three Black Crows, 20-Tage-Ausbrüche, Gaps, Double Top, Double Bottom.

## Zwei Messlatten, die man leicht falsch setzt

**Die Basisrate ist nicht 50 %.** Aktien steigen an 51,84 % aller Tage. Ein Muster mit
52 % Trefferquote ist der Normalzustand, kein Signal.

**Bärische Muster brauchen Marktbereinigung.** Eine Short-Position verliert in einem
steigenden Markt schon deshalb, weil der Markt steigt. Ohne Bereinigung sieht jedes
bärische Muster nach einem starken Befund aus — in die falsche Richtung.

Was das ausmacht, am Beispiel `double_top`:

| | t-Wert |
|---|---:|
| roh gerechnet | **−3,38** (sieht signifikant aus) |
| marktbereinigt | **−1,31** (nichts) |

Der ganze scheinbare Befund war der Aufwärtsdrift des Marktes.

## Ergebnis

**264.870 Kerzen, 95 Aktien, 2015–2026, marktbereinigt.** Basisrate 49,56 %.

Kein einziges der 25 Muster erreicht die bei 25 Tests nötige Schwelle von |t| > 2,8.
Größter gemessener Wert: **2,12** (`gap_up`). Die Trefferquoten liegen alle zwischen
48,5 % und 50,9 % — also im Rauschen um die Basisrate.

## Der entscheidende Test

Bestes Muster in der ersten Hälfte suchen, in der zweiten prüfen:

| | 2015–2020 | 2021–2026 |
|---|---:|---:|
| `doji` (Bester der 1. Hälfte) | 50,15 %, t=+1,95 | 48,73 %, **t=−0,69** |

Und die Zahl, um die es geht:

> **Korrelation der t-Werte zwischen beiden Hälften: −0,004**

Null. Wie gut ein Muster in sechs Jahren abgeschnitten hat, sagt **nichts** darüber,
wie es in den nächsten sechs Jahren abschneidet. Genau das müsste anders sein, wenn
die Muster echt wären.

Höchste Trefferquote irgendwo im ganzen Datensatz: 52,65 %. Nicht 60 %, nicht 70 %.

---

# Selektivität: bringt es etwas, nur die besten Signale zu handeln?

Die Idee: Nicht auf beliebige Trades wetten, sondern aus vielen Möglichkeiten die
zuversichtlichsten wenigen auswählen. Von tausend Kandidaten die zehn besten.

Das ist testbar, und zwar direkt: Das Modell aus `ml.py` gibt für jede Aktie und jeden
Tag eine Wahrscheinlichkeit aus. Man kann sie sortieren, oben abschneiden und nachsehen,
ob die Trefferquote steigt.

## Kalibrierung zuerst

Bevor man die „besten" auswählt, muss die Rangfolge überhaupt etwas bedeuten. Sagt das
Modell 70 %, steigen dann auch 70 %?

| Dezil | Modell sagt | tatsächlich | Abweichung |
|---:|---:|---:|---:|
| 1 | 36,08 % | 50,16 % | **+14,08 pp** |
| 5 | 51,48 % | 51,81 % | +0,33 pp |
| 9 | 62,47 % | 53,66 % | −8,81 pp |
| 10 | **75,40 %** | **54,07 %** | **−21,33 pp** |

Das Modell ist massiv überzeugt von sich. Seine Wahrscheinlichkeiten reichen von 5,7 %
bis 98,2 % — die Wirklichkeit dahinter bewegt sich zwischen 50 % und 54 %.

## Und die Auswahlkurve

Nur die besten N pro Tag handeln (aus rund 95 Kandidaten täglich):

| beste pro Tag | Modell sagt | **tatsächlich** | nach Kosten |
|---:|---:|---:|---:|
| 100 | 53,33 % | **51,68 %** | −1,09 bp |
| 50 | 55,83 % | 52,08 % | −0,98 bp |
| 20 | 57,82 % | 51,95 % | −1,38 bp |
| 10 | 58,93 % | **51,65 %** | −2,65 bp |
| 5 | 59,87 % | 51,66 % | −1,41 bp |
| 3 | 60,48 % | **50,80 %** | −1,93 bp |
| 1 | 61,53 % | 51,05 % | +0,83 bp |

Die mittlere Spalte steigt von 53 % auf 62 %. Die rechte bleibt flach bei 51 %.

**Selektivität erhöht die Zuversicht, nicht die Trefferquote.** Je wählerischer man
wird, desto größer die Lücke zwischen dem, was man zu wissen glaubt, und dem, was
eintritt.

## Die Kontrolle

Dasselbe mit einem Modell, das auf **durchgewürfelten** Zielwerten trainiert wurde:

| beste pro Tag | tatsächlich | nach Kosten | Sharpe |
|---:|---:|---:|---:|
| 10 | 52,11 % | +0,72 bp | +0,15 |
| 5 | 51,92 % | +1,89 bp | **+0,29** |
| 3 | 51,90 % | +1,89 bp | +0,23 |

Das auf reinem Rauschen trainierte Modell schneidet bei enger Auswahl **besser** ab als
das echte. Damit ist jeder scheinbare Gewinn durch Selektivität als Zufall ausgewiesen.

## Der Test prüft sich selbst

`test_selectivity_raises_hit_rate_when_model_is_real` speist ein künstliches Modell mit
echtem Signal ein und verlangt, dass die Trefferquote bei engerer Auswahl **steigt**.
Der Test besteht. Das Messwerkzeug funktioniert also — die flache Kurve auf echten
Daten ist ein Ergebnis, kein kaputtes Messgerät.

---

# Muster selbst finden

Bekannte Formationen sind bekannt — und damit sehr wahrscheinlich wegarbitriert. Dieses
Modul nimmt kein Lehrbuch, sondern sucht selbst.

```bash
python -m research.discovery_cli                       # Formmuster, 5 Balken
python -m research.discovery_cli --kind candle --window 4
python -m research.discovery_cli --shuffle             # Kontrolllauf ohne Signal
```

## Wie gesucht wird

Jedes Kursfenster wird in ein **Symbolwort** übersetzt. Zwei Kodierungen:

**Formmuster.** Das Fenster wird z-normiert, damit nur die *Form* zählt und nicht das
Kursniveau — ein Anstieg von 10 auf 11 € ergibt dasselbe Wort wie einer von 100 auf
110 €. Dann wird jeder Punkt einer von 3–5 Klassen zugeordnet: `ddbba`, `abadd`, …

**Kerzenmuster.** Jede Kerze wird nach Richtung und Körpergröße kodiert (`H` große
grüne, `h` kleine grüne, `o` Doji, `l` kleine rote, `L` große rote), dann verkettet:
`hlHo`, `Loll`, …

Anschließend wird jedes vorkommende Wort einzeln vermessen — marktbereinigt und mit
nach Datum geclusterten t-Werten.

## Der Filter ist das Eigentliche

Wer 1.400 Muster testet, findet garantiert Dutzende mit traumhaften Werten. Drei Stufen
dagegen:

1. **FDR-Korrektur** (Benjamini-Hochberg) über alle gleichzeitig getesteten Muster
2. **Strikte Trennung**: gesucht wird nur bis 2020, geprüft ausschließlich ab 2021
3. **Kontrolllauf** mit durchgewürfelten Zielwerten

## Ergebnis

**1.410 selbst gefundene Muster**, keins aus einem Lehrbuch:

| Variante | getestet | nominell signifikant | **nach FDR** | out-of-sample gehalten |
|---|---:|---:|---:|---:|
| Form, 5 Balken, 4 Klassen | 322 | 21 | **0** | 36 % |
| Form, 7 Balken, 4 Klassen | 199 | 13 | **0** | 32 % |
| Form, 6 Balken, 3 Klassen | 271 | 15 | **0** | 52 % |
| Kerzen, 4 Balken | 615 | 31 | **0** | 48 % |

80 Muster sehen nominell signifikant aus. Nach Korrektur für die Menge der Tests bleibt
in **jeder** Variante exakt **null** übrig. Out-of-sample halten sie ihr Vorzeichen in
32–52 % der Fälle — Zufall wäre 50 %.

### Der Kontrolllauf entscheidet

Dieselbe Suche auf **durchgewürfelten** Zielwerten, wo es nichts zu finden gibt:

| | echte Daten | reines Rauschen |
|---|---:|---:|
| Muster getestet | 322 | 322 |
| nominell signifikant | 21 | **19** |
| bester t-Wert | 3,29 | **3,21** |

Praktisch identisch. Die Zahl der „Entdeckungen" auf echten Marktdaten ist nicht von
der auf Zufallsdaten zu unterscheiden.

### Ein Beispiel, das alles zeigt

Das Muster `babbcc` im Trainingszeitraum: **57,61 % Trefferquote**, +39,06 bp, t = 3,02.
Das ist die Größenordnung, nach der man sucht.

Im Haltezeitraum: 53,81 %, +7,19 bp, **t = 0,59**.

Und `ddbba`: Training 53,57 % und t = 3,14 — Holdout 47,20 % und t = −0,99. Vorzeichen
gedreht.

## Was das bedeutet

Der Einwand „bekannte Muster sind arbitriert, also nimm unbekannte" trifft ein echtes
Problem, aber die Lösung greift nicht. Ein unbekanntes Muster, das man durch Absuchen
von 1.400 Kandidaten gefunden hat, ist nicht eher echt — es ist ein Lottogewinner. Man
hat nicht das beste Muster gefunden, sondern das glücklichste.

Genau dagegen ist der Kontrolllauf gebaut: Er zeigt, wie viele Lottogewinner die Suche
allein durch ihre eigene Größe produziert.

---

# Die Muster, die es wirklich gibt

Alle Studien oben suchen nach Kurzfrist-Signalen — Stunden bis Wochen. Das ist der am
härtesten umkämpfte Bereich des Marktes, und dort war nichts. Es gibt aber eine zweite
Familie von Mustern, die seit Jahrzehnten dokumentiert ist. Sie unterscheidet sich in
drei Punkten:

- Sie wirkt im **Querschnitt**: nicht „steigt diese Aktie", sondern „steigt sie stärker
  als die anderen"
- Sie braucht **Monate**, nicht Stunden
- Sie ist keine Prognose, sondern eine **Risikoprämie** — man wird dafür bezahlt, etwas
  zu halten, das andere nicht halten wollen

## Ergebnis

Bestes Fünftel kaufen, schlechtestes verkaufen, monatlich umschichten, marktneutral.
95 Aktien, 2010–2026:

| Signal | pro Jahr | Sharpe | t | max. Drawdown |
|---|---:|---:|---:|---:|
| **Momentum (12 Monate ohne den letzten)** | **+6,88 %** | **+0,30** | +1,17 | −37,0 % |
| Kurzfrist-Gegenbewegung (1 Monat) | +0,38 % | +0,02 | +0,08 | −40,8 % |
| Langfrist-Gegenbewegung (5–1 Jahre) | −2,97 % | −0,15 | −0,52 | −62,9 % |
| Niedrige Volatilität | −20,83 % | −0,88 | −3,52 | −98,7 % |

**Momentum ist das erste Signal in diesem ganzen Repo, das die Halbierung übersteht:**

| | bis 2018 | ab 2018 |
|---|---:|---:|
| Momentum | t = +0,94, Sharpe +0,36 | t = +0,81, Sharpe +0,28 |

Kein Zusammenbruch, kein Vorzeichenwechsel. Genau das, woran alles andere gescheitert ist.

## Zwei Warnungen zum eigenen Ergebnis

**Der t-Wert von 1,17 ist nicht entscheidend.** Auf 95 Aktien über 16 Jahre lässt sich
Momentum nicht beweisen. Der Wert ist, dass er zur umfangreichen Literatur passt (die
mit tausenden Aktien über 90 Jahre arbeitet) und dass er in beiden Hälften steht.

**Der Volatilitätseffekt ist ein Artefakt.** Er sieht mit t = −3,52 am stärksten aus und
ist der unglaubwürdigste Wert der Tabelle. Grund: Survivorship Bias. Im wildesten
Viertel liegt der mittlere Gesamtfaktor bei 63,30, der Median aber bei 13,14 — die
Verzerrung kommt von wenigen Überlebenden wie NVDA. Das Universum ist die
Zusammensetzung von heute, und die wilden Aktien, die es bis heute geschafft haben,
sind genau die, die gewaltig gestiegen sind.

Das ist derselbe Bias, der ganz oben in diesem Dokument als Einschränkung steht — hier
sieht man ihn zum ersten Mal wirken.

## Momentum verträgt keinen Hebel

| Haltedauer | pro Jahr | Sharpe | max. Drawdown |
|---|---:|---:|---:|
| 1 Monat | +6,89 % | +0,30 | −37,0 % |
| 3 Monate | +3,39 % | +0,19 | −43,8 % |
| 6 Monate | +1,62 % | +0,06 | −69,1 % |
| 12 Monate | −0,55 % | −0,02 | −87,3 % |

Der schlechteste Einzelmonat der Strategie: **−26,28 %**. Mit Hebel 30 wären das −788 %.

> **Höchster Hebel, den dieses Signal überhaupt verträgt: 3,8**

Nicht 30. Nicht 50. Das ist die Zahl, an der sich die ganze Frage entscheidet.

## KORREKTUR: Momentum repliziert nicht auf dem größeren Datensatz

Das Ergebnis oben (+6,88 % pro Jahr) stammt aus 95 Aktien ab 2010. Auf **159 Aktien
ab 2000** verschwindet es:

| | 95 Aktien, ab 2010 | 159 Aktien, ab 2000 |
|---|---:|---:|
| pro Jahr | +6,88 % | **−0,21 %** |
| Sharpe | +0,30 | **−0,01** |
| t | +1,17 | **−0,05** |

**Replikation über 5 unabhängige Sektoren:** positiv in 3 von 5. Bei reinem Zufall
wären es im Mittel 2,5 — die Wahrscheinlichkeit für „3 oder mehr" liegt bei 50 %.

| Sektor | pro Jahr | Sharpe | t |
|---|---:|---:|---:|
| Technologie | +10,73 % | +0,35 | +1,73 |
| Gesundheit | +4,18 % | +0,21 | +0,75 |
| Industrie | +0,74 % | +0,04 | +0,21 |
| Energie/Rohstoff | −0,01 % | −0,00 | −0,00 |
| Finanzen | −4,38 % | −0,15 | −0,70 |

**Replikation über 5 unabhängige Zeiträume:** positiv in 2 von 5.

| Zeitraum | pro Jahr | Sharpe |
|---|---:|---:|
| 2001–2005 | −2,51 % | −0,08 |
| 2006–2010 | −6,83 % | −0,27 |
| 2011–2015 | +9,26 % | +0,76 |
| 2016–2020 | −7,86 % | −0,38 |
| 2021–2026 | +7,31 % | +0,44 |

**Und die Kontrolle:** ersetzt man das Momentum-Signal durch **Zufallszahlen**, kommt
+2,08 % pro Jahr bei Sharpe +0,26 heraus — also *besser* als das echte Signal.

Damit ist das Ergebnis der vorigen Sektion zurückgezogen. Es war ein Artefakt aus
Universum und Zeitraum.

## Warum dieser Test trotzdem nichts beweist — in beide Richtungen

Der Test ist **systematisch gegen Momentum verzerrt**, und zwar aus einem konkreten
Grund:

Momentum verkauft short die schwächsten Aktien. Die schwächsten Aktien der Geschichte
sind genau die, die pleitegegangen sind — Lehman, Enron, WorldCom, Kodak, Sears,
Wirecard, SVB. Die sind in einem Universum aus heutigen Firmen **alle nicht enthalten**.
Der Short-Zweig wird also planmäßig um seine besten Trades gebracht.

Dazu kommt: 2000 haben nur 86 % der Aktien überhaupt Daten, und drei von acht Sektoren
liefen mangels Historie gar nicht durch. Der Drawdown von −101 % im Finanzsektor zeigt
außerdem, dass die einfache Gleichgewichtung ohne Risikosteuerung an ihre Grenze stößt.

**Fazit: Mit frei verfügbaren Yahoo-Daten lässt sich Momentum weder belegen noch
widerlegen.** Nicht wegen mangelnder Mühe, sondern weil die Datenquelle strukturell
ungeeignet ist. Genau dafür existieren survivorship-freie Point-in-Time-Datenbanken
(CRSP, Compustat) — und genau deshalb wird akademische Finanzforschung mit ihnen
gemacht und nicht mit Gratisdaten.

---

# Fundamentaldaten: bringt es etwas, die guten Firmen auszuwählen?

Alle Studien oben benutzen ausschließlich Kurse. Das ist eine echte Lücke — niemand
wählt Aktien nach Kerzenformen aus. Man schaut auf Umsatz, Gewinn, Marge,
Eigenkapitalrendite: **wie das Unternehmen aufgestellt ist.**

Quelle ist SEC EDGAR, kostenlos und offiziell. Entscheidend ist das Feld `filed` — das
Datum, an dem eine Zahl eingereicht und damit öffentlich wurde. Der Quartalsgewinn zum
31.03. ist nicht am 31.03. bekannt, sondern erst vier bis sechs Wochen später. Wer das
Quartalsende statt des Einreichungsdatums benutzt, handelt mit Wissen aus der Zukunft.

## Ergebnis: die starken Firmen schneiden schlechter ab

159 Firmen, 8.335 Beobachtungen, 63 Quartale, 12 Monate Haltedauer, marktbereinigt.
Bestes Fünftel gegen schlechtestes:

| Kennzahl | oberes Fünftel | unteres Fünftel | Differenz | t |
|---|---:|---:|---:|---:|
| Eigenkapitalquote | +6,39 % | +2,81 % | +3,49 % | +1,81 |
| Umsatzwachstum | +6,60 % | +5,34 % | +1,71 % | +0,71 |
| Kapitalrendite | +3,83 % | +8,22 % | −4,04 % | −1,91 |
| Eigenkapitalrendite | +4,72 % | +8,75 % | −3,80 % | −2,52 |
| **Marge** | +1,26 % | **+10,87 %** | **−10,20 %** | **−4,19** |
| **Gewinnwachstum** | +0,73 % | **+8,08 %** | **−7,71 %** | **−4,43** |

Bei 6 gleichzeitigen Tests wäre |t| > 2,6 belastbar. **Zwei Kennzahlen überschreiten
das deutlich — beide mit negativem Vorzeichen.**

Die Firmen mit den höchsten Margen und dem stärksten Gewinnwachstum liefern über die
folgenden zwölf Monate **7 bis 10 Prozentpunkte weniger** als die schwächsten. Und
das Vorzeichen hält in beiden Teilzeiträumen (2010–2017 und 2018–2026) bei allen sechs
Kennzahlen.

## Zwei Erklärungen, und beide zählen

**Die Zahlen sind längst im Kurs.** Wenn Apple 27 % Marge meldet, ist das binnen Minuten
öffentlich und eingepreist. Die besten Firmen auszuwählen heißt, das zu kaufen, was
alle bereits als gut erkannt haben — zu dem Preis, den alle dafür hochgeboten haben.
Die Information ist kein Vorteil; sie steckt schon im Preis. Das ist die bekannte
Value-Prämie beziehungsweise die Kehrseite davon, und die Richtung passt zur Literatur.

**Aber Survivorship Bias zeigt in dieselbe Richtung.** Das Universum besteht aus Firmen,
die es heute noch gibt. Eine Firma mit miserabler Marge 2012, die bis 2026 überlebt hat,
muss sich erholt haben — die Erholungsfälle sind drin, die Pleiten fehlen. Genau das
lässt das untere Fünftel künstlich gut aussehen.

**Beides lässt sich mit diesen Daten nicht sauber trennen.** Der Befund ist also nicht,
dass „schlechte Firmen kaufen" funktioniert. Der Befund ist, dass **„gute Firmen
auswählen" nachweislich nicht funktioniert** — und das ist die Richtung, auf die es
hier ankommt.

## Was das für die Auswahl bedeutet

Die naheliegendste Auswahlmethode überhaupt — Quartalszahlen lesen, die stärksten
Firmen kaufen — liefert in diesem Test eine Unterperformance, keine Überperformance.
Es ist das einzige statistisch klare Ergebnis dieses Repos, und es zeigt gegen die
Intuition.
