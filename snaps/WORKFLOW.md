# Arbeitsweise (Stand Batch 01)

Wenn der Nutzer sagt „ich brauch wieder neue Videos": **9 neue Clips für Wizarding World + 9 für Pokémon**,
als Artefakt-Seite wie `prompts/batch-01.html` (Vorlage: `prompts/batch-01.py`, gleiche Templates).

Regeln für jeden Clip:
- **Bild-Prompt** (Nano Banana 2, 9:16): beginnt mit „Use the attached reference snaps as the style template …",
  Snap-Look (unscharf, verrauscht, JPEG), Caption-Balken im Bild, Figuren als **@Name** (Theo, Maja, Lena, Nova,
  Finn, Ollie, Cara / Jonas, Emma, Lukas, Mira, Sam, Yuna). Keine Schauspielergesichter im Startframe.
- **Video-Prompt** (Omni Flash 1.1, 10 s, Startframe = Bild): Aufbau des funktionierenden Butterbier-Videos,
  Kameramann stumm, Dialog auf Deutsch, Leute interagieren miteinander, Caption-Balken bleibt als Overlay,
  kein „keep static / no zoom / subtle only".
- Originalfiguren (Snape, McGonagall, Hagrid …) nur beschrieben, nie beim Namen, und erst im Video ins Bild.
- Running Gags aus `CHARACTERS.md` weiterführen.

Der Nutzer hängt die Referenz-Snaps (Stil) und die Figuren-Referenzbilder in der ersten Flow-Nachricht an.
Die Seite hat pro Welt einen „Alles kopieren"-Knopf mit Anleitung (Schritt 1 Startframes, Schritt 2 Videos).
