"""Подбор весов по логу: арифметика, а не рекомендации.

Скрипт отвечает на вопрос «что было бы при других весах» по уже
случившимся сделкам, поэтому проверяем именно счёт: кого порог сохраняет,
кого теряет и что попадает в кандидаты.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tune


def scores(audit=0.8, narrative=0.8, timing=0.8, metrics=0.8, total=0.8) -> dict:
    return {"audit": audit, "narrative": narrative, "timing": timing,
            "metrics": metrics, "total": total}


def write_log(tmp_path: Path, records: list[dict]) -> str:
    path = tmp_path / "trades.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")
    return str(path)


# --- сетка весов ----------------------------------------------------------


def test_simplex_sums_to_one():
    grid = tune.simplex(0.1)
    assert all(sum(weights) == pytest.approx(1.0) for weights in grid)
    assert (1.0, 0.0, 0.0, 0.0) in grid
    assert len(grid) == 286


def test_finer_step_gives_more_sets():
    assert len(tune.simplex(0.05)) > len(tune.simplex(0.1))


def test_total_is_weighted_sum():
    assert tune.total((1.0, 0.0, 0.5, 0.0), (0.5, 0.2, 0.2, 0.1)) == pytest.approx(0.6)


# --- чтение лога ----------------------------------------------------------


def test_candidates_join_buys_with_their_outcome(tmp_path):
    log = write_log(tmp_path, [
        {"type": "buy", "mint": "A", "scores": scores(), "ts": 1},
        {"type": "close", "mint": "A", "pnl_sol": 0.25, "ts": 2},
        {"type": "skip", "mint": "B", "stage": "scoring", "scores": scores(total=0.4), "ts": 3},
    ])
    candidates = tune.load_candidates(log, rotated=False)
    assert len(candidates) == 2
    bought = next(c for c in candidates if c.mint == "A")
    assert bought.bought and bought.pnl_sol == 0.25
    skipped = next(c for c in candidates if c.mint == "B")
    assert not skipped.bought and skipped.pnl_sol is None


def test_records_without_scores_are_ignored(tmp_path):
    log = write_log(tmp_path, [
        {"type": "skip", "mint": "A", "stage": "monitor", "reason": "few_buyers", "ts": 1},
        {"type": "skip", "mint": "B", "stage": "scoring", "scores": scores(), "ts": 2},
    ])
    assert [c.mint for c in tune.load_candidates(log, rotated=False)] == ["B"]


def test_same_mint_counted_once(tmp_path):
    log = write_log(tmp_path, [
        {"type": "skip", "mint": "A", "stage": "scoring", "scores": scores(), "ts": 1},
        {"type": "skip", "mint": "A", "stage": "checker", "scores": scores(), "ts": 2},
    ])
    assert len(tune.load_candidates(log, rotated=False)) == 1


def test_partial_closes_are_summed(tmp_path):
    log = write_log(tmp_path, [
        {"type": "buy", "mint": "A", "scores": scores(), "ts": 1},
        {"type": "close", "mint": "A", "pnl_sol": 0.2, "ts": 2},
        {"type": "close", "mint": "A", "pnl_sol": -0.05, "ts": 3},
    ])
    assert tune.load_candidates(log, rotated=False)[0].pnl_sol == pytest.approx(0.15)


# --- оценка ---------------------------------------------------------------


def candidates() -> list[tune.Candidate]:
    return [
        tune.Candidate("хорошая", (0.9, 0.9, 0.9, 0.9), True, +1.0),
        tune.Candidate("плохая", (0.4, 0.4, 0.4, 0.4), True, -0.5),
        tune.Candidate("неторгованная", (0.7, 0.7, 0.7, 0.7), False, None),
    ]


def test_threshold_splits_kept_and_lost():
    weights = (0.25, 0.25, 0.25, 0.25)
    outcome = tune.evaluate(candidates(), weights, threshold=0.5)
    assert outcome.passed == 2                 # хорошая и неторгованная
    assert (outcome.kept_trades, outcome.kept_pnl) == (1, 1.0)
    assert (outcome.lost_trades, outcome.lost_pnl) == (1, -0.5)


def test_score_rewards_cutting_losers():
    """Порог, отрезающий убыточную сделку, должен оцениваться выше."""
    weights = (0.25, 0.25, 0.25, 0.25)
    loose = tune.evaluate(candidates(), weights, threshold=0.3)
    tight = tune.evaluate(candidates(), weights, threshold=0.5)
    assert loose.kept_trades == 2
    assert tight.score > loose.score


def test_everything_below_threshold_keeps_nothing():
    outcome = tune.evaluate(candidates(), (0.25, 0.25, 0.25, 0.25), threshold=0.99)
    assert outcome.passed == 0 and outcome.kept_trades == 0


def test_rank_prefers_less_degenerate_weights():
    """При равном результате балансированный набор бьёт вес 1.00 на одном."""
    outcome = tune.Outcome(passed=2, kept_trades=2, kept_pnl=1.0, lost_trades=0, lost_pnl=0.0)
    balanced = (outcome, (0.25, 0.25, 0.25, 0.25), 0.65)
    degenerate = (outcome, (1.0, 0.0, 0.0, 0.0), 0.65)
    assert tune.rank(balanced) > tune.rank(degenerate)


def test_current_weights_normalized_from_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("scoring:\n  weights:\n    audit: 2\n    narrative: 2\n"
                      "    timing: 2\n    metrics: 2\n")
    assert tune.current_weights(str(config)) == (0.25, 0.25, 0.25, 0.25)


def test_current_weights_fall_back_to_defaults(tmp_path):
    weights = tune.current_weights(str(tmp_path / "нет.yaml"))
    assert sum(weights) == pytest.approx(1.0)


def test_empty_log_exits_with_error(tmp_path, monkeypatch, capsys):
    log = tmp_path / "пусто.jsonl"
    log.write_text("")
    monkeypatch.setattr(sys, "argv", ["tune.py", str(log)])
    assert tune.main() == 1
    assert "нет записей" in capsys.readouterr().out


def test_main_runs_on_real_shaped_log(tmp_path, monkeypatch, capsys):
    records = []
    for index in range(40):
        mint = f"M{index}"
        good = index % 3 == 0
        records.append({"type": "buy" if good else "skip", "mint": mint, "ts": index,
                        "stage": "scoring", "scores": scores(total=0.9 if good else 0.5)})
        if good:
            records.append({"type": "close", "mint": mint, "pnl_sol": 0.1, "ts": index + 0.5})
    log = write_log(tmp_path, records)
    monkeypatch.setattr(sys, "argv", ["tune.py", log, "--top", "3"])
    assert tune.main() == 0
    printed = capsys.readouterr().out
    assert "Порог при текущих весах" in printed
    assert "Лучшие 3" in printed
