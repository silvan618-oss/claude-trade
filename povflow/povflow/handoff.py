"""The manual-backend hand-off sheet.

Subscription credits work in Flow but grant no API access, so the cheap path
keeps a human in the generation step. This renders everything that human needs:
the prompts to paste, where to save each clip, and what it costs in credits.

Written in German because it is the file the creator opens every day.
"""

from __future__ import annotations

from .config import Config
from .ideas import Concept
from .shotlist import ShotPrompt


def render_handoff(concept: Concept, shots: list[ShotPrompt], cfg: Config) -> str:
    total_seconds = sum(s.seconds for s in shots)
    credits = (
        cfg.credits_per_clip * len(shots) if cfg.credits_per_clip
        else cfg.credits_per_second * total_seconds
    )
    eur = credits * cfg.eur_per_credit

    out: list[str] = [
        f"# {concept.title}",
        "",
        f"**Logline:** {concept.logline}",
        "",
        f"**Laenge:** {len(shots)} Shots x {shots[0].seconds}s = {int(total_seconds)}s",
        f"**Kosten:** ca. {credits:.0f} Credits (~{eur:.2f} EUR)",
        "",
        "---",
        "",
        "## So gehst du vor",
        "",
        "1. Shots mit **NEUE SZENE** normal generieren (Prompt kopieren).",
        "2. Shots mit **FORTSETZUNG** nicht frisch prompten, sondern an den",
        "   vorherigen Clip anschliessen. Wie das in Flow geht, haengt vom Modell ab:",
        "",
        "   - **Omni:** im selben Chat weiterarbeiten und beschreiben, was als",
        "     Naechstes passiert. Omni behaelt Szene, Licht und Motiv im Kontext.",
        "     Alternativ den vorherigen Clip als Referenz anhaengen.",
        "   - **Veo:** der `+`-Knopf rechts an der Szene, dann `Extend` (setzt",
        "     denselben Shot fort) oder `Jump to` (neuer Shot, Kontext bleibt).",
        "     Laut Google-Doku funktioniert `Extend` **nur mit Veo-Clips**.",
        "",
        "   Falls dein Flow keine dieser Optionen anbietet: Prompt normal nutzen,",
        "   aber vorher einen Standbild-Export des letzten Frames als Referenz",
        "   anhaengen. Ein voellig frischer Prompt startet sonst eine neue Welt.",
        "",
        "3. Jeden Clip herunterladen und exakt so benennen wie unten angegeben,",
        "   in den Unterordner `shots/`.",
        "4. Danach im Projektordner:",
        "",
        "   ```",
        "   python3 -m povflow.cli assemble <dieser-ordner>",
        "   ```",
        "",
        "   Das schneidet alles zusammen und legt `final_silent.mp4` an.",
        "5. Voice-over nach `voiceover.txt` einsprechen. Timecodes stehen drin.",
        "",
        "---",
        "",
        f"## Frame 1 — das Wichtigste",
        "",
        f"{concept.hook_visual or '(kein Hook-Visual im Konzept)'}",
        "",
        "Wenn der erste Frame das nicht zeigt, nochmal generieren. Der Rest des",
        "Videos ist egal, wenn Sekunde 1 nicht haelt.",
        "",
        "---",
        "",
    ]

    for shot in shots:
        if shot.starts_new_chain:
            label = f"Shot {shot.index} — NEUE SZENE"
            note = (
                "Frisch generieren. Hier darf geschnitten werden."
                if shot.index > 1 else "Frisch generieren."
            )
        else:
            label = f"Shot {shot.index} — FORTSETZUNG von Shot {shot.index - 1}"
            note = "Nicht neu prompten, an den vorherigen Clip anschliessen."
        out += [
            f"## {label}",
            "",
            note,
            "",
            f"Speichern als: `shots/shot_{shot.index:02d}.mp4`",
            "",
            "```",
            shot.prompt,
            "```",
            "",
            "Nicht enthalten:",
            "",
            "```",
            shot.negative_prompt,
            "```",
            "",
        ]

    if concept.caption or concept.hashtags:
        out += ["---", "", "## Beim Posten", ""]
        if concept.caption:
            out += [f"**Caption:** {concept.caption}", ""]
        if concept.hashtags:
            out += ["**Hashtags:** " + " ".join(concept.hashtags), ""]
        out += [
            "**Nicht vergessen:** KI-Kennzeichnung setzen. Die Plattformen erkennen",
            "SynthID ohnehin, und nicht gekennzeichneter KI-Content wird gedrosselt.",
            "",
        ]

    return "\n".join(out)
