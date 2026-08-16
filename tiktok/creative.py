"""Die Kreativ-Schicht: Idee -> Skript -> Clip-Prompts.

Hier steckt das eigentliche TikTok-Wissen. Die Struktur ist nicht frei
erfunden, sondern folgt dem, was die Retention-Kurve belohnt:

    0.0 - 1.5 s   Bild schockt, bevor irgendjemand spricht. Kein Logo, kein "Hi".
    0.0 - 3.0 s   Erster Satz oeffnet eine Wissensluecke, die man schliessen WILL.
    ~ alle 10 s   Neuer visueller Reiz — faellt hier mit der Clipgrenze zusammen.
    40 - 60 %     Der Re-Hook. Genau da steigen die Leute sonst aus, also kommt
                  dort die Wendung: "Aber das ist nicht der eigentliche Punkt."
    letzte 3 s    Loop-Back: der letzte Satz fuehrt zurueck zum ersten, damit das
                  Video nahtlos nochmal laeuft. Kein Abspann, keine Verabschiedung.

Dazu kommt das Anti-Wiederholungs-Gedaechtnis: jede Idee wird gegen alles
geprueft, was der Kanal schon produziert hat.
"""

from tiktok.channels import Channel
from tiktok.llm import LLM
from tiktok.memory import VideoMemory

ROLE_HOOK = "hook"
ROLE_SETUP = "setup"
ROLE_ESCALATION = "escalation"
ROLE_REHOOK = "rehook"
ROLE_PEAK = "peak"
ROLE_LOOP = "payoff_loop"

ROLE_BRIEF = {
    ROLE_HOOK: (
        "Sekunde 0-3. Das staerkste Bild des ganzen Videos, sofort, ohne Anlauf. "
        "Der erste Satz ist eine offene Schleife: eine Behauptung oder Frage, deren "
        "Aufloesung man abwarten muss. Nie mit einer Begruessung oder dem Namen des "
        "Tieres/Themas beginnen."
    ),
    ROLE_SETUP: "Kontext, aber nur so viel wie noetig. Jeder Satz muss die Spannung halten, nicht erklaeren.",
    ROLE_ESCALATION: "Steigerung. Neue Information, groesseres Bild, hoehere Einsaetze als im Clip davor.",
    ROLE_REHOOK: (
        "Der Wendepunkt bei ca. 50 % — genau da, wo die Leute sonst wegwischen. "
        "Kehre die Erwartung um ('Aber das ist nicht der eigentliche Wahnsinn'), "
        "liefere die ueberraschendste Einzelinformation des Videos."
    ),
    ROLE_PEAK: "Der visuelle und inhaltliche Hoehepunkt. Hier wird die Schleife aus dem Hook eingeloest.",
    ROLE_LOOP: (
        "Aufloesung plus Loop-Back: der letzte Satz muss inhaltlich an den ersten Satz "
        "andocken, sodass ein direkter Rewatch sich wie eine Fortsetzung anfuehlt. "
        "Keine Verabschiedung, kein 'Folgt mir', kein Abspann."
    ),
}


def beat_plan(channel: Channel) -> list[str]:
    """Verteilt die Rollen auf die Clips — Hook vorn, Re-Hook in der Mitte, Loop hinten."""
    count = channel.clip_count
    if count == 1:
        return [ROLE_HOOK]
    if count == 2:
        return [ROLE_HOOK, ROLE_LOOP]
    if count == 3:
        return [ROLE_HOOK, ROLE_REHOOK, ROLE_LOOP]

    roles = [ROLE_ESCALATION] * count
    roles[0] = ROLE_HOOK
    roles[1] = ROLE_SETUP
    roles[-1] = ROLE_LOOP
    roles[-2] = ROLE_PEAK
    # Re-Hook auf die Clipgrenze bei ca. 50 % der Laufzeit legen.
    roles[max(2, round(count * 0.5) - 1)] = ROLE_REHOOK
    return roles


def _channel_system(channel: Channel) -> str:
    return (
        f"Du bist Head of Content fuer den TikTok-Kanal '{channel.name}'.\n\n"
        f"KANAL-BIBEL:\n{channel.bible}\n\n"
        f"PERSONA DER STIMME:\n{channel.persona}\n\n"
        f"Sprache aller Texte: {channel.language}.\n\n"
        "REGELN, die ueber allem stehen:\n"
        "1. Retention schlaegt Vollstaendigkeit. Lieber eine Sache richtig spannend "
        "als drei Sachen korrekt und langweilig.\n"
        "2. Keine Floskeln, keine Fuellwoerter, keine Moderationssaetze "
        "('In diesem Video zeige ich euch...'). Gesprochen wird nur, was Bild oder "
        "Spannung traegt.\n"
        "3. Konkrete Zahlen, Namen, Vergleiche statt Adjektiven. 'Der Druck von "
        "40 Autos auf einer Handflaeche' statt 'unglaublich stark'.\n"
        "4. Fakten muessen stimmen. Wenn du dir bei einer Zahl nicht sicher bist, "
        "nimm eine andere Aussage, die du sicher belegen kannst.\n"
        "5. Nie zwei Videos mit demselben Muster. Weder Thema noch Hook noch "
        "Satzbau noch Kameraidee duerfen sich wiederholen.\n"
        "6. Antworte ausschliesslich mit gueltigem JSON, ohne Text davor oder danach."
    )


# ---------------------------------------------------------------- Idee

IDEA_KEYS = ("topic", "subject", "hook", "first_line", "style", "angle", "payoff", "why_it_works")


def generate_idea(llm: LLM, channel: Channel, memory: VideoMemory, attempts: int = 4) -> dict:
    """Erzeugt eine Videoidee, die es auf diesem Kanal noch nicht gab."""
    system = _channel_system(channel)
    feedback = ""

    for attempt in range(1, attempts + 1):
        prompt = (
            "Entwickle EINE neue Videoidee fuer den Kanal.\n\n"
            f"Thematischer Korridor (waehle daraus oder etwas Benachbartes):\n"
            + "\n".join(f"  - {d}" for d in channel.domains)
            + "\n\nMoegliche Erzaehlwinkel (rotiere bewusst, nimm nicht immer den ersten):\n"
            + "\n".join(f"  - {a}" for a in channel.angles)
            + "\n\nDAS HIER GAB ES SCHON — jede Wiederholung ist ein Fehler:\n"
            + memory.avoid_block(channel.slug)
            + (f"\n\nSelbst gelernte Regeln:\n{memory.lessons()}" if memory.lessons() else "")
            + feedback
            + "\n\nAntworte als JSON:\n"
            "{\n"
            '  "topic": "das Thema in max. 8 Woertern",\n'
            '  "subject": "das konkrete Tier / der konkrete Ort / die konkrete Person im Video",\n'
            '  "hook": "die Spannungsidee der ersten 3 Sekunden, in einem Satz beschrieben",\n'
            '  "first_line": "der exakte erste gesprochene Satz, max. 12 Woerter",\n'
            '  "style": "die visuelle Grundidee dieses Videos in max. 10 Woertern",\n'
            '  "angle": "welcher Erzaehlwinkel verwendet wird",\n'
            '  "payoff": "die Aufloesung, auf die das Video zulaeuft",\n'
            '  "why_it_works": "in einem Satz: warum jemand das bis zum Ende schaut"\n'
            "}"
        )
        idea = llm.json(system, prompt, tier="creative")
        missing = [k for k in IDEA_KEYS if not str(idea.get(k, "")).strip()]
        if missing:
            feedback = f"\n\nDein letzter Versuch war unvollstaendig (fehlend: {', '.join(missing)})."
            continue

        reason = memory.repeat_reason(channel.slug, idea)
        if not reason:
            return idea
        feedback = (
            f"\n\nDEIN VERSUCH {attempt} WURDE ABGELEHNT: {reason}. "
            "Waehle ein deutlich anderes Subjekt UND einen anderen Erzaehlwinkel — "
            "nicht nur andere Worte fuer dasselbe."
        )

    raise RuntimeError(
        f"Nach {attempts} Versuchen nur Wiederholungen fuer Kanal {channel.slug}. "
        "Korridor in der Kanaldatei erweitern (domains/angles)."
    )


# ---------------------------------------------------------------- Skript


def generate_script(llm: LLM, channel: Channel, idea: dict, attempts: int = 3) -> dict:
    """Baut aus der Idee ein Beat-Skript — ein Beat pro Videoclip."""
    system = _channel_system(channel)
    roles = beat_plan(channel)
    seconds = channel.clip_seconds
    feedback = ""

    beat_specs = "\n".join(
        f"  Clip {i + 1} ({i * seconds}-{(i + 1) * seconds}s) — Rolle '{role}': {ROLE_BRIEF[role]} "
        f"Wortbudget Voiceover: {channel.word_budget(seconds) - 3}-{channel.word_budget(seconds)} Woerter."
        for i, role in enumerate(roles)
    )

    for _ in range(attempts):
        prompt = (
            f"Schreibe das Skript zu dieser Idee:\n{_format_idea(idea)}\n\n"
            f"Das Video besteht aus {len(roles)} Clips à {seconds} Sekunden "
            f"(gesamt {len(roles) * seconds}s, Format {channel.aspect_ratio}).\n\n"
            f"BEAT-STRUKTUR:\n{beat_specs}\n\n"
            "WICHTIG fuer die Bild-Prompts:\n"
            "- Clip 1 beschreibt die Szene vollstaendig (Subjekt, Umgebung, Licht, Kamera).\n"
            f"- Clip 2 bis {len(roles)} werden technisch als Fortsetzung des vorherigen Clips "
            "erzeugt. Beschreibe dort nur, WAS SICH AENDERT: Bewegung, Kamerafahrt, neuer "
            "Bildausschnitt, neues Element. Wiederhole nicht die ganze Szenenbeschreibung, "
            "aber benenne das Subjekt weiter eindeutig, damit es konsistent bleibt.\n"
            "- Bild-Prompts auf Englisch, ein dichter Absatz, keine Aufzaehlung, "
            "keine Stilangaben (die kommen automatisch dazu), kein Text im Bild.\n"
            "- Jeder Clip braucht eine eigene Kameraidee. Keine zwei Clips mit derselben "
            "Einstellung.\n\n"
            "Das Voiceover laeuft durchgehend ueber alle Clips und muss sich wie EIN Text "
            "lesen, nicht wie vier Bruchstuecke.\n"
            + feedback
            + "\n\nAntworte als JSON:\n"
            "{\n"
            '  "title": "interner Titel",\n'
            '  "caption": "TikTok-Caption, max. 120 Zeichen, macht neugierig, keine Hashtags",\n'
            '  "hashtags": ["#..."],\n'
            '  "beats": [\n'
            "    {\n"
            '      "role": "hook",\n'
            '      "voiceover": "der exakt gesprochene Text dieses Clips",\n'
            '      "video_prompt": "englischer Bild-Prompt",\n'
            '      "camera": "Kameraeinstellung und -bewegung in wenigen Worten",\n'
            '      "on_screen_text": "max. 5 Woerter oder leer"\n'
            "    }\n"
            "  ]\n"
            "}"
        )
        script = llm.json(system, prompt, tier="creative")
        problems = validate_script(channel, script)
        if not problems:
            script["idea"] = idea
            script.setdefault("hashtags", channel.hashtags)
            for beat, role in zip(script["beats"], roles):
                beat["role"] = role
                beat["seconds"] = seconds
            return script
        feedback = (
            "\n\nDEIN LETZTER ENTWURF WURDE ABGELEHNT:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\nBehebe genau diese Punkte."
        )

    raise RuntimeError(f"Skript nach {attempts} Versuchen weiterhin fehlerhaft: {problems}")


def validate_script(channel: Channel, script: dict) -> list[str]:
    """Prueft das Skript gegen die harten Vorgaben. Leere Liste = in Ordnung."""
    problems: list[str] = []
    beats = script.get("beats")
    expected = channel.clip_count

    if not isinstance(beats, list) or not beats:
        return ["Feld 'beats' fehlt oder ist leer."]
    if len(beats) != expected:
        problems.append(f"{len(beats)} Beats geliefert, gebraucht werden genau {expected}.")

    budget = channel.word_budget(channel.clip_seconds)
    cameras: list[str] = []
    for i, beat in enumerate(beats, start=1):
        voiceover = str(beat.get("voiceover", "")).strip()
        prompt = str(beat.get("video_prompt", "")).strip()
        if not voiceover:
            problems.append(f"Clip {i}: voiceover fehlt.")
        if not prompt:
            problems.append(f"Clip {i}: video_prompt fehlt.")
        words = len(voiceover.split())
        # Zu lang heisst: das Voiceover laeuft ueber die Clipgrenze hinaus.
        if words > budget:
            problems.append(
                f"Clip {i}: {words} Woerter, erlaubt sind maximal {budget} "
                f"(sonst passt das Voiceover nicht in {channel.clip_seconds}s)."
            )
        if words and words < budget * 0.4:
            problems.append(f"Clip {i}: nur {words} Woerter — zu wenig, es entsteht eine Leerstelle.")
        if len(str(beat.get("on_screen_text", "")).split()) > 5:
            problems.append(f"Clip {i}: on_screen_text laenger als 5 Woerter.")
        camera = str(beat.get("camera", "")).strip().lower()
        if camera and camera in cameras:
            problems.append(f"Clip {i}: dieselbe Kameraeinstellung wie in einem frueheren Clip.")
        cameras.append(camera)

    first_line = str(beats[0].get("voiceover", "")).strip().lower()
    if first_line.startswith(("hallo", "hi ", "willkommen", "in diesem video", "heute")):
        problems.append("Clip 1: Der erste Satz ist eine Begruessung/Moderation — das killt die Hook.")

    last_line = str(beats[-1].get("voiceover", "")).lower()
    if any(word in last_line for word in ("abonnier", "folgt mir", "like da", "bis zum naechsten")):
        problems.append("Letzter Clip: Abspann/CTA im Voiceover — killt Watchtime und Loop.")

    return problems


def _format_idea(idea: dict) -> str:
    return "\n".join(f"  {key}: {idea.get(key, '')}" for key in IDEA_KEYS)


# ---------------------------------------------------------------- Prompts fuer den Provider


def clip_prompt(channel: Channel, beat: dict, index: int) -> str:
    """Baut den finalen Prompt fuer einen Clip: Beat + Kamera + Kanalstil."""
    parts = [str(beat.get("video_prompt", "")).strip()]
    camera = str(beat.get("camera", "")).strip()
    if camera:
        parts.append(f"Camera: {camera}.")
    if channel.visual_style:
        parts.append(channel.visual_style)
    if index == 0:
        # Nur der erste Clip legt das Format fest, danach uebernimmt extend.
        parts.append(f"Vertical {channel.aspect_ratio} composition.")
    return " ".join(p for p in parts if p)


def full_voiceover(script: dict) -> str:
    return " ".join(str(b.get("voiceover", "")).strip() for b in script.get("beats", []))
