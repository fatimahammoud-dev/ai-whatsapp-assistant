import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mixed_language_samples.json"


def test_mixed_language_fixture_is_valid_and_reusable():
    samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8-sig"))

    assert len(samples) >= 6

    ids = [sample["id"] for sample in samples]
    assert len(ids) == len(set(ids))

    for sample in samples:
        assert sample["message"]
        assert sample["expected_tool"] == "check_availability"
        assert sample["expected_date"]

        preference = sample["expected_time_preference"]
        assert preference in {
            "morning",
            "afternoon",
            "evening",
            "any",
        }


def test_fixture_covers_required_language_styles():
    samples = json.loads(FIXTURE_PATH.read_text(encoding="utf-8-sig"))

    ids = {sample["id"] for sample in samples}

    assert "pure_arabic_tomorrow_afternoon" in ids
    assert "arabizi_tomorrow_afternoon" in ids
    assert "arabic_english_tomorrow_afternoon" in ids
    assert "french_arabic_tomorrow_morning" in ids
