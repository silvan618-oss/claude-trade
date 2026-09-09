# Faktencheck: „Stop day-trading, try night-trading instead“

Geprüft wurde ein virales Reel (@ELITEOPTIONSTRADER2), das behauptet: Wer Micron
jeden Tag zum Schluss kauft und zur Eröffnung verkauft, hätte +138 Mio. %
gemacht; wer das Gegenteil tut, –99,9 %. Das Muster gelte laut einer Studie im
*Journal of Financial Economics* (2019) für Apple, Amazon, Google und weltweite
Indizes, und die Erklärung sei: Kleinanleger handeln zur Eröffnung, Institutionen
zum Schluss.

Eigene Nachrechnung: `python research/overnight_vs_intraday.py` (Daten: viaNexus
EOD, vollständig adjustiert, Stand 2026-09-08; Micron erst ab 2010 verfügbar).

## Ergebnis in Kürze

| Behauptung | Befund |
|---|---|
| Micron: Overnight-Kette extrem positiv, Intraday-Kette extrem negativ | **Richtung stimmt** (2010–2026: Overnight +68.683 %, Intraday –85,6 %, Buy&Hold +9.784 %). Die konkrete Zahl „138 Mio. %“ (seit 1984) konnte mangels Daten vor 2010 nicht geprüft werden. |
| Das gilt genauso für Apple, Amazon, Google | **Nur teilweise.** Apple 2007–2026: Overnight +2.591 %, Intraday +366 % (beide positiv). Apple letzte 5 Jahre: Overnight **–45 %**, Intraday **+278 %**, also umgekehrt. Alphabet 2015–2026: Intraday (+304 %) schlägt Overnight (+151 %). |
| Die JFE-Studie belegt: „kaufe zum Schluss, verkaufe zur Eröffnung“ macht am ehesten Gewinn | **Falsch zugespitzt.** Lou/Polk/Skouras (JFE 134, 2019) untersuchen, wie sich die Gewinne von 14 *Faktorstrategien* (Momentum, Reversal, Value usw.) auf Nacht und Tag verteilen. Sie empfehlen keine Overnight-Haltestrategie. Die Grid-Charts einzelner Aktien und Länder stammen mit hoher Wahrscheinlichkeit aus Bruce Knutesons arXiv-Papieren (2020ff.), nicht aus der JFE-Studie. |
| Erklärung: Kleinanleger handeln zur Eröffnung, Institutionen zum Schluss (Liquidität) | **Im Kern korrekt wiedergegeben**, aber verkürzt. Berkman et al. (JFQA 2012) zeigen: Retail-Aufmerksamkeit treibt den Eröffnungskurs hoch, danach Reversal am Tag. Cushing/Madhavan (2000): Institutionen handeln zum Schluss wegen Bewertung zum Closing-Preis. Knuteson hält das für keine ausreichende Erklärung. |
| Daraus folgt eine profitable Strategie | **Nicht belegt.** Siehe unten: Kosten, Ausreißer und Instabilität. |

## Was die Zahlen wirklich zeigen

**1. Die Zerlegung erzeugt keine Rendite.** Overnight-Kette × Intraday-Kette =
Buy&Hold, exakt. Ein Wert von 138 Mio. % bei –99,9 % am Tag ist rechnerisch
nichts anderes als Buy&Hold seit 1984 (ca. 100.000 %), zerlegt in zwei
Faktoren. Wer täglich 4.000-mal einen kleinen positiven Faktor aufzinst, bekommt
zwangsläufig astronomische Prozentzahlen. Die Größe der Zahl sagt nichts über
die Größe des Effekts pro Tag aus.

**2. Pro Tag ist der Effekt klein und hängt an wenigen Nächten.**

| | Ø Overnight/Tag | Ø Intraday/Tag | Overnight ohne beste 1 % Nächte |
|---|---|---|---|
| Micron 2010–26 | +17,5 bp | –1,5 bp | +2.062 % statt +68.683 % |
| SPY 2007–26 | +3,4 bp | +1,8 bp | **–22 %** statt +354 % |
| Apple 2007–26 | +7,5 bp | +4,4 bp | +75 % statt +2.591 % |

Bei Micron sind 42 von 4.182 Nächten (fast alle Quartalszahlen-Gaps) für den
Großteil des Ergebnisses verantwortlich. Beim S&P 500 wird die Overnight-Kette
ohne die 50 besten Nächte negativ. Das ist kein stetiges „Nacht-Alpha“, sondern
Gap-Risiko aus Nachrichten außerhalb der Handelszeit.

**3. Nach Kosten bleibt bei Index und Blue Chips wenig bis nichts.** Die
Strategie ist ein Round-Trip pro Tag, rund 250 pro Jahr.

| Kosten pro Round-Trip | Micron CAGR | SPY CAGR | Apple CAGR |
|---|---|---|---|
| 0 bp | 48,2 % | 8,1 % | 18,3 % |
| 2 bp | 41,0 % | 2,8 % | 12,5 % |
| 5 bp | 30,7 % | –4,7 % | 4,3 % |
| 10 bp | 15,2 % | –16,0 % | –8,0 % |

Buy&Hold SPY im selben Zeitraum: 11,8 % p. a., ohne einen einzigen Trade und
ohne Steuerereignisse. Auktionskurse an Open und Close vermeiden zwar den
Spread, aber Slippage, Gebühren und vor allem Steuern auf 250 kurzfristige
Gewinne pro Jahr sind real. Die Literatur ist gespalten: Lachance (RFE 2023)
findet für ausgewählte Aktien Profitabilität nach Kosten, Analysen zu SPY
(Alpha Architect, Elm Wealth) kommen auf ein Nullsummenspiel oder Verlust.

**4. Der Effekt ist nicht stabil.** Apple hat die letzten fünf Jahre praktisch
nur am Tag verdient. Micron hatte 2015, 2018 und 2022 negative oder flache
Overnight-Jahre. Micron ist zudem ein Paradebeispiel für Selection Bias: Man
zeigt die Aktie mit dem extremsten Verlauf, nicht eine repräsentative.

## Bewertung

- Das Phänomen (Overnight-Renditen > Intraday-Renditen im Durchschnitt) ist
  real und akademisch gut dokumentiert. Für Micron ist die Richtung auch in
  eigenen Daten seit 2010 klar bestätigt.
- Die Präsentation im Video ist irreführend: kumulierte Prozentzahlen über
  Jahrzehnte, Zuschreibung von Charts zur falschen Studie, keine Kosten, keine
  Steuern, keine Ausreißeranalyse, ein selektiv gewähltes Beispiel.
- Als Handelsregel („Day-Trading durch Night-Trading ersetzen“) ist die These
  nicht belegt. Wer den Effekt trotzdem nutzen will, braucht: kostenlose
  Auktionsausführung, ein steuerneutrales Konto, Toleranz für Earnings-Gaps in
  beide Richtungen und einen Backtest mit realistischen Kosten.

## Quellen

- Lou, Polk, Skouras: *A tug of war: Overnight versus intraday expected returns*, JFE 134(1), 2019, 192–213.
- Berkman, Koch, Tuttle, Zhang: *Paying attention: Overnight returns and the hidden cost of buying at the open*, JFQA 47(4), 2012.
- Knuteson: *Strikingly Suspicious Overnight and Intraday Returns*, arXiv:2010.01727 (2020) und Folgepapiere.
- Lachance: *Night trading: Lower risk but higher returns?*, Review of Financial Economics 41(4), 2023.
- Cushing, Madhavan: *Stock returns and trading at the close*, Journal of Financial Markets 3, 2000.
