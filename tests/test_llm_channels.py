import json

import pytest

from tiktok.channels import Channel, list_channels, load_channel
from tiktok.llm import LLMError, extract_json


def test_extract_json_aus_reinem_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_aus_codeblock():
    assert extract_json('Hier bitte:\n```json\n{"a": 1}\n```\nFertig.') == {"a": 1}


def test_extract_json_mit_text_davor():
    assert extract_json('Klar!\n{"topic": "Wolf"}') == {"topic": "Wolf"}


def test_extract_json_mit_verschachtelten_objekten():
    payload = {"beats": [{"voiceover": "a"}, {"voiceover": "b"}]}
    assert extract_json(f"Antwort: {json.dumps(payload)} — passt.") == payload


def test_extract_json_scheitert_verstaendlich():
    with pytest.raises(LLMError, match="Keine gueltige JSON-Antwort"):
        extract_json("Tut mir leid, dazu kann ich nichts sagen.")


def test_kanalprofile_im_repo_laden_und_sind_plausibel():
    slugs = list_channels("channels")
    assert "silver-wildlife" in slugs and "silver-influencer" in slugs
    for slug in slugs:
        channel = load_channel(slug, "channels")
        assert channel.bible and channel.visual_style
        assert channel.domains and channel.angles
        assert channel.clip_count >= 3  # sonst passt die Hook/Re-Hook/Loop-Struktur nicht


def test_clip_count_rundet_auf_ganze_clips():
    assert Channel(slug="x", name="X", target_seconds=60, clip_seconds=10).clip_count == 6
    assert Channel(slug="x", name="X", target_seconds=45, clip_seconds=10).clip_count == 4


def test_fehlendes_profil_nennt_die_vorhandenen():
    with pytest.raises(FileNotFoundError, match="silver-wildlife"):
        load_channel("gibtsnicht", "channels")


def test_unbekannte_felder_im_profil_brechen_nicht():
    channel = Channel.from_dict({"slug": "x", "name": "X", "voellig_neues_feld": 1})
    assert channel.slug == "x"
