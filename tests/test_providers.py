import json
import os

import pytest

from tiktok.config import Config
from tiktok.providers.assisted import AssistedProvider
from tiktok.providers.higgsfield import dig, fill
from tiktok.providers.higgsfield_cli import HiggsfieldCliProvider


def test_dig_folgt_pfaden_mit_listenindex():
    data = {"results": [{"url": "https://x/v.mp4"}]}
    assert dig(data, "results.0.url") == "https://x/v.mp4"
    assert dig(data, "results.5.url") is None
    assert dig(data, "gibtsnicht") is None


def test_fill_ersetzt_platzhalter_und_erhaelt_typen():
    body = fill(
        {"model": "{model}", "duration": "{seconds}", "prompt": "a {model} shot"},
        {"model": "seedance-2.5", "seconds": 10},
    )
    assert body == {"model": "seedance-2.5", "duration": 10, "prompt": "a seedance-2.5 shot"}


def test_fill_entfernt_kommentarfelder():
    assert fill({"_comment": "weg", "a": "1"}, {}) == {"a": "1"}


def test_schema_datei_ist_gueltig_und_vollstaendig():
    with open("tiktok/providers/higgsfield.schema.json", encoding="utf-8") as fh:
        schema = json.load(fh)
    for section in ("generate", "extend", "status"):
        assert "path" in schema[section]
    assert "{source_id}" in json.dumps(schema["extend"])
    assert "{job_id}" in schema["status"]["path"]


def test_cli_kommando_interpoliert_nie_in_die_shell():
    provider = HiggsfieldCliProvider(Config())
    cmd = provider.build_command(
        "generate --prompt {prompt} --output {output}",
        {"prompt": "a lion; rm -rf /", "output": "clip_01.mp4"},
    )
    # Der Prompt bleibt genau ein Argument, egal was drinsteht.
    assert cmd[-3] == "a lion; rm -rf /"
    assert cmd[-1] == "clip_01.mp4"


def test_assisted_schreibt_prompt_und_findet_abgelegten_clip(tmp_path):
    config = Config()
    config.generation_timeout_seconds = 5
    config.poll_interval_seconds = 1
    provider = AssistedProvider(config)

    out_path = str(tmp_path / "clip_01.mp4")
    # Clip liegt schon da: der Provider muss ihn sofort uebernehmen.
    with open(out_path, "wb") as fh:
        fh.write(b"video")

    result = provider.generate("a lion at dusk", 10, "9:16", out_path)
    assert result.path == out_path
    assert os.path.exists(tmp_path / "clip_01.prompt.txt")
    prompt_file = open(tmp_path / "clip_01.prompt.txt", encoding="utf-8").read()
    assert "a lion at dusk" in prompt_file
    assert "NEUE Generierung" in prompt_file


def test_assisted_laeuft_in_timeout_wenn_nichts_abgelegt_wird(tmp_path):
    config = Config()
    config.generation_timeout_seconds = 1
    config.poll_interval_seconds = 1
    provider = AssistedProvider(config)
    with pytest.raises(Exception, match="Kein Clip"):
        provider.generate("prompt", 10, "9:16", str(tmp_path / "clip_02.mp4"))
