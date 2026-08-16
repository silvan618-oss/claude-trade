import os

from tiktok.assemble import (
    build_srt,
    concat_args,
    mix_args,
    normalize_args,
    write_concat_list,
)


def test_normalize_schneidet_auf_hochformat():
    args = normalize_args("ffmpeg", "in.mp4", "out.mp4", 1080, 1920, 30, silent=False)
    joined = " ".join(args)
    assert "scale=1080:1920" in joined and "crop=1080:1920" in joined
    assert "fps=30" in joined
    assert "anullsrc" not in joined


def test_normalize_ergaenzt_stille_bei_clips_ohne_ton():
    args = normalize_args("ffmpeg", "in.mp4", "out.mp4", 1080, 1920, 30, silent=True)
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in args
    assert "-shortest" in args


def test_concat_kopiert_ohne_neukodierung():
    args = concat_args("ffmpeg", "list.txt", "out.mp4")
    assert args[:6] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0"]
    assert "-c" in args and "copy" in args


def test_concat_liste_nutzt_absolute_pfade(tmp_path):
    clip = tmp_path / "clip_01.mp4"
    clip.write_bytes(b"")
    list_path = write_concat_list([str(clip)], str(tmp_path / "concat.txt"))
    content = open(list_path, encoding="utf-8").read()
    assert content.startswith("file '/") and str(clip) in content


def test_mix_legt_voiceover_an_die_clipgrenzen():
    args = mix_args("ffmpeg", "joined.mp4", [("v1.mp3", 0.0), ("v2.mp3", 10.0)], "", "out.mp4")
    filters = args[args.index("-filter_complex") + 1]
    assert "adelay=0|0" in filters
    assert "adelay=10000|10000" in filters
    # Zwei Sprachspuren plus Originalton
    assert "amix=inputs=3" in filters
    assert "normalize=0" in filters


def test_mix_mischt_musik_als_zusaetzliche_spur():
    args = mix_args("ffmpeg", "joined.mp4", [("v1.mp3", 0.0)], "musik.mp3", "out.mp4")
    filters = args[args.index("-filter_complex") + 1]
    assert "amix=inputs=3" in filters
    assert "musik.mp3" in args


def test_mix_ohne_untertitel_kopiert_das_bild():
    args = mix_args("ffmpeg", "joined.mp4", [("v1.mp3", 0.0)], "", "out.mp4")
    assert args[args.index("-c:v") + 1] == "copy"


def test_mix_mit_untertiteln_rendert_neu():
    args = mix_args("ffmpeg", "joined.mp4", [("v1.mp3", 0.0)], "", "out.mp4", subtitles="subs.srt")
    assert args[args.index("-c:v") + 1] == "libx264"
    assert "subtitles='subs.srt'" in args[args.index("-filter_complex") + 1]


def test_srt_zeitachse_folgt_den_clipdauern():
    beats = [{"voiceover": "erster satz"}, {"voiceover": "zweiter satz"}]
    srt = build_srt(beats, [10.0, 9.5])
    assert "00:00:00,000 --> 00:00:10,000" in srt
    assert "00:00:10,000 --> 00:00:19,500" in srt
    assert "zweiter satz" in srt


def test_srt_ueberspringt_leere_beats():
    assert build_srt([{"voiceover": ""}], [10.0]).strip() == ""
