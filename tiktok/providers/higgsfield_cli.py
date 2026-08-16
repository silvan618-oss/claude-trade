"""Higgsfield ueber die offizielle CLI.

Wenn Higgsfield lokal als CLI (oder MCP-Bridge) installiert ist, ist das der
sauberste Weg: kein eigener API-Nachbau, keine Browser-Automatisierung, und die
Authentifizierung liegt beim offiziellen Tool.

Die Kommandozeilen sind als Vorlage konfigurierbar, weil sich CLI-Flags
schneller aendern als dieser Code:

    HIGGSFIELD_CLI_GENERATE="generate --model {model} --prompt {prompt} --duration {seconds} --aspect {aspect_ratio} --output {output}"
    HIGGSFIELD_CLI_EXTEND="extend --video {source_id} --prompt {prompt} --duration {seconds} --output {output}"
"""

import os
import shlex
import subprocess

from tiktok.config import Config
from tiktok.providers.base import ClipResult, GenerationFailed

DEFAULT_GENERATE = (
    "generate --model {model} --prompt {prompt} --duration {seconds} "
    "--aspect {aspect_ratio} --output {output}"
)
DEFAULT_EXTEND = (
    "extend --from {source_id} --prompt {prompt} --duration {seconds} --output {output}"
)


class HiggsfieldCliProvider:
    name = "higgsfield_cli"
    supports_extend = True

    def __init__(self, config: Config):
        self.config = config
        self.generate_template = os.getenv("HIGGSFIELD_CLI_GENERATE", DEFAULT_GENERATE)
        self.extend_template = os.getenv("HIGGSFIELD_CLI_EXTEND", DEFAULT_EXTEND)

    def generate(self, prompt: str, seconds: int, aspect_ratio: str, out_path: str) -> ClipResult:
        return self._run(self.generate_template, prompt, seconds, aspect_ratio, out_path, "")

    def extend(self, prompt: str, seconds: int, source: ClipResult, out_path: str) -> ClipResult:
        anchor = source.video_id or source.path
        return self._run(self.extend_template, prompt, seconds, "", out_path, anchor)

    def build_command(self, template: str, values: dict) -> list[str]:
        """Baut die Argumentliste — Werte werden nie in die Shell interpoliert."""
        args = [self.config.higgsfield_cli]
        for token in shlex.split(template):
            if token.startswith("{") and token.endswith("}"):
                args.append(str(values.get(token[1:-1], "")))
            else:
                args.append(token)
        return args

    def _run(self, template: str, prompt: str, seconds: int, aspect_ratio: str, out_path: str, source_id: str) -> ClipResult:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        cmd = self.build_command(
            template,
            {
                "model": self.config.video_model,
                "prompt": prompt,
                "seconds": seconds,
                "aspect_ratio": aspect_ratio or "9:16",
                "output": out_path,
                "source_id": source_id,
            },
        )
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=self.config.generation_timeout_seconds
        )
        if proc.returncode != 0:
            raise GenerationFailed(f"Higgsfield-CLI ({proc.returncode}): {proc.stderr.strip()[:500]}")
        if not os.path.exists(out_path):
            raise GenerationFailed(f"CLI meldete Erfolg, aber {out_path} existiert nicht.")

        index = int(os.path.splitext(os.path.basename(out_path))[0].split("_")[-1] or 0)
        return ClipResult(
            index=index,
            path=out_path,
            prompt=prompt,
            video_id=out_path,
            seconds=float(seconds),
            meta={"stdout": proc.stdout.strip()[:2000]},
        )
