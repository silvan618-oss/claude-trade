import os

from tiktok.memory import VideoMemory, VideoRecord, similarity


def make_memory(tmp_path) -> VideoMemory:
    return VideoMemory(
        str(tmp_path / "videos.jsonl"), str(tmp_path / "used.json"), str(tmp_path / "lessons.md")
    )


IDEA = {
    "topic": "Wie Wanderfalken im Sturzflug jagen",
    "subject": "Wanderfalke",
    "hook": "Er ist schneller als ein Formel-1-Wagen",
    "style": "Zeitlupe aus der Luft",
    "first_line": "Nichts auf diesem Planeten faellt schneller.",
}


def test_neue_idee_ist_keine_wiederholung(tmp_path):
    memory = make_memory(tmp_path)
    assert memory.repeat_reason("kanal", IDEA) == ""


def test_identische_idee_wird_blockiert(tmp_path):
    memory = make_memory(tmp_path)
    memory.remember("kanal", IDEA)
    assert "schon benutzt" in memory.repeat_reason("kanal", IDEA)


def test_umformulierte_idee_wird_als_zu_aehnlich_erkannt(tmp_path):
    memory = make_memory(tmp_path)
    memory.remember("kanal", IDEA)
    aehnlich = dict(IDEA, topic="Wie Wanderfalken jagen im Sturzflug", subject="Falke")
    assert memory.repeat_reason("kanal", aehnlich)


def test_anderer_kanal_teilt_das_gedaechtnis_nicht(tmp_path):
    memory = make_memory(tmp_path)
    memory.remember("kanal-a", IDEA)
    assert memory.repeat_reason("kanal-b", IDEA) == ""


def test_gedaechtnis_ueberlebt_neustart(tmp_path):
    make_memory(tmp_path).remember("kanal", IDEA)
    assert make_memory(tmp_path).repeat_reason("kanal", IDEA)


def test_avoid_block_listet_benutzte_subjekte(tmp_path):
    memory = make_memory(tmp_path)
    memory.remember("kanal", IDEA)
    block = memory.avoid_block("kanal")
    assert "Wanderfalke" in block and "Subjekte" in block


def test_avoid_block_ohne_historie(tmp_path):
    assert "freie Wahl" in make_memory(tmp_path).avoid_block("kanal")


def test_ledger_schreibt_jede_zeile(tmp_path):
    memory = make_memory(tmp_path)
    memory.append(VideoRecord(channel="k", topic="t", subject="s", hook="h", style="st"))
    memory.append(VideoRecord(channel="k", topic="t2", subject="s2", hook="h2", style="st2"))
    assert len(memory.all_records()) == 2


def test_lessons_werden_angehaengt(tmp_path):
    memory = make_memory(tmp_path)
    memory.add_lesson("Kein zweites Video ueber Wanderfalken.")
    assert "Wanderfalken" in memory.lessons()


def test_slug_ist_dateisystemtauglich():
    record = VideoRecord(channel="k", topic="Der Grosse Weisse Hai: Jagd bei Nacht!", subject="s", hook="h", style="st")
    assert " " not in record.slug and ":" not in record.slug
    assert record.slug.startswith(record.created_at[:10])


def test_similarity_grenzen():
    assert similarity("Wanderfalke im Sturzflug", "Wanderfalke im Sturzflug") == 1.0
    assert similarity("Wanderfalke im Sturzflug", "Tiefsee Anglerfisch Lockstoff") == 0.0
