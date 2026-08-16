"""Vollautomatische TikTok-Video-Produktion.

Idee -> Skript (TikTok-Retention-Struktur) -> Clip-Prompts -> Video-Generierung
(Higgsfield/Seedance, Clip fuer Clip per extend) -> Voiceover -> Schnitt (ffmpeg)
-> fertiges 9:16-Video.

Der Einstieg ist `python -m tiktok --help`.
"""

__all__ = ["config", "llm", "memory", "channels", "creative", "voice", "assemble", "pipeline", "runner"]
