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
