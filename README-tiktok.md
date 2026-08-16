# Vollautomatische TikTok-Produktion

Idee → Skript → Clips (Higgsfield/Seedance, per `extend` aneinandergehängt) →
Voiceover in der Stimme *Silver* → Schnitt → fertiges 9:16-Video.

Was übrig bleibt: **Musik drüberlegen und posten.** Alles davor läuft allein,
im Dauerbetrieb, solange Kontingent da ist.

```bash
pip install -r requirements.txt
cp .env.example .env          # Keys eintragen
python -m tiktok channels     # welche Kanäle gibt es
python -m tiktok idea -c silver-wildlife    # nur eine Idee (fast kostenlos, zum Testen)
python -m tiktok once -c silver-wildlife    # ein komplettes Video
python -m tiktok loop -c silver-wildlife -c silver-influencer   # 24/7
```

---

## Wie ein Video entsteht

| Schritt | Was passiert | Datei |
|---|---|---|
| 1. Idee | Claude erfindet Thema, Subjekt, Hook, ersten Satz — geprüft gegen alles, was der Kanal schon hatte | `creative.py` |
| 2. Skript | Ein Beat pro Clip, mit Voiceover-Text im passenden Wortbudget und englischem Bild-Prompt | `creative.py` |
| 3. Clips | Clip 1 neu, Clip 2–n als `extend` vom jeweils vorherigen — immer nur eine Generierung gleichzeitig, mit Warten bis fertig | `providers/` |
| 4. Stimme | Pro Clip ein Voiceover-File in der Stimme Silver | `voice.py` |
| 5. Schnitt | Normalisieren auf 1080×1920, aneinanderhängen, Ton mischen, optional Untertitel | `assemble.py` |
| 6. Ausgabe | `final.mp4` plus `post.md` mit Caption, Hashtags und Sprechtext | `pipeline.py` |

Alles landet in einem Ordner pro Video:

```
output/silver-wildlife/2026-08-16-jagd-des-wanderfalken-a1b2c3/
    state.json      Stand der Produktion (Grundlage für resume)
    script.json     das komplette Skript
    clip_01.mp4 …   die einzelnen Clips
    voice_01.mp3 …  Voiceover je Clip
    final.mp4       das fertige Video
    post.md         Caption, Hashtags, Sprechtext
```

Bricht etwas ab — Timeout, Kontingent leer, Rechner aus —, macht

```bash
python -m tiktok resume output/silver-wildlife/2026-08-16-…
```

genau dort weiter. Fertige Clips werden **nicht** neu generiert.

---

## Die TikTok-Strategie steckt im Code, nicht im Prompt-Bauchgefühl

`creative.py` erzwingt die Struktur, die die Retention-Kurve belohnt:

- **0–3 s Hook** — stärkstes Bild sofort, erster Satz ist eine offene Schleife.
  Begrüßungen und Moderationssätze („Hallo Leute", „In diesem Video…") werden
  vom Validator **abgelehnt**, das Skript muss neu geschrieben werden.
- **Alle 10 s ein neuer visueller Reiz** — fällt hier mit der Clipgrenze zusammen.
  Zwei Clips mit derselben Kameraeinstellung werden abgelehnt.
- **Re-Hook bei ~50 %** — genau da, wo die Leute sonst abspringen, kommt die
  Wendung. Die Rolle wird automatisch auf den mittleren Clip gelegt.
- **Loop-Back am Ende** — der letzte Satz dockt an den ersten an, damit ein
  Rewatch nahtlos wirkt. CTAs im Voiceover („abonniert", „folgt mir") werden
  abgelehnt, weil sie Watchtime kosten.
- **Wortbudget je Clip** — `Sekunden × Sprechgeschwindigkeit`. Zu lang heißt:
  das Voiceover läuft über den Bildwechsel hinaus. Zu kurz heißt: tote Sekunden.

Verstößt ein Entwurf dagegen, geht er mit der konkreten Fehlerliste zurück an
Claude — bis zu dreimal, dann bricht der Job ab statt schlechten Content zu
produzieren.

## Nichts wiederholt sich

`memory/used.json` merkt sich pro Kanal jedes Thema, Subjekt, jeden Hook, Stil
und Eröffnungssatz. Vor jeder neuen Idee geht diese Liste als Negativliste in
den Prompt, und die fertige Idee wird noch einmal gegengeprüft — nicht nur auf
exakte Gleichheit, sondern auf Wortähnlichkeit (Jaccard ≥ 0,55). „Wie
Wanderfalken im Sturzflug jagen" und „Wie Wanderfalken jagen im Sturzflug"
gelten als dasselbe Video. Bei Ablehnung bekommt Claude den Grund zu lesen und
muss ein anderes Subjekt **und** einen anderen Erzählwinkel nehmen.

`memory/videos.jsonl` ist das Langzeit-Log: jedes produzierte Video mit allen
Parametern.

---

## Kanäle

Ein Kanal ist eine JSON-Datei in `channels/`. Mitgeliefert:

- **`silver-wildlife`** — die Tierdoku im Kinolook.
- **`silver-influencer`** — der POV-Account.

Wichtige Felder:

| Feld | Wirkung |
|---|---|
| `bible` | Was der Kanal ist und was er dem Zuschauer verspricht. Geht in jeden Prompt. |
| `visual_style` | Wird an **jeden** Clip-Prompt angehängt → Wiedererkennungswert über alle Videos. |
| `domains` / `angles` | Der Korridor, aus dem Ideen kommen. Je breiter, desto länger dauert es, bis sich etwas wiederholt. |
| `target_seconds` / `clip_seconds` | 40 s / 10 s = 4 Clips. Auf 60 gestellt sind es 6. |
| `words_per_second` | Wortbudget je Clip (Deutsch ≈ 2,4). |
| `voice.voice_id` | Die ElevenLabs-Stimme Silver. **Muss eingetragen werden**, sonst läuft das Video ohne Voiceover durch. |

Neuer Kanal = Datei kopieren, Bibel und Korridor umschreiben, fertig.

---

## Die drei Wege zu den Clips

`VIDEO_PROVIDER` in der `.env`:

**`higgsfield`** — HTTP-API mit Key. Voll automatisch. Endpunkte, Feldnamen und
Statuswerte stehen in `tiktok/providers/higgsfield.schema.json`, damit eine
geänderte API-Signatur ohne Codeänderung nachgezogen werden kann. **Diese Datei
gegen die aktuelle Higgsfield-Doku prüfen, bevor du sie benutzt** — die Werte
darin sind eine plausible Vorlage, keine verifizierte Signatur.

**`higgsfield_cli`** — die offizielle Higgsfield-CLI lokal. Der sauberste Weg,
wenn du sie hast: kein API-Nachbau, Authentifizierung bleibt beim offiziellen
Tool. Die Kommandozeilen sind als Vorlage konfigurierbar
(`HIGGSFIELD_CLI_GENERATE`, `HIGGSFIELD_CLI_EXTEND`).

**`assisted`** — der Standard, wenn du nur den Weboberflächen-Zugang hast. Die
Pipeline schreibt den fertigen Prompt in den Job-Ordner (copy-paste-fertig, mit
allen Einstellungen), wartet, bis die Datei `clip_03.mp4` dort liegt, und läuft
dann automatisch weiter. Aus 20 Minuten Handarbeit pro Video werden ein paar
Klicks — Idee, Skript, Prompts, Voiceover, Schnitt und Ausgabe passieren weiter
von allein.

### Zur Bot-Erkennung

Eine Browser-Automatisierung, die die Higgsfield-Oberfläche fernsteuert und dabei
die Bot-Erkennung umgeht, ist hier bewusst **nicht** gebaut. Das verstößt gegen
die Nutzungsbedingungen und ist genau das, was zur Sperre des Accounts führt —
mit einem Unlimited-Plan ist das ein teurer Totalverlust. Die drei Wege oben sind
die belastbaren Alternativen: offizielle API, offizielle CLI, oder der
Assisted-Modus, bei dem die Generierung ein Mensch auslöst und der Rest
automatisch läuft.

---

## Kosten

Zwei Modellstufen: `MODEL_CREATIVE` (Ideen und Skripte — da zählt Qualität) und
`MODEL_UTILITY` (Kleinkram). Der eigentliche Hebel ist aber `LLM_BACKEND`:

- **`cli`** — Aufrufe laufen über die Claude Code CLI und damit über dein
  Abo-Kontingent. Keine Zusatzkosten. Ist das Kontingent leer, meldet die CLI
  das, der Runner **wartet** (15 → 30 → 60 min) statt abzubrechen und macht
  weiter, sobald wieder Kontingent da ist.
- **`api`** — pro Token abgerechnet, dafür ohne Kontingentgrenze. Der
  Kanal-Kontext wird gecacht, das drückt die Kosten deutlich.
  `MAX_USD_PER_RUN` ist die Notbremse.

Pro Video sind es zwei große Aufrufe (Idee, Skript). Der Löwenanteil der Kosten
entsteht ohnehin bei der Videogenerierung, nicht beim Text.

## Dauerbetrieb

```bash
python -m tiktok loop -c silver-wildlife -c silver-influencer
```

Kanäle werden reihum bedient. Der Runner beendet sich sauber bei
`MAX_VIDEOS_PER_RUN`, `MAX_USD_PER_RUN` oder wenn die Datei `output/STOP`
existiert (`touch output/STOP` heißt: nach diesem Video ist Schluss). Fehler bei
einem Video kosten das Video, nicht den Lauf — der Runner protokolliert und
macht mit dem nächsten weiter.

## Voraussetzungen

- Python 3.11+
- **ffmpeg** und **ffprobe** im `PATH` (der Schnitt)
- Claude Code CLI *oder* `ANTHROPIC_API_KEY`
- ElevenLabs-Key + `voice_id` für das Voiceover (optional, ohne läuft es stumm)

```bash
pytest    # 62 Tests, ohne Netz und ohne ffmpeg lauffähig
```
