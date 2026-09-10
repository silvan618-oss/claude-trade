# Arbeitsweise (Stand Batch 01)

Wenn der Nutzer sagt „ich brauch wieder neue Videos": **9 neue Clips für Wizarding World + 9 für Pokémon**,
als Artefakt-Seite wie `prompts/batch-01.html` (Vorlage: `prompts/batch-01.py`, gleiche Templates).

**Zwei Schritte, immer:** Schritt 1 liefert nur die Bild-Prompts (Startframes). Der Nutzer schickt die fertigen
Bilder mit Clip-Nummer zurück. Schritt 2: Video-Prompts werden erst dann geschrieben, exakt auf das, was im Bild ist
(Blickrichtung, Haltung, wer wo steht). Video-Prompts vor dem Bild sind nur Entwurf.

Regeln für jeden Clip:
- **Bild-Prompt** (Nano Banana 2, 9:16): beginnt mit „Use the attached reference snaps as the style template …",
  Snap-Look (unscharf, verrauscht, JPEG), Caption-Balken im Bild, Figuren als **@Name** (Theo, Maja, Lena, Nova,
  Finn, Ollie, Cara / Jonas, Emma, Lukas, Mira, Sam, Yuna). Keine Schauspielergesichter im Startframe.
- **Video-Prompt** (Omni Flash 1.1, 10 s, Startframe = Bild): Aufbau des funktionierenden Butterbier-Videos,
  Kameramann stumm, Leute interagieren miteinander. **Sprache: Wizarding World auf Englisch (britischer Akzent), Pokémon auf Deutsch.**, Caption-Balken bleibt als Overlay,
  kein „keep static / no zoom / subtle only".
- **Voiceover-Lücken:** Die Szene wird geplant, als würde der Kamerahalter mitreden. Seine Sätze stehen NICHT im
  Prompt, stattdessen Pausen von 2–3 Sekunden, in denen die anderen in die Kamera schauen und zuhören, und ihre
  Antworten beziehen sich auf das, was er gesagt hätte ("Genau.", "Hast du gehört?"). Gilt für beide Welten.
- Originalfiguren (Snape, McGonagall, Hagrid …) nur beschrieben, nie beim Namen, und erst im Video ins Bild.
- Running Gags aus `CHARACTERS.md` weiterführen.

Der Nutzer hängt die Referenz-Snaps (Stil) und die Figuren-Referenzbilder in der ersten Flow-Nachricht an.
Die Seite hat pro Welt einen „Alles kopieren"-Knopf mit Anleitung (Schritt 1 Startframes, Schritt 2 Videos).
