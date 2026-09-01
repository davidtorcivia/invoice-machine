"""The money and date arithmetic must not drift.

tests/golden/*.json pin the exact output of every pure function that decides
what a customer is charged. A failure means the charged amounts changed: fix the
bug, or regenerate with `python tests/golden/generate.py` and review the diff
line by line. Never regenerate to make this pass -- the diff is the change.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"
GENERATOR = GOLDEN_DIR / "generate.py"

sys.path.insert(0, str(GOLDEN_DIR))

from generate import BUILDERS, serialize  # noqa: E402


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_golden_matches_current_behavior(name):
    """Recompute the matrix and compare it to the committed golden."""
    path = GOLDEN_DIR / name
    assert path.exists(), f"missing golden {name}; run python tests/golden/generate.py"

    expected = path.read_text(encoding="utf-8")
    actual = serialize(BUILDERS[name]())

    if expected == actual:
        return

    exp, act = json.loads(expected), json.loads(actual)
    diffs = []
    for group in sorted(set(exp) | set(act)):
        e, a = exp.get(group, {}), act.get(group, {})
        for key in sorted(set(e) | set(a)):
            if e.get(key) != a.get(key):
                diffs.append(f"  {group}[{key}]: {e.get(key)!r} -> {a.get(key)!r}")
    pytest.fail(
        f"{name} drifted ({len(diffs)} value(s) changed):\n"
        + "\n".join(diffs[:40])
        + (f"\n  ... {len(diffs) - 40} more" if len(diffs) > 40 else "")
        + "\n\nIf intended: python tests/golden/generate.py, then review the diff."
    )


def test_generator_is_deterministic():
    """Two runs must produce identical bytes."""
    for name, builder in BUILDERS.items():
        assert serialize(builder()) == serialize(builder()), f"{name} is not deterministic"


def test_generator_check_mode_passes():
    """`generate.py --check` is the CI gate; it must agree with the committed files."""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=str(GOLDEN_DIR.parents[1]),
    )
    assert result.returncode == 0, f"--check failed:\n{result.stdout}\n{result.stderr}"
