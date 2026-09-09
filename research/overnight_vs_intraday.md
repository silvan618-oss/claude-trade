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

## Gegenprobe mit 27 weiteren Titeln

`python research/overnight_screen.py` zerlegt alle CSVs in `research/data/`
(Mega-Caps, Halbleiter, Blue Chips, Meme-Aktien, Index-ETFs und die im Video
genannten Länder Italien, Frankreich, Singapur, Thailand als US-ETFs).
ON = Overnight, ID = Intraday, „5J“ = letzte fünf Jahre, t = t-Statistik der
Differenz ON minus ID pro Tag.

```
          ab Buy&Hold Overnight Intraday ON bp/Tag ID bp/Tag t(ON-ID) ON ohne Top1% ON CAGR @5bp B&H CAGR  ON 5J  ID 5J
Symbol                                                                                                                 
AAPL    2007  +12448%    +2591%    +366%      +7.5      +4.4     +1.0          +75%          +4%     +28%   -45%  +278%
AMC     2013     -98%   +31964%    -100%     +31.5     -19.1     +3.3          -92%         +39%     -26%   -66%   -98%
AMD     2015  +18701%    +6096%    +203%     +16.5      +8.2     +1.2         +299%         +26%     +57%  +288%   +19%
COIN    2021     -45%      -21%     -31%      +3.3      +7.6     -0.3          -84%         -16%     -11%   -24%   -11%
EWG     2007    +165%       +9%    +142%      +1.1      +2.4     -0.5          -94%         -11%      +5%   -17%   +55%
EWI     2007     +40%       +4%     +34%      +1.1      +1.2     -0.1          -91%         -12%      +2%   +17%   +69%
EWJ     2007    +111%      -64%    +483%      -1.5      +3.9     -2.9          -95%         -16%      +4%   -12%   +57%
EWQ     2007     +82%      -42%    +212%      -0.3      +2.9     -1.4          -94%         -14%      +3%   -23%   +61%
EWS     2007    +266%      +24%    +196%      +1.3      +2.6     -0.5          -94%         -11%      +7%   +15%   +37%
GME     2007    +307%    +1619%     -76%     +12.5      +6.2     +0.7         -100%          +2%      +7%   -56%   -13%
GOOGL   2015    +915%     +151%    +304%      +4.1      +6.1     -0.5          -52%          -4%     +24%    +1%  +135%
INTC    2007    +762%      +40%    +517%      +1.9      +5.4     -1.0          -95%         -10%     +12%   +96%    +8%
IWM     2007    +418%     +793%     -42%      +4.8      -0.3     +2.3          +32%          -1%      +9%   +57%   -14%
JNJ     2007    +596%     +168%    +160%      +2.2      +2.4     -0.1          -26%          -7%     +10%    -7%   +89%
JPM     2007   +1102%     +652%     +60%      +4.9      +2.7     +0.7          -60%          -2%     +14%   +56%   +60%
KO      2007    +529%     +264%     +73%      +2.9      +1.6     +0.7          -27%          -6%     +10%   +69%    +4%
META    2012   +1514%     +913%     +59%      +8.0      +2.9     +1.2          -63%          +4%     +22%   +14%   +41%
MSFT    2007   +2209%     +342%    +422%      +3.6      +4.3     -0.3          -64%          -5%     +17%   +46%   +17%
MU      2010   +9784%   +68683%     -86%     +17.5      -1.5     +4.0        +2062%         +31%     +32%  +519%  +125%
NFLX    2007  +20103%     +455%   +3539%      +5.7     +10.6     -1.0          -96%          -4%     +32%    +8%   +21%
NVDA    2007  +40942%   +22503%     +82%     +14.4      +5.3     +1.7         +452%         +20%     +41%  +508%   +63%
PG      2007    +282%      -28%    +431%      -0.5      +3.9     -2.5          -83%         -13%      +7%   -16%   +35%
QQQ     2011   +1350%     +579%    +114%      +5.4      +2.5     +1.2          +71%          -0%     +19%   +57%   +22%
SPY     2007    +787%     +354%     +95%      +3.4      +1.8     +0.9          -22%          -5%     +12%   +37%   +28%
THD     2008    +117%     +148%     -13%      +2.9      +0.1     +1.2          -78%          -7%      +4%    -5%    +5%
TSLA    2010  +23055%   +38587%     -40%     +17.0      +3.0     +2.4         +520%         +28%     +40%   +85%   -19%
XOM     2007    +321%       -1%    +324%      +0.5      +3.9     -1.4          -85%         -12%      +8%   +36%  +153%

Titel mit Overnight > Intraday (gesamt): 16 von 27
Titel mit Overnight > Intraday (letzte 5 Jahre): 11 von 27
Titel, bei denen Overnight nach 5 bp Kosten Buy&Hold schlägt: 1 von 27
Titel mit |t| > 2 für Overnight minus Intraday: 6 von 27
```

Befund:

- **Kein allgemeines Gesetz.** Overnight schlägt Intraday über den ganzen
  Zeitraum bei 16 von 27 Titeln, in den letzten fünf Jahren nur bei 11 von 27.
  Statistisch belastbar (|t| > 2) ist die Differenz bei 6 Titeln, davon 4 in
  Richtung des Videos (MU, AMC, IWM, TSLA) und 2 dagegen (EWJ, PG).
- **Das extreme Muster ist ein Retail-Hype-Muster.** Die stärksten
  Overnight-Ausreißer sind Micron, AMC, GameStop, Tesla, Nvidia und AMD:
  hohe Aufmerksamkeit, viele Kleinanleger, große Earnings-Gaps. Genau das
  beschreiben Berkman et al. (2012). Bei AMC lief die Intraday-Kette auf
  –100 %, die Overnight-Kette auf +31.964 %, und trotzdem hat die Aktie
  insgesamt 98 % verloren.
- **Langweilige Titel zeigen es nicht.** Procter & Gamble, Exxon, Intel,
  Netflix, Microsoft, Alphabet und alle Länder-ETFs haben am Tag mehr
  verdient als in der Nacht. Bei den Länder-ETFs ist das erwartbar: Sie
  handeln in US-Zeit, die „Nacht“ des ETF ist der lokale Handelstag in
  Europa oder Asien. Die Grid-Charts im Video zu Italien, Frankreich,
  Singapur, Thailand beziehen sich auf lokale Indizes und sind damit nicht
  vergleichbar, aber die Aussage „gilt weltweit“ ist so nicht überprüfbar.
- **Ohne die besten 1 % der Nächte kippt fast alles.** Nur bei MU, AMD, NVDA,
  TSLA, QQQ, IWM und AAPL bleibt die Overnight-Kette dann positiv. Bei 20 von
  27 Titeln ist sie ohne die Ausreißer-Nächte negativ.
- **Nach 5 bp Kosten pro Round-Trip schlägt die Overnight-Strategie
  Buy-and-Hold bei genau einem Titel: AMC.** Und zwar nur, weil Buy-and-Hold
  dort –98 % war. Bei allen anderen 26 Titeln wäre einfaches Halten besser
  gewesen.

## Bewertung

- Das Phänomen (Overnight-Renditen > Intraday-Renditen im Durchschnitt) ist
  real und akademisch gut dokumentiert. Für Micron ist die Richtung auch in
  eigenen Daten seit 2010 klar bestätigt.
- Die Präsentation im Video ist irreführend: kumulierte Prozentzahlen über
  Jahrzehnte, Zuschreibung von Charts zur falschen Studie, keine Kosten, keine
  Steuern, keine Ausreißeranalyse, ein selektiv gewähltes Beispiel.
- Die Gegenprobe mit 27 weiteren Titeln zeigt: Das Muster ist auf Aktien mit
  hoher Retail-Aufmerksamkeit und großen Earnings-Gaps beschränkt. Es ist
  kein Marktgesetz.
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
