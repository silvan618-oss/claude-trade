# povflow

Erzeugt vollautomatisch vertikale Shorts, die aussehen wie mit dem Handy aus der
Ich-Perspektive gefilmt — inklusive eigener Ideen, Shotlist und fertigem
Voice-over-Skript mit Timecodes. Du sprichst nur noch drüber.

Ein Durchlauf liefert pro Folge:

```
output/2026-08-05_der-hafen/
  prompts.md          <- Prompts zum Reinkopieren in Flow, Shot fuer Shot
  voiceover.txt       <- dein Skript, mit Timecodes pro Shot
  voiceover.srt       <- dasselbe als Untertitelspur fuer den Editor
  concept.json        <- die Idee
  shotlist.json       <- dieselben Prompts maschinenlesbar
  shots/              <- hier kommen die Clips rein
  final_silent.mp4    <- entsteht beim Zusammenfuegen
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

## Der wichtigste Punkt: Credits ≠ API

**Abo-Credits und API-Abrechnung sind zwei getrennte Systeme.** Die Credits aus
deinem Google-AI-Abo funktionieren in Flow, in der Gemini-App und in Whisk. Sie
geben **keinen API-Zugang**. Wer über die API generiert, zahlt Pay-per-Use, egal
wie viele Credits im Abo noch liegen.

Der Unterschied ist erheblich:

| | Pro Sekunde | 40s-Folge | 30 Folgen/Monat |
|---|---|---|---|
| **Flow mit Credits** (2500 für 27,99 €) | ~0,017 € | **0,67 €** | **20 €** |
| **Gemini API** (Omni Flash, 0,10 $/s) | ~0,093 € | 3,70 € | 119 € |

Das ist Faktor **5,5**. 2500 Credits decken etwa **41 Folgen à 40 Sekunden** pro
Monat ab — gut eine pro Tag.

Deshalb ist der Standard hier nicht Vollautomatik, sondern der Hybrid-Modus.

**Wichtig für die Einstellungen:** Flow rechnet **pro Generierung** ab, nicht pro
Sekunde — 15 Credits pro Clip von bis zu 10 Sekunden. Ein 8-Sekunden-Shot kostet
also exakt dasselbe wie ein 10-Sekunden-Shot. Deshalb steht die Standardkonfiguration
auf `seconds_per_shot = 10`: gleiche Kosten, 25 % mehr Video. `povflow costs`
warnt dich, wenn du Sekunden verschenkst.

## Die drei Backends

Einstellbar in `config.toml` unter `backend`.

### `manual` — Hybrid (Standard, empfohlen)

Das Tool macht alles ausser der Clip-Generierung: Ideen, Prompts, Schnitt,
Voice-over-Skript. Du generierst die Clips selbst in Flow mit deinen Credits.

Der Ablauf pro Folge dauert ein paar Minuten:

1. `povflow run -n 1` → erzeugt Ordner mit `prompts.md`
2. Prompts aus `prompts.md` in Flow kopieren, Clips generieren
3. Clips als `shot_01.mp4`, `shot_02.mp4` … in den `shots/`-Unterordner
4. `povflow assemble <ordner>` → fertiger stummer Schnitt
5. Voice-over nach `voiceover.txt` einsprechen

Du behältst die Credit-Preise und verlierst nur den letzten Automatikschritt.
Ideenfindung, Prompt-Handwerk, Schnitt und Skript — der zeitaufwendige Teil —
laufen weiterhin automatisch.

**In Flow wichtig:** Für Shot 2 und später nicht neu generieren, sondern die
Szene erweitern. Ein frischer Prompt startet eine neue Welt, und die Folge fällt
auseinander. Die `prompts.md` weist bei jedem Shot darauf hin.

### `omni` — Gemini Omni Flash über die API

Vollautomatisch, aber zu API-Preisen. Der technische Vorteil liegt in der
**Interactions API**: Jeder Shot baut per `previous_interaction_id` auf dem
vorherigen auf, das Modell behält Szene, Licht und Motiv im Kopf. Das ist
zuverlässiger als manuelles Erweitern in Flow.

Grenzen: nur 720p, Clips zwischen 3 und 10 Sekunden. Ausgaben tragen
SynthID-Wasserzeichen.

Sinnvoll, wenn dir die Zeitersparnis die ~8-fachen Kosten wert ist, oder wenn du
so viel produzierst, dass 2500 Credits nicht reichen.

### `veo` — Veo 3.1 über die API

Kein Chaining, jeder Clip entsteht isoliert. Dafür 1080p und 4K möglich, und mit
der Lite-Variante die billigste API-Option ($0.05/s).

Modelle: `veo-3.1-lite-generate-preview`, `veo-3.1-fast-generate-preview`,
`veo-3.1-generate-preview`.

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

**Auch im Hybrid-Modus brauchst du diesen Key** — aber nur, damit das Tool die
Episoden-Ideen schreiben kann. Das ist eine reine Textanfrage für Bruchteile
eines Cents, die der Gratis-Kontingent von AI Studio normalerweise abdeckt. Es
läuft **kein Video** über die API, deine Flow-Credits bleiben unberührt.

---

## Benutzung

**Erst mal trocken testen — kostet nichts:**

```bash
python3 -m povflow.cli run --dry-run -n 3
```

Das erzeugt drei komplette Konzepte, Shotlists und Voice-over-Skripte, ohne ein
einziges Video zu generieren. Schau dir die `prompts.md` an: Das sind exakt die
Prompts, die du später in Flow einsetzt. Wenn die Prompts gut aussehen, sieht
meist auch das Video gut aus — und Konzepte aussortieren ist gratis, Clips
generieren kostet Credits.

**Kosten prüfen, bevor du echt startest:**

```bash
python3 -m povflow.cli costs
```

**Echt produzieren:**

```bash
python3 -m povflow.cli run -n 1
```

Im Hybrid-Modus legt das den Ordner mit `prompts.md` an. Nachdem du die Clips in
Flow generiert und in `shots/` abgelegt hast:

```bash
python3 -m povflow.cli assemble output/2026-08-05_der-hafen
```

Das sucht alle Videodateien in `shots/`, sortiert sie nach Namen, schneidet sie
auf 9:16 zu und fügt sie zusammen. Andere Dateien im Ordner werden ignoriert.

**Was schon produziert wurde:**

```bash
python3 -m povflow.cli history
```

---

## Kosten

`povflow costs` rechnet dir das für deine aktuelle Konfiguration aus — im
Hybrid-Modus in Credits, bei den API-Backends in Dollar.

**Hybrid-Modus (Credits):** 15 Credits pro Clip bis 10 Sekunden. Eine Folge aus
4 Shots kostet also 60 Credits ≈ 0,67 €, und deine 2500 Credits reichen für ~41
Folgen im Monat. Trag dein Abo unter `[costs.credits]` in der `config.toml` ein,
dann stimmt die Anzeige. Falls dein Plan doch pro Sekunde abrechnet:
`credits_per_clip = 0` setzen und `credits_per_second` eintragen.

**API-Backends**, Preise Gemini API Stand August 2026, pro Sekunde Ausgabe:

| Modell | 720p | 1080p |
|---|---|---|
| Gemini Omni Flash | $0.10 | — |
| Veo 3.1 Lite | $0.05 | $0.08 |
| Veo 3.1 Fast | $0.10 | $0.12 |
| Veo 3.1 Standard | $0.40 | $0.40 |

**Beim Omni-Chaining kommt etwas dazu, das im Sekundenpreis nicht steht:** Ein
verketteter Shot schickt den vorherigen Clip als Kontext mit, und der wird als
Video-Input berechnet (5.792 Tokens pro Sekunde, $1.50 pro 1 Mio. Tokens). Das
sind ca. **$0.07 pro verkettetem Shot**, bei 5 Shots also $0.28 pro Folge. Die
Pipeline rechnet das mit ein und zeigt es getrennt an.

Zwei harte Bremsen greifen bei den API-Backends, beide in der `config.toml`:
`max_usd_per_run` und `max_usd_per_month`. Die Ausgaben werden nach jedem
erfolgreichen Clip sofort protokolliert, ein Absturz mitten im Lauf verliert
also keine bereits ausgegebenen Beträge.

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
4 × 10 s = 40 s ist der Startwert für TikTok. `seconds_per_shot` solltest du im
Hybrid-Modus auf 10 lassen: Kürzere Shots kosten dieselben 15 Credits, bringen
aber weniger Video. Willst du längere Folgen, erhöhe `shots_per_episode` — jeder
zusätzliche Shot kostet 15 Credits und bringt 10 Sekunden.

Der Look selbst steckt in `povflow/style.py`. Da ist die "Style-DNA" definiert,
die in jeden einzelnen Shot-Prompt eingebaut wird: Handkamera, Autofokus-Suchen,
Rolling-Shutter, überbelichtete Lichter, kein Color Grading. Der Negativ-Prompt
schließt gezielt aus, was Veo sonst von allein macht — Stativ, Gimbal, Drohne,
Kino-Grading — und vor allem **jede Art von Sprache**, damit nichts gegen dein
Voice-over läuft.

---

## Automatisch planen lassen

Im Hybrid-Modus kann der Planungsteil trotzdem nachts laufen: Morgens liegt eine
fertige `prompts.md` bereit, du generierst die Clips in Flow und lässt
`assemble` drüberlaufen. Bei den API-Backends entsteht dabei direkt das fertige
Video.

**macOS/Linux** (`crontab -e`), jeden Tag um 6 Uhr früh:

```
0 6 * * * cd /pfad/zu/povflow && /usr/bin/python3 -m povflow.cli run -n 1 >> run.log 2>&1
```

**Windows**: Aufgabenplanung → Neue Aufgabe → Programm `python`, Argumente
`-m povflow.cli run -n 1`, Startordner auf den `povflow`-Ordner setzen.

Morgens liegt dann ein fertig geplanter Ordner in `output/`.

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
- **Im Hybrid-Modus generiert es keine Clips.** Das ist der Preis für die
  Credit-Preise: Flow hat keine API, also bleibt dieser Schritt bei dir.
- **Kontinuität ist besser, aber nicht gelöst.** In Flow hängt sie daran, dass du
  die Szene erweiterst statt neu zu generieren; über das Omni-Backend erledigt
  das `chain_shots`. Perfekt ist beides nicht — Details driften, je länger die
  Kette wird. Bei Handy-Optik fällt das deutlich weniger auf als bei Kino-Look,
  was einer der Gründe ist, warum dieser Stil für KI-Video gut funktioniert. Wenn
  eine Folge auseinanderfällt: `shots_per_episode` senken und `seconds_per_shot`
  erhöhen. Weniger Kettenglieder, weniger Drift.
- **Es prüft keine Plattformregeln.** KI-Inhalte müssen auf TikTok, Instagram und
  YouTube als solche gekennzeichnet werden. Das ist deine Verantwortung, und es
  ist auch in deinem Interesse: Nicht gekennzeichneter KI-Content wird von den
  Plattformen zunehmend in der Reichweite gedrosselt. Omni-Ausgaben tragen
  ohnehin ein SynthID-Wasserzeichen, die Plattformen erkennen es also so oder so.

---

## Wenn etwas nicht funktioniert

**`GEMINI_API_KEY is not set`** — `.env` fehlt oder der Key steht nicht drin. Wird
auch im Hybrid-Modus gebraucht, aber nur für die Ideen (reiner Text, praktisch
gratis). Zum Ausprobieren ohne Key: `--dry-run`.

**`No clips found in .../shots`** — die Clips liegen nicht im `shots/`-Unterordner
oder haben eine ungewöhnliche Endung. Erkannt werden `.mp4`, `.mov`, `.webm`,
`.m4v`. Die Reihenfolge ergibt sich aus dem Dateinamen, deshalb `shot_01`,
`shot_02` mit führender Null.

**`Gemini Omni Flash only outputs 720p`** — `resolution` in der `config.toml` auf
`"720p"` setzen, oder auf `backend = "veo"` wechseln. Im Hybrid-Modus gilt die
Grenze nicht: dort trägst du ein, was aus Flow rauskommt.

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

61 Tests, decken Konfiguration und Backend-Limits, Credit-Abrechnung pro Clip und
pro Sekunde, Dollar-Kostenlogik inklusive Chaining-Aufschlag, Omni-Request-Aufbau,
das Hand-off-Blatt, Clip-Erkennung beim Zusammenfügen, Ideen-Parsing, Dedup,
Prompt-Aufbau, ffmpeg-Kommandos und Voice-over-Timing ab. Die mitgelieferte
`config.toml` wird mitgetestet, damit die dokumentierten Kosten stimmen.
