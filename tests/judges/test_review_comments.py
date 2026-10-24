"""The review-comments judge returns the labelled verdict for each diff."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from conventions_hooks.review import ask_claude, review, rules

REPO = Path(__file__).resolve().parents[2]
CASES = yaml.safe_load(
    Path(__file__).with_name("review_comments_cases.yaml").read_text()
)

pytestmark = pytest.mark.judges


@pytest.fixture(scope="module")
def answers() -> dict[str, tuple[bool, str]]:
    guide = rules(REPO)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = pool.map(lambda c: review(c["diff"], guide, ask=ask_claude), CASES)
        return {case["id"]: result for case, result in zip(CASES, results, strict=True)}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_the_verdict_matches_the_label(case, answers):
    passed, answer = answers[case["id"]]

    assert ("PASS" if passed else "FAIL") == case["label"], answer
