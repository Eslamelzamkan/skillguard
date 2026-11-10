"""The lift math is the competition's own metric - verify it directly."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("measure_lift", REPO / "lab" / "measure_lift.py")
measure_lift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure_lift)


def test_normalized_lift_matches_competition_formula():
    # g = (pass_skill - pass_vanilla) / (1 - pass_vanilla)
    assert measure_lift.normalized_lift(0.0, 1.0) == 1.0          # 0 -> full = perfect lift
    assert measure_lift.normalized_lift(0.5, 0.75) == 0.5          # closes half the gap
    assert measure_lift.normalized_lift(0.5, 0.25) == -0.5         # regression -> negative
    assert measure_lift.normalized_lift(0.5, 0.5) == 0.0           # no change


def test_normalized_lift_no_headroom_is_zero_not_divide_by_zero():
    # vanilla already passes every time -> denominator 0 -> defined as 0, no crash
    assert measure_lift.normalized_lift(1.0, 1.0) == 0.0


def test_passed_respects_binary_threshold():
    assert measure_lift.passed(1.0, 1.0) is True
    assert measure_lift.passed(0.0, 1.0) is False
    assert measure_lift.passed(None, 1.0) is False  # errored rollout != pass


def test_rollout_reward_reads_canonical_schema(tmp_path):
    # mirrors the real result.json: rewards.reward is the terminal scalar
    r = tmp_path / "rollout"
    r.mkdir()
    (r / "result.json").write_text(
        '{"task_name":"t","rewards":{"reward":1},"n_skill_invocations":2,"error":null}',
        encoding="utf-8")
    reward, invoked, error = measure_lift.rollout_reward(tmp_path)
    assert reward == 1 and invoked == 2 and error is None
