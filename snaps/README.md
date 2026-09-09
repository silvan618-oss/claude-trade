# snaps — Wizarding-School-Snaps reproduzieren

Ziel: die fünf Referenz-Snaps (`reference/`) exakt nachbauen — Foto-Look eines 2015er iPhones,
der Snapchat-Beschriftungsbalken und die Snapchat-Wiedergabe (harte Schnitte, kein UI).

```
snaps.json     Prompts, Captions, Balkenposition, Look- und Animations-Parameter (alles einstellbar)
generate.py    Prompts für Google Flow exportieren (--export) oder per API generieren  ->  raw/<id>.png
import_raw.py  Flow-Downloads den Snaps zuordnen             ->  raw/<id>.png
flow/          fertige Prompts zum Kopieren (PROMPTS.md, <id>.txt)
snapify.py     iPhone-Look + Caption-Balken                   ->  out/<id>.jpg
animate.py     Wiedergabe wie in Snapchat                     ->  out/story.mp4 + out/story.html
reference/     die Original-Snaps als Messvorlage
fonts/         Nimbus Sans (freier Helvetica-Klon, URW base35 / AGPL mit Font-Ausnahme)
```

## Ablauf mit Google Flow (Nano Banana 2)

```bash
pip install -r snaps/requirements.txt
cd snaps
python generate.py --export flow          # 1. Prompts -> flow/PROMPTS.md (zum Kopieren in Flow)
#    In Flow: Bilder, Modell "Nano Banana 2", Seitenverhältnis 9:16, je Prompt ein Bild, herunterladen
python import_raw.py <id> <datei>         # 2. Download zuordnen, z. B. import_raw.py 03-delilah ~/Downloads/Flow_....png
python import_raw.py --list               #    zeigt, welche Snaps noch ein Foto brauchen
python snapify.py                         # 3. Look + Caption   -> out/<id>.jpg
python animate.py                         # 4. Story-Video      -> out/story.mp4 + story.html
```

Fünf Downloads auf einmal: `python import_raw.py ~/Downloads/Flow_*.png` ordnet sie nach Downloadzeit
den fünf Snaps in Reihenfolge zu. Flow-Downloads in 2K/4K sind fein; `snapify.py` schneidet auf 9:16
zu und skaliert auf 1080×1920.

Alternativ per API (`generate.py`, Backend `nanobanana` mit `GEMINI_API_KEY`, sonst `gemini`, `openai`,
`bedrock`): `python generate.py 03-delilah --n 4` erzeugt vier Varianten (`raw/03-delilah-2.png` …).
`python snapify.py --calibrate` misst die Balken-Geometrie der eigenen Ausgabe gegen die Referenzen
und legt Vergleichsstreifen in `out/calib-*.png` ab.

## Der Snap-Look (aus den Referenzen vermessen)

Alle Maße sind relativ zur Bildbreite W, damit sie bei jeder Auflösung identisch sind
(Referenz: 1200×2133, Ausgabe: 1080×1920, 9:16).

| Element | gemessen (W=1200) | relativ |
|---|---|---|
| Balkenhöhe, eine Zeile | 106 px | 0.0883·W |
| Zeilenabstand (zweite Zeile) | +59 px | 0.0492·W |
| Schriftgröße (Helvetica-Regular, Kleinbuchstaben) | ≈ 50 px | 0.0417·W |
| Grundlinie der ersten Zeile unter Balkenoberkante | 71 px | 0.0592·W |
| Balkenfarbe | Schwarz, ≈ 62 % Deckkraft | `bar_alpha` 0.62 |
| Text | Reinweiß, exakt horizontal zentriert, greedy Wortumbruch | `side_padding` 0.08·W |
| Balkenposition (Mitte / H) | 0.59 · 0.509 · 0.398 · 0.523 · 0.532 | `caption_y` pro Snap |

Kalibrierstand (`snapify.py --calibrate`): Balkenhöhe 106/106 bzw. 165/165 px, Textzeilen-Pixelreihen
identisch, Textbreite auf ±2 px. Der Foto-Look (`look` in `snaps.json`): leichte Auflösungsreduktion,
Weichzeichnung, Luma-/Chroma-Rauschen, angehobene Schwarzwerte, leichte Vignette, JPEG-Artefakte —
der Balken wird danach scharf darüber gelegt, wie in der App.

## Animation

Snapchat blendet nicht: ein Snap erscheint sofort, bleibt `duration` Sekunden, dann kommt der nächste
(harter Schnitt, kein Chrome). Genau das macht `animate.py` standardmäßig. Optional
(`snaps.json` → `animation` oder Kommandozeile): `--story-ui` (Fortschrittssegmente oben),
`--transition fade`, `--ken-burns 0.03`, `--durations 3,2,2,2.5,4`. `out/story.html` spielt die Snaps
im Browser wie eine Story ab (tippen = weiter, links tippen = zurück, halten = Pause).

## Feinabstimmung

Alles Einstellbare liegt in `snaps.json`: `caption` (Geometrie), `look` (Bildqualität), `caption_y`
je Snap, `scene`/`caption` je Snap, `animation`. Nach jeder Änderung `snapify.py` und `animate.py`
erneut laufen lassen.
