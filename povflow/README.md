# povflow

Erzeugt vollautomatisch vertikale Shorts, die aussehen wie mit dem Handy aus der
Ich-Perspektive gefilmt — inklusive eigener Ideen, Shotlist und fertigem
Voice-over-Skript mit Timecodes. Du sprichst nur noch drüber.

Ein Durchlauf liefert pro Folge:

```
output/2026-08-05_der-hafen/
  final_silent.mp4    <- fertig geschnittenes Video, ohne Sprache
  voiceover.txt       <- dein Skript, mit Timecodes pro Shot
  voiceover.srt       <- dasselbe als Untertitelspur fuer den Editor
  concept.json        <- die Idee
  shotlist.json       <- die Prompts, die an Veo gingen
  shots/              <- die einzelnen Rohclips
```

---

## Wichtig vorab: warum nicht "mit deinem Flow-Account"

**Flow hat keine API.** Google Flow ist ein reines Web-Interface. Die einzige
Möglichkeit, es "automatisch" zu bedienen, wäre ein Bot, der sich mit deinen
Zugangsdaten einloggt und die Oberfläche fernsteuert. Davon rate ich ab:

- Es verstößt gegen Googles Nutzungsbedingungen für automatisierten Zugriff.
- Google erkennt so etwas zuverlässig — im schlimmsten Fall ist dein **Google-Account
  gesperrt**, mit allem was dranhängt.
- Es bricht bei jedem UI-Update, also praktisch ständig.

Der offizielle Weg ist die **Gemini API** — dieselben Modelle, die auch hinter Flow
laufen, nur mit einer Schnittstelle, die für genau diesen Zweck gedacht ist. Du
brauchst kein Flow-Abo, sondern einen API-Key, und zahlst pro generierter Sekunde
statt pro Monat.

## Backends: Omni oder Veo

Einstellbar in `config.toml` unter `backend`.

### `omni` — Gemini Omni Flash (Standard)

Seit 30. Juni 2026 in der API (`gemini-omni-flash-preview`). Der entscheidende
Unterschied liegt in der **Interactions API**: Jeder Shot kann per
`previous_interaction_id` auf den vorherigen aufbauen. Das Modell behält dabei
Szene, Licht, Kamera und Motiv im Kopf, statt jeden Clip bei null zu beginnen.

Genau das ist die grösste Schwäche von reiner Clip-für-Clip-Generierung, und
deshalb ist Omni hier der Standard. Eingeschaltet über `chain_shots = true`.

Grenzen: **nur 720p**, Clips zwischen **3 und 10 Sekunden**. Ausgaben tragen
SynthID-Wasserzeichen.

### `veo` — Veo 3.1

Kein Chaining, jeder Clip entsteht isoliert. Dafür 1080p und 4K möglich, und mit
der Lite-Variante deutlich billiger. Sinnvoll, wenn du einzelne starke Shots
brauchst statt einer durchgehenden Szene, oder wenn du in 1080p ausspielen willst.

Modelle: `veo-3.1-lite-generate-preview` ($0.05/s), `veo-3.1-fast-generate-preview`
($0.10/s), `veo-3.1-generate-preview` ($0.40/s).

---

## Einrichtung (einmalig, ca. 10 Minuten)

**1. Python 3.11 oder neuer** — prüfen mit `python3 --version`

**2. ffmpeg installieren** (schneidet die Clips zusammen)

```bash
# macOS
brew install ffmpeg
# Windows
winget install ffmpeg
# Linux
sudo apt install ffmpeg
```

**3. Abhängigkeit installieren**

```bash
cd povflow
pip install -r requirements.txt
```

**4. API-Key eintragen**

Key holen auf https://aistudio.google.com/apikey — dann:

```bash
cp .env.example .env
```

und den Key in die `.env` schreiben. Die Datei ist per `.gitignore` ausgeschlossen
und landet nie im Repository.

---

## Benutzung

**Erst mal trocken testen — kostet nichts:**

```bash
python3 -m povflow.cli run --dry-run -n 3
```

Das erzeugt drei komplette Konzepte, Shotlists und Voice-over-Skripte, ohne ein
einziges Video zu generieren und ohne einen Cent auszugeben. Schau dir die
`shotlist.json` an: Das sind exakt die Prompts, die später an Veo gehen. Wenn die
Prompts gut aussehen, sieht meist auch das Video gut aus.

**Kosten prüfen, bevor du echt startest:**

```bash
python3 -m povflow.cli costs
```

**Echt produzieren:**

```bash
python3 -m povflow.cli run -n 1
```

**Was schon produziert wurde:**

```bash
python3 -m povflow.cli history
```

---

## Kosten

Preise Gemini API, Stand August 2026, pro generierter Sekunde Ausgabe:

| Modell | 720p | 1080p |
|---|---|---|
| Gemini Omni Flash | $0.10 | — |
| Veo 3.1 Lite | $0.05 | $0.08 |
| Veo 3.1 Fast | $0.10 | $0.12 |
| Veo 3.1 Standard | $0.40 | $0.40 |

**Beim Chaining kommt etwas dazu, das im Sekundenpreis nicht steht:** Ein
verketteter Shot schickt den vorherigen Clip als Kontext mit, und der wird als
Video-Input berechnet (5.792 Tokens pro Sekunde, $1.50 pro 1 Mio. Tokens). Das
sind ca. **$0.07 pro verkettetem Shot**. Die Pipeline rechnet das mit ein,
`povflow costs` zeigt es getrennt an.

Mit der Standardeinstellung (Omni, 720p, 5 Shots à 8 Sekunden = 40 Sekunden Video):

- **ca. $4.28 pro Folge** ($4.00 Ausgabe + $0.28 Chaining)
- 1 Folge pro Tag ≈ **$130 im Monat**
- Ohne Chaining: $4.00 pro Folge, aber schlechtere Kontinuität
- Mit Veo Lite statt Omni: $2.00 pro Folge, kein Chaining möglich

Zwei harte Bremsen sind eingebaut, beide in der `config.toml`:

- `max_usd_per_run` — bricht ab, bevor ein einzelner Durchlauf zu teuer wird
- `max_usd_per_month` — zählt über alle Läufe mit und stoppt am Monatslimit

Die Ausgaben werden nach jedem erfolgreichen Clip sofort protokolliert. Wenn die
Pipeline mittendrin abstürzt, ist das bereits ausgegebene Geld trotzdem korrekt
verbucht. Google berechnet nur erfolgreich generierte Videos.

**Rechne das gegen deine Einnahmen.** Bei 1.000–1.500 € im Monat aus dem
Pokémon-Account sind $120 vertretbar, aber es ist echtes Geld. Fang mit
`-n 1` an und schau dir das Ergebnis an, bevor du täglich produzierst.

---

## Konfiguration

Alles Wichtige steht in `config.toml`. Die drei Regler, die tatsächlich etwas
verändern:

**`concept_brief`** — mit Abstand der wichtigste. Das ist die Beschreibung deines
Kanals, die in jeden Ideen-Prompt fließt. Je konkreter, desto besser die Ideen.
Schreib rein, was die Serie ausmacht, und vor allem, was sie *nicht* sein soll.

**`style_preset`** — bestimmt die Bildwelt: `fantasy`, `wildlife`, `urban`,
`survival`. Die Handy-Optik bleibt in allen Presets identisch, nur die Welt ändert
sich.

**`shots_per_episode` und `seconds_per_shot`** — steuern Länge und Preis direkt.
5 × 8 s = 40 s ist ein guter Startwert für TikTok. Bei Omni sind 3–10 s pro Shot
erlaubt; längere Shots bedeuten weniger Kettenglieder und damit weniger Drift.

Der Look selbst steckt in `povflow/style.py`. Da ist die "Style-DNA" definiert,
die in jeden einzelnen Shot-Prompt eingebaut wird: Handkamera, Autofokus-Suchen,
Rolling-Shutter, überbelichtete Lichter, kein Color Grading. Der Negativ-Prompt
schließt gezielt aus, was Veo sonst von allein macht — Stativ, Gimbal, Drohne,
Kino-Grading — und vor allem **jede Art von Sprache**, damit nichts gegen dein
Voice-over läuft.

---

## Vollautomatik

Wenn du täglich eine Folge willst, ohne selbst etwas zu starten:

**macOS/Linux** (`crontab -e`), jeden Tag um 6 Uhr früh:

```
0 6 * * * cd /pfad/zu/povflow && /usr/bin/python3 -m povflow.cli run -n 1 >> run.log 2>&1
```

**Windows**: Aufgabenplanung → Neue Aufgabe → Programm `python`, Argumente
`-m povflow.cli run -n 1`, Startordner auf den `povflow`-Ordner setzen.

Morgens liegt dann eine fertige Folge im `output/`-Ordner. Du öffnest die
`voiceover.txt`, sprichst drüber, fertig.

---

## Was das Tool nicht macht

Ehrlich, damit du nicht enttäuscht bist:

- **Es lädt nichts hoch.** Bewusst so. Automatisiertes Posten über inoffizielle
  APIs ist der schnellste Weg zu einem gesperrten TikTok-Account. Der letzte
  Schritt bleibt manuell.
- **Es nimmt kein Voice-over auf.** Das ist dein Teil.
- **Nicht jede Folge wird gut.** Rechne mit einer brauchbaren Folge aus zwei bis
  drei. Deshalb der Dry-Run: Konzepte aussortieren ist gratis, Videos generieren
  nicht.
- **Kontinuität ist besser, aber nicht gelöst.** Mit `chain_shots = true` hält
  Omni die Szene über die Shots hinweg. Perfekt ist das nicht — Details können
  weiter driften, je länger die Kette wird. Bei Handy-Optik fällt das deutlich
  weniger auf als bei Kino-Look, was einer der Gründe ist, warum dieser Stil für
  KI-Video gut funktioniert. Wenn eine Folge auseinanderfällt, hilft es meist,
  `shots_per_episode` zu senken und `seconds_per_shot` auf 10 zu erhöhen: weniger
  Kettenglieder, weniger Drift.
- **Es prüft keine Plattformregeln.** KI-Inhalte müssen auf TikTok, Instagram und
  YouTube als solche gekennzeichnet werden. Das ist deine Verantwortung, und es
  ist auch in deinem Interesse: Nicht gekennzeichneter KI-Content wird von den
  Plattformen zunehmend in der Reichweite gedrosselt. Omni-Ausgaben tragen
  ohnehin ein SynthID-Wasserzeichen, die Plattformen erkennen es also so oder so.

---

## Wenn etwas nicht funktioniert

**`GEMINI_API_KEY is not set`** — `.env` fehlt oder der Key steht nicht drin.

**`Gemini Omni Flash only outputs 720p`** — `resolution` in der `config.toml` auf
`"720p"` setzen, oder auf `backend = "veo"` wechseln.

**Folge fällt szenisch auseinander** — `shots_per_episode` runter,
`seconds_per_shot` auf 10 hoch. Kürzere Kette, weniger Drift.

**`ffmpeg and ffprobe are required`** — ffmpeg fehlt. Die Clips sind trotzdem
generiert und liegen in `shots/`; du kannst sie von Hand zusammenschneiden.

**Video kommt quer statt hochkant** — passiert, Veo ignoriert `aspect_ratio`
gelegentlich. Die Pipeline misst jeden Clip nach und schneidet ihn automatisch
mittig auf 9:16 zu. In der Ausgabe steht dann `got 1280x720, cropping to 720x1280`.

**`would break the monthly cap`** — Monatslimit erreicht. In `config.toml` unter
`max_usd_per_month` anheben, wenn das gewollt ist.

---

## Tests

```bash
python3 -m unittest discover -s tests -v
```

47 Tests, decken Konfiguration und Backend-Limits, Kostenlogik inklusive
Chaining-Aufschlag, Omni-Request-Aufbau, Ideen-Parsing, Dedup, Prompt-Aufbau,
ffmpeg-Kommandos und Voice-over-Timing ab.
