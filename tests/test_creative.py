from tiktok import creative
from tiktok.channels import Channel
from tiktok.creative import ROLE_HOOK, ROLE_LOOP, ROLE_REHOOK


def make_channel(**kwargs) -> Channel:
    defaults = dict(
        slug="test",
        name="Test",
        visual_style="cinematic wildlife look",
        target_seconds=40,
        clip_seconds=10,
        words_per_second=2.4,
    )
    defaults.update(kwargs)
    return Channel(**defaults)


def valid_script(channel: Channel) -> dict:
    budget = channel.word_budget(channel.clip_seconds)
    beats = []
    for i in range(channel.clip_count):
        beats.append(
            {
                "voiceover": " ".join(f"wort{i}{j}" for j in range(budget - 2)),
                "video_prompt": f"a lion at dusk, step {i}",
                "camera": f"kamera {i}",
                "on_screen_text": "",
            }
        )
    return {"title": "t", "caption": "c", "beats": beats}


def test_beat_plan_hat_hook_rehook_und_loop():
    roles = creative.beat_plan(make_channel())
    assert len(roles) == 4
    assert roles[0] == ROLE_HOOK
    assert roles[-1] == ROLE_LOOP
    # Der Re-Hook muss in der Mitte sitzen, nicht am Rand.
    assert ROLE_REHOOK in roles[1:-1]


def test_beat_plan_bei_sechs_clips_setzt_rehook_um_die_haelfte():
    roles = creative.beat_plan(make_channel(target_seconds=60))
    assert len(roles) == 6
    assert roles.index(ROLE_REHOOK) in (2, 3)


def test_gueltiges_skript_hat_keine_probleme():
    channel = make_channel()
    assert creative.validate_script(channel, valid_script(channel)) == []


def test_zu_langes_voiceover_wird_erkannt():
    channel = make_channel()
    script = valid_script(channel)
    script["beats"][1]["voiceover"] = " ".join(["wort"] * 60)
    problems = creative.validate_script(channel, script)
    assert any("maximal" in p for p in problems)


def test_falsche_anzahl_beats_wird_erkannt():
    channel = make_channel()
    script = valid_script(channel)
    script["beats"].pop()
    assert any("genau 4" in p for p in creative.validate_script(channel, script))


def test_begruessung_im_hook_wird_abgelehnt():
    channel = make_channel()
    script = valid_script(channel)
    script["beats"][0]["voiceover"] = "Hallo Leute, heute geht es um Loewen und ihre Jagd"
    assert any("Hook" in p for p in creative.validate_script(channel, script))


def test_cta_im_letzten_clip_wird_abgelehnt():
    channel = make_channel()
    script = valid_script(channel)
    script["beats"][-1]["voiceover"] = "Abonniert den Kanal fuer mehr solche Videos jeden Tag"
    assert any("Watchtime" in p for p in creative.validate_script(channel, script))


def test_doppelte_kamera_wird_erkannt():
    channel = make_channel()
    script = valid_script(channel)
    script["beats"][2]["camera"] = script["beats"][1]["camera"]
    assert any("Kameraeinstellung" in p for p in creative.validate_script(channel, script))


def test_zu_langer_bildtext_wird_erkannt():
    channel = make_channel()
    script = valid_script(channel)
    script["beats"][0]["on_screen_text"] = "eins zwei drei vier fuenf sechs"
    assert any("on_screen_text" in p for p in creative.validate_script(channel, script))


def test_clip_prompt_haengt_stil_an_und_setzt_format_nur_im_ersten_clip():
    channel = make_channel()
    beat = {"video_prompt": "a wolf in snow", "camera": "slow push in"}
    first = creative.clip_prompt(channel, beat, 0)
    later = creative.clip_prompt(channel, beat, 2)
    assert "a wolf in snow" in first
    assert "cinematic wildlife look" in first and "cinematic wildlife look" in later
    assert "9:16" in first and "9:16" not in later


def test_wortbudget_folgt_sprechgeschwindigkeit():
    assert make_channel(words_per_second=2.4).word_budget(10) == 24
