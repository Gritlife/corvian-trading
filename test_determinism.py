import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.providers.sample_data import generate_chain_for_scenario, stable_seed

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_stable_seed_is_deterministic_for_same_inputs():
    a = stable_seed("SPX", "SPX_DEFAULT_DEMO", "v1")
    b = stable_seed("SPX", "SPX_DEFAULT_DEMO", "v1")
    assert a == b


def test_stable_seed_differs_for_different_scenarios():
    a = stable_seed("SPX", "SPX_POSITIVE_GAMMA", "v1")
    b = stable_seed("SPX", "SPX_NEGATIVE_GAMMA", "v1")
    assert a != b


def test_deterministic_spx_scenario_reproducibility_in_process():
    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    chain1 = generate_chain_for_scenario("SPX", "SPX_DEFAULT_DEMO", as_of)
    chain2 = generate_chain_for_scenario("SPX", "SPX_DEFAULT_DEMO", as_of)
    assert len(chain1) == len(chain2)
    total_oi_1 = sum(c.open_interest for c in chain1)
    total_oi_2 = sum(c.open_interest for c in chain2)
    assert total_oi_1 == total_oi_2
    assert chain1[0].implied_volatility == chain2[0].implied_volatility


def test_deterministic_tsla_scenario_reproducibility_in_process():
    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    chain1 = generate_chain_for_scenario("TSLA", "TSLA_DEFAULT_DEMO", as_of)
    chain2 = generate_chain_for_scenario("TSLA", "TSLA_DEFAULT_DEMO", as_of)
    total_oi_1 = sum(c.open_interest for c in chain1)
    total_oi_2 = sum(c.open_interest for c in chain2)
    assert total_oi_1 == total_oi_2


def test_deterministic_seed_across_separate_processes():
    """Launches two independent Python subprocesses (each with a
    different PYTHONHASHSEED to defeat any accidental reliance on
    Python's randomized built-in hash()) and confirms identical output.
    This directly targets the v0.1 defect: hash()-based seeding is
    randomized per-process via PYTHONHASHSEED and is NOT reproducible.
    """
    script = (
        "from datetime import datetime, timezone; "
        "from app.providers.sample_data import generate_chain_for_scenario; "
        "chain = generate_chain_for_scenario('SPX', 'SPX_DEFAULT_DEMO', datetime(2026,1,1,tzinfo=timezone.utc)); "
        "print(sum(c.open_interest for c in chain))"
    )
    import os

    inherited_path = os.pathsep.join([str(REPO_ROOT)] + [p for p in sys.path if p])

    full_env1 = dict(os.environ)
    full_env1["PYTHONHASHSEED"] = "1"
    full_env1["PYTHONPATH"] = inherited_path

    full_env2 = dict(os.environ)
    full_env2["PYTHONHASHSEED"] = "99999"
    full_env2["PYTHONPATH"] = inherited_path

    result1 = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, env=full_env1, capture_output=True, text=True)
    result2 = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, env=full_env2, capture_output=True, text=True)

    assert result1.returncode == 0, result1.stderr
    assert result2.returncode == 0, result2.stderr
    assert result1.stdout.strip() == result2.stdout.strip()
