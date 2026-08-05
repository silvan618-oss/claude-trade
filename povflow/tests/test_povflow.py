"""Unit tests for the parts that run without network or ffmpeg."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from povflow.assemble import (  # noqa: E402
    AssemblyError, Dimensions, build_concat_command, build_normalize_command,
    build_video_filter, target_dimensions,
)
from povflow.handoff import render_handoff  # noqa: E402
from povflow.pipeline import assemble_folder  # noqa: E402
from povflow.config import ConfigError, load_config  # noqa: E402
from povflow.omni import ChainState, build_request  # noqa: E402
from povflow.ideas import (  # noqa: E402
    Concept, Shot, drop_duplicates, parse_concepts, build_idea_prompt, IdeaError,
)
from povflow.shotlist import build_shot_prompt, build_shotlist  # noqa: E402
from povflow.state import Store, idea_fingerprint, slugify  # noqa: E402
from povflow.style import NEGATIVE_PROMPT, POV_STYLE_DNA  # noqa: E402
from povflow.voiceover import build_vo_lines, format_timecode, render_script, render_srt  # noqa: E402

BASE_CONFIG = """
[channel]
niche = "test niche"
style_preset = "fantasy"
language = "de"

[video]
backend = "veo"
chain_shots = false
model = "veo-3.1-fast-generate-preview"
resolution = "720p"
aspect_ratio = "9:16"
seconds_per_shot = 8
shots_per_episode = 5

[costs]
max_usd_per_run = 6.0
max_usd_per_month = 120.0

[paths]
output_dir = "output"
state_db = "state/db.sqlite3"
"""

OMNI_CONFIG = BASE_CONFIG.replace(
    'backend = "veo"\nchain_shots = false\nmodel = "veo-3.1-fast-generate-preview"',
    'backend = "omni"\nchain_shots = true\nmodel = "gemini-omni-flash-preview"',
)


def write_config(tmp: Path, body: str = BASE_CONFIG) -> Path:
    path = tmp / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def make_concept(title: str = "Test", shots: int = 3) -> Concept:
    return Concept(
        title=title,
        logline="A thing happens in the woods.",
        hook_visual="a huge shape already blocking the path",
        shots=[
            Shot(index=i + 1, beat=f"beat {i + 1}", action=f"action {i + 1}",
                 camera="handheld push in", ambient="wind in trees")
            for i in range(shots)
        ],
        voiceover=[f"line {i + 1}" for i in range(shots)],
    )


class TestConfig(unittest.TestCase):
    def test_loads_and_computes_costs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp)))
            self.assertEqual(cfg.niche, "test niche")
            self.assertEqual(cfg.usd_per_second, 0.10)
            self.assertEqual(cfg.episode_seconds, 40)
            self.assertAlmostEqual(cfg.usd_per_episode, 4.0)

    def test_rejects_episode_costlier_than_run_cap(self):
        body = BASE_CONFIG.replace("max_usd_per_run = 6.0", "max_usd_per_run = 1.0")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(write_config(Path(tmp), body))
            self.assertIn("over max_usd_per_run", str(ctx.exception))

    def test_rejects_bad_aspect_ratio(self):
        body = BASE_CONFIG.replace('aspect_ratio = "9:16"', 'aspect_ratio = "4:3"')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(write_config(Path(tmp), body))

    def test_unknown_rate_raises_with_guidance(self):
        body = BASE_CONFIG.replace(
            'model = "veo-3.1-fast-generate-preview"', 'model = "veo-9-imaginary"'
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(write_config(Path(tmp), body))
            self.assertIn("No price known", str(ctx.exception))


MANUAL_CONFIG = BASE_CONFIG.replace(
    'backend = "veo"', 'backend = "manual"'
) + """
[costs.credits]
credits_per_clip = 15
clip_credit_seconds = 10
credits_per_second = 0.0
plan_eur = 27.99
plan_credits = 2500
"""


class TestManualBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = load_config(write_config(Path(self.tmp.name), MANUAL_CONFIG))

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_costs_nothing_via_api(self):
        self.assertTrue(self.cfg.is_manual)
        self.assertEqual(self.cfg.usd_per_second, 0.0)
        self.assertEqual(self.cfg.usd_per_episode, 0.0)

    def test_credit_maths_bills_per_clip_not_per_second(self):
        self.assertAlmostEqual(self.cfg.eur_per_credit, 27.99 / 2500)
        # 5 shots at 15 credits each, regardless of the 8s length.
        self.assertAlmostEqual(self.cfg.credits_per_episode, 75.0)
        self.assertAlmostEqual(self.cfg.eur_per_episode_credits, 75 * 27.99 / 2500)
        self.assertEqual(self.cfg.episodes_per_plan, 33)

    def test_short_shots_report_wasted_seconds(self):
        # 8s shots on a 10s clip allowance throw away 2s per generation.
        self.assertAlmostEqual(self.cfg.wasted_seconds_per_clip, 2.0)

    def test_full_length_shots_waste_nothing(self):
        body = MANUAL_CONFIG.replace("seconds_per_shot = 8", "seconds_per_shot = 10")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp), body))
            self.assertEqual(cfg.wasted_seconds_per_clip, 0.0)
            # Same 75 credits, but 50s of video instead of 40s.
            self.assertAlmostEqual(cfg.credits_per_episode, 75.0)
            self.assertEqual(cfg.episode_seconds, 50)

    def test_per_second_billing_still_supported(self):
        body = MANUAL_CONFIG.replace("credits_per_clip = 15", "credits_per_clip = 0") \
                            .replace("credits_per_second = 0.0", "credits_per_second = 1.5")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp), body))
            self.assertAlmostEqual(cfg.credits_per_episode, 40 * 1.5)
            self.assertEqual(cfg.wasted_seconds_per_clip, 0.0)

    def test_manual_allows_1080p_that_omni_forbids(self):
        body = MANUAL_CONFIG.replace('resolution = "720p"', 'resolution = "1080p"')
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp), body))
            self.assertEqual(cfg.resolution, "1080p")

    def test_manual_ignores_unknown_model_rate(self):
        # No API call means no rate lookup, so an unpriced model must not fail.
        body = MANUAL_CONFIG.replace(
            'model = "veo-3.1-fast-generate-preview"', 'model = "whatever-flow-uses"'
        )
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp), body))
            self.assertEqual(cfg.usd_per_episode, 0.0)

    def test_handoff_lists_every_shot_with_filename(self):
        concept = make_concept(shots=3)
        shots = build_shotlist(concept, self.cfg)
        sheet = render_handoff(concept, shots, self.cfg)
        for i in (1, 2, 3):
            self.assertIn(f"shots/shot_{i:02d}.mp4", sheet)
        self.assertIn(concept.hook_visual, sheet)

    def test_handoff_tells_you_to_extend_not_regenerate(self):
        concept = make_concept(shots=3)
        sheet = render_handoff(concept, build_shotlist(concept, self.cfg), self.cfg)
        self.assertIn("Shot 1 — neu generieren", sheet)
        self.assertIn("Szene aus Shot 1 erweitern", sheet)
        self.assertIn("Szene aus Shot 2 erweitern", sheet)

    def test_handoff_states_credit_cost(self):
        concept = make_concept(shots=5)
        sheet = render_handoff(concept, build_shotlist(concept, self.cfg), self.cfg)
        self.assertIn("75 Credits", sheet)


class TestShippedConfig(unittest.TestCase):
    """The config that ships in the repo must load and match the documented cost."""

    def test_default_config_is_valid_and_wastes_nothing(self):
        cfg = load_config(Path(__file__).resolve().parent.parent / "config.toml")
        self.assertTrue(cfg.is_manual)
        self.assertEqual(cfg.episode_seconds, 40)
        self.assertAlmostEqual(cfg.credits_per_episode, 60.0)
        self.assertAlmostEqual(cfg.eur_per_episode_credits, 60 * 27.99 / 2500, places=4)
        self.assertEqual(cfg.episodes_per_plan, 41)
        self.assertEqual(cfg.wasted_seconds_per_clip, 0.0)


class TestAssembleFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = load_config(write_config(Path(self.tmp.name), MANUAL_CONFIG))

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_shots_folder_is_reported(self):
        episode = Path(self.tmp.name) / "ep"
        episode.mkdir()
        with self.assertRaises(AssemblyError) as ctx:
            assemble_folder(self.cfg, episode)
        self.assertIn("No shots/ folder", str(ctx.exception))

    def test_empty_shots_folder_is_reported(self):
        episode = Path(self.tmp.name) / "ep"
        (episode / "shots").mkdir(parents=True)
        with self.assertRaises(AssemblyError) as ctx:
            assemble_folder(self.cfg, episode)
        self.assertIn("No clips found", str(ctx.exception))

    def test_non_video_files_are_ignored(self):
        episode = Path(self.tmp.name) / "ep"
        shots = episode / "shots"
        shots.mkdir(parents=True)
        (shots / "notes.txt").write_text("ignore me")
        (shots / ".DS_Store").write_text("junk")
        with self.assertRaises(AssemblyError) as ctx:
            assemble_folder(self.cfg, episode)
        self.assertIn("No clips found", str(ctx.exception))


class TestOmniConfig(unittest.TestCase):
    def test_chaining_adds_input_cost_to_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp), OMNI_CONFIG))
            self.assertEqual(cfg.backend, "omni")
            # 5 shots x 8s x $0.10 output = $4.00, plus 4 chained shots carrying
            # the previous 8s clip as input at 5792 tok/s and $1.50/1M.
            expected_chain = 8 * 5792 / 1_000_000 * 1.50
            self.assertAlmostEqual(cfg.chained_input_usd_per_shot, expected_chain)
            self.assertAlmostEqual(cfg.usd_per_episode, 4.0 + 4 * expected_chain)

    def test_no_chaining_means_no_input_surcharge(self):
        body = OMNI_CONFIG.replace("chain_shots = true", "chain_shots = false")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp), body))
            self.assertEqual(cfg.chained_input_usd_per_shot, 0.0)
            self.assertAlmostEqual(cfg.usd_per_episode, 4.0)

    def test_veo_backend_never_charges_chaining(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp)))
            self.assertEqual(cfg.chained_input_usd_per_shot, 0.0)

    def test_omni_rejects_1080p(self):
        body = OMNI_CONFIG.replace('resolution = "720p"', 'resolution = "1080p"')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(write_config(Path(tmp), body))
            self.assertIn("only outputs 720p", str(ctx.exception))

    def test_omni_rejects_clip_over_ten_seconds(self):
        body = OMNI_CONFIG.replace("seconds_per_shot = 8", "seconds_per_shot = 12")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(write_config(Path(tmp), body))
            self.assertIn("3-10s clips", str(ctx.exception))

    def test_omni_rejects_clip_under_three_seconds(self):
        body = OMNI_CONFIG.replace("seconds_per_shot = 8", "seconds_per_shot = 2")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(write_config(Path(tmp), body))

    def test_unknown_backend_rejected(self):
        body = OMNI_CONFIG.replace('backend = "omni"', 'backend = "sora"')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(write_config(Path(tmp), body))
            self.assertIn("backend must be one of", str(ctx.exception))


class TestOmniRequest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = load_config(write_config(Path(self.tmp.name), OMNI_CONFIG))
        self.shots = build_shotlist(make_concept(shots=3), self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_shot_starts_a_new_scene(self):
        req = build_request(self.cfg, self.shots[0], ChainState())
        self.assertNotIn("previous_interaction_id", req)
        self.assertEqual(
            req["generation_config"]["video_config"]["task"], "text_to_video"
        )
        self.assertEqual(req["response_format"]["aspect_ratio"], "9:16")
        self.assertEqual(req["model"], "gemini-omni-flash-preview")

    def test_chained_shot_links_to_previous_interaction(self):
        req = build_request(self.cfg, self.shots[1], ChainState("interaction-abc"))
        self.assertEqual(req["previous_interaction_id"], "interaction-abc")
        self.assertEqual(req["generation_config"]["video_config"]["task"], "edit")
        self.assertIn("Continue the same continuous handheld take", req["input"])
        self.assertIn("Do not restart the scene", req["input"])

    def test_negatives_are_folded_into_the_prompt(self):
        # Omni has no negative_prompt field, so they must survive in the text.
        req = build_request(self.cfg, self.shots[0], ChainState())
        self.assertIn("Do not include:", req["input"])
        self.assertIn("tripod", req["input"])
        self.assertIn("dialogue", req["input"])

    def test_chaining_disabled_never_links(self):
        self.cfg.chain_shots = False
        req = build_request(self.cfg, self.shots[1], ChainState("interaction-abc"))
        self.assertNotIn("previous_interaction_id", req)


class TestState(unittest.TestCase):
    def test_slugify_handles_umlauts(self):
        self.assertEqual(slugify("Größe & Wärme!"), "groesse-waerme")

    def test_fingerprint_ignores_word_order_and_filler(self):
        a = idea_fingerprint("Der Drache im Wald", "Ein Drache steht im Wald")
        b = idea_fingerprint("Wald Drache", "Im Wald steht ein Drache")
        self.assertEqual(a, b)

    def test_fingerprint_separates_different_ideas(self):
        a = idea_fingerprint("Drache im Wald", "Ein Drache im Wald")
        b = idea_fingerprint("Hai im Hafen", "Ein Hai im Hafen")
        self.assertNotEqual(a, b)

    def test_slug_collision_gets_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite3")
            _, first = store.add_episode("Same Title", "logline one", {})
            _, second = store.add_episode("Same Title", "a totally different story", {})
            self.assertEqual(first, "same-title")
            self.assertEqual(second, "same-title-2")

    def test_spend_accumulates_within_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite3")
            self.assertEqual(store.spend_this_month(), 0.0)
            store.record_spend(usd=1.5, seconds=8, model="m")
            store.record_spend(usd=2.25, seconds=8, model="m")
            self.assertAlmostEqual(store.spend_this_month(), 3.75)

    def test_spend_excludes_other_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite3")
            store.record_spend(usd=5.0, seconds=8, model="m")
            far_future = date(2099, 1, 15)
            self.assertEqual(store.spend_this_month(far_future), 0.0)


class TestIdeas(unittest.TestCase):
    RAW = """```json
    [{"title": "T1", "logline": "L1", "hook_visual": "H1",
      "shots": [{"beat":"b","action":"a1","camera":"c","ambient":"am"},
                {"beat":"b","action":"a2","camera":"c","ambient":"am"}],
      "voiceover": ["v1","v2"], "caption": "cap", "hashtags": ["#x"]}]
    ```"""

    def test_parses_fenced_json(self):
        concepts = parse_concepts(self.RAW, shots_expected=5)
        self.assertEqual(len(concepts), 1)
        self.assertEqual(concepts[0].title, "T1")
        self.assertEqual(len(concepts[0].shots), 2)
        self.assertEqual(concepts[0].shots[1].index, 2)

    def test_parses_json_embedded_in_prose(self):
        noisy = 'Here you go!\n[{"title":"A","logline":"B","shots":' \
                '[{"action":"x"}],"voiceover":["v"]}]\nHope that helps.'
        concepts = parse_concepts(noisy, shots_expected=5)
        self.assertEqual(len(concepts), 1)
        self.assertEqual(concepts[0].title, "A")

    def test_trims_overlong_shotlist_to_expected(self):
        raw = '[{"title":"A","logline":"B","shots":[' + \
              ",".join(f'{{"action":"a{i}"}}' for i in range(9)) + \
              '],"voiceover":["v"]}]'
        concepts = parse_concepts(raw, shots_expected=4)
        self.assertEqual(len(concepts[0].shots), 4)

    def test_pads_missing_voiceover_lines(self):
        raw = '[{"title":"A","logline":"B","shots":' \
              '[{"action":"a1"},{"action":"a2"}],"voiceover":["only one"]}]'
        concept = parse_concepts(raw, shots_expected=5)[0]
        self.assertEqual(len(concept.voiceover), 2)
        self.assertEqual(concept.voiceover[1], "")

    def test_skips_entries_without_title_or_shots(self):
        raw = '[{"logline":"no title","shots":[{"action":"a"}]},' \
              '{"title":"no shots","logline":"L","shots":[]},' \
              '{"title":"good","logline":"L","shots":[{"action":"a"}]}]'
        concepts = parse_concepts(raw, shots_expected=5)
        self.assertEqual([c.title for c in concepts], ["good"])

    def test_raises_on_unparseable_response(self):
        with self.assertRaises(IdeaError):
            parse_concepts("I refuse to answer.", shots_expected=5)

    def test_drop_duplicates_against_history_and_self(self):
        a, b = make_concept("Dragon in the forest"), make_concept("Forest dragon")
        c = make_concept("Shark in the harbour")
        c.logline = "A shark appears in the harbour."
        known = set()
        result = drop_duplicates([a, b, c], known)
        self.assertEqual(len(result), 2)

    def test_idea_prompt_carries_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(write_config(Path(tmp)))
            cfg.forbidden = ["gore"]
            system, user = build_idea_prompt(cfg, 3, ["Old Episode"])
            self.assertIn("exactly 5 shots", user)
            self.assertIn("gore", user)
            self.assertIn("Old Episode", user)
            self.assertIn("JSON array only", system)


class TestShotlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = load_config(write_config(Path(self.tmp.name)))
        self.concept = make_concept(shots=3)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_shot_leads_with_hook(self):
        prompt = build_shot_prompt(self.concept, 1, self.cfg).prompt
        self.assertTrue(prompt.startswith("Opens immediately on"))
        self.assertIn(self.concept.hook_visual, prompt)

    def test_every_shot_carries_style_dna_and_negatives(self):
        for shot in build_shotlist(self.concept, self.cfg):
            self.assertIn("filmed on a modern smartphone", shot.prompt)
            self.assertIn("dialogue", shot.negative_prompt)
            self.assertIn("tripod", shot.negative_prompt)

    def test_later_shots_reference_continuity(self):
        prompt = build_shot_prompt(self.concept, 2, self.cfg).prompt
        self.assertIn("Continues directly from the previous moment", prompt)
        self.assertIn("Same time of day", prompt)

    def test_shots_get_varied_imperfections(self):
        prompts = [s.prompt for s in build_shotlist(self.concept, self.cfg)]
        self.assertEqual(len(set(prompts)), len(prompts))

    def test_out_of_range_shot_raises(self):
        with self.assertRaises(IndexError):
            build_shot_prompt(self.concept, 99, self.cfg)

    def test_speech_never_requested(self):
        for shot in build_shotlist(self.concept, self.cfg):
            self.assertIn("no voices", shot.prompt)


class TestAssemble(unittest.TestCase):
    def test_target_dimensions(self):
        self.assertEqual(target_dimensions("9:16", "720p"), (720, 1280))
        self.assertEqual(target_dimensions("9:16", "1080p"), (1080, 1920))

    def test_wide_source_scales_by_height_then_crops(self):
        # The Veo-returns-16:9 case: must crop the sides, not letterbox.
        filt = build_video_filter(Dimensions(1280, 720), 720, 1280)
        self.assertIn("scale=-2:1280", filt)
        self.assertIn("crop=720:1280", filt)

    def test_matching_source_still_normalised(self):
        filt = build_video_filter(Dimensions(720, 1280), 720, 1280)
        self.assertIn("scale=720:-2", filt)
        self.assertIn("crop=720:1280", filt)

    def test_normalize_command_ducks_ambient_audio(self):
        cmd = build_normalize_command(
            Path("in.mp4"), Path("out.mp4"), Dimensions(1280, 720), 720, 1280,
            keep_audio=True, gain_db=-18.0,
        )
        self.assertIn("volume=-18.0dB,aresample=async=1", cmd)
        self.assertNotIn("-an", cmd)

    def test_normalize_command_can_strip_audio(self):
        cmd = build_normalize_command(
            Path("in.mp4"), Path("out.mp4"), Dimensions(720, 1280), 720, 1280,
            keep_audio=False, gain_db=-18.0,
        )
        self.assertIn("-an", cmd)

    def test_concat_uses_stream_copy(self):
        cmd = build_concat_command(Path("l.txt"), Path("o.mp4"), keep_audio=True)
        self.assertIn("concat", cmd)
        self.assertIn("-c", cmd)
        self.assertIn("copy", cmd)


class TestVoiceover(unittest.TestCase):
    def test_timecodes(self):
        self.assertEqual(format_timecode(0), "00:00.0")
        self.assertEqual(format_timecode(75.5), "01:15.5")
        self.assertEqual(format_timecode(8, srt=True), "00:00:08,000")

    def test_lines_are_keyed_to_shot_positions(self):
        lines = build_vo_lines(make_concept(shots=3), seconds_per_shot=8)
        self.assertEqual([(l.start_s, l.end_s) for l in lines],
                         [(0, 8), (8, 16), (16, 24)])

    def test_flags_line_too_long_to_speak(self):
        concept = make_concept(shots=1)
        concept.voiceover = [" ".join(["Wort"] * 60)]
        line = build_vo_lines(concept, seconds_per_shot=8)[0]
        self.assertTrue(line.is_too_long)
        self.assertIn("TOO LONG", render_script(concept, [line]))

    def test_normal_line_not_flagged(self):
        concept = make_concept(shots=1)
        concept.voiceover = ["Das hier hätte niemand filmen dürfen."]
        line = build_vo_lines(concept, seconds_per_shot=8)[0]
        self.assertFalse(line.is_too_long)

    def test_srt_skips_empty_lines(self):
        concept = make_concept(shots=3)
        concept.voiceover = ["first", "", "third"]
        srt = render_srt(build_vo_lines(concept, seconds_per_shot=8))
        self.assertIn("first", srt)
        self.assertIn("third", srt)
        self.assertEqual(srt.count("-->"), 2)

    def test_script_mentions_empty_shot_explicitly(self):
        concept = make_concept(shots=1)
        concept.voiceover = [""]
        script = render_script(concept, build_vo_lines(concept, 8))
        self.assertIn("no line", script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
