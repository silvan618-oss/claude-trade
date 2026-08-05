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
        "1. Shot 1 in Flow generieren (Prompt unten kopieren).",
        "2. **Fuer Shot 2 bis "
        f"{len(shots)}: nicht neu generieren.** In Flow die Szene erweitern",
        "   bzw. den vorherigen Clip als Ausgangspunkt nehmen. Nur so bleiben",
        "   Ort, Licht und Motiv gleich. Ein frischer Prompt startet eine neue Welt.",
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
        label = "Shot 1 — neu generieren" if shot.index == 1 else (
            f"Shot {shot.index} — Szene aus Shot {shot.index - 1} erweitern"
        )
        out += [
            f"## {label}",
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
