"""Video-Provider: alles, was aus einem Prompt einen Clip macht.

Drei Wege, je nachdem, welchen Zugang man hat:

  higgsfield      HTTP-API mit Key (voll automatisch)
  higgsfield_cli  die offizielle Higgsfield-CLI/MCP lokal (voll automatisch)
  assisted        Prompts werden in den Job-Ordner geschrieben, die fertigen
                  Clips legt man selbst dort ab. Der Rest der Pipeline laeuft
                  weiter automatisch.

Alle drei erfuellen dasselbe Interface, die Pipeline kennt den Unterschied nicht.
"""

from tiktok.config import Config
from tiktok.providers.base import ClipResult, VideoProvider


def build_provider(config: Config) -> VideoProvider:
    name = config.video_provider.lower()
    if name == "higgsfield":
        from tiktok.providers.higgsfield import HiggsfieldProvider

        return HiggsfieldProvider(config)
    if name in ("higgsfield_cli", "cli"):
        from tiktok.providers.higgsfield_cli import HiggsfieldCliProvider

        return HiggsfieldCliProvider(config)
    if name == "assisted":
        from tiktok.providers.assisted import AssistedProvider

        return AssistedProvider(config)
    raise ValueError(f"Unbekannter VIDEO_PROVIDER: {config.video_provider}")


__all__ = ["build_provider", "ClipResult", "VideoProvider"]
