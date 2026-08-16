"""Kommandozeile.

    python -m tiktok channels                      # verfuegbare Kanalprofile
    python -m tiktok idea   -c silver-wildlife      # nur eine Idee (kostet fast nichts)
    python -m tiktok script -c silver-wildlife      # Idee + Skript, ohne Video
    python -m tiktok once   -c silver-wildlife      # ein komplettes Video
    python -m tiktok resume output/silver-wildlife/2026-08-16-...   # abgebrochenen Job fortsetzen
    python -m tiktok loop   -c silver-wildlife -c silver-influencer # Dauerbetrieb
"""

import argparse
import json
import sys

from tiktok import creative
from tiktok.channels import list_channels, load_channel
from tiktok.config import load_config
from tiktok.llm import LLM
from tiktok.memory import VideoMemory
from tiktok.pipeline import Pipeline
from tiktok.providers import build_provider
from tiktok.runner import Runner
from tiktok.voice import build_voice


def _memory(config):
    return VideoMemory(config.ledger_path, config.used_path, config.lessons_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tiktok", description="Vollautomatische TikTok-Produktion")
    parser.add_argument("command", choices=["channels", "idea", "script", "once", "resume", "loop"])
    parser.add_argument("target", nargs="?", default="", help="Job-Ordner (nur bei resume)")
    parser.add_argument("-c", "--channel", action="append", default=[], help="Kanal-Slug (mehrfach moeglich)")
    parser.add_argument("--music", default="", help="Musikdatei, die untergemischt wird")
    args = parser.parse_args(argv)

    config = load_config()

    if args.command == "channels":
        for slug in list_channels(config.channels_dir):
            channel = load_channel(slug, config.channels_dir)
            print(f"{slug:24s} {channel.name} — {channel.clip_count} Clips à {channel.clip_seconds}s")
        return 0

    if args.command == "resume":
        if not args.target:
            parser.error("resume braucht den Job-Ordner als Argument.")
        with open(f"{args.target}/state.json", encoding="utf-8") as fh:
            state = json.load(fh)
        channel = load_channel(state["channel"], config.channels_dir)
        pipeline = Pipeline(
            config, channel, LLM(config), _memory(config),
            build_provider(config), build_voice(config, channel),
        )
        pipeline.produce(job_dir=args.target, music=args.music)
        return 0

    if not args.channel:
        parser.error("Bitte mindestens einen Kanal angeben: -c <slug>")

    if args.command == "loop":
        Runner(config, args.channel, music=args.music).run()
        return 0

    channel = load_channel(args.channel[0], config.channels_dir)
    memory = _memory(config)
    llm = LLM(config)

    if args.command == "idea":
        print(json.dumps(creative.generate_idea(llm, channel, memory), ensure_ascii=False, indent=2))
        return 0

    if args.command == "script":
        idea = creative.generate_idea(llm, channel, memory)
        print(json.dumps(creative.generate_script(llm, channel, idea), ensure_ascii=False, indent=2))
        return 0

    Pipeline(
        config, channel, llm, memory, build_provider(config), build_voice(config, channel)
    ).produce(music=args.music)
    return 0


if __name__ == "__main__":
    sys.exit(main())
