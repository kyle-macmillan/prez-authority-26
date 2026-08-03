import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from path_dependency.classify_operative_children import (
    choose_policy, policy_metrics, rank_children, text_windows,
)


def test_policy_metrics_and_highest_coverage_selection():
    labels = {"1": "3", "2": "3", "3": "1", "4": "0"}
    rules = {
        "1": {"rule_positive": True}, "2": {"rule_positive": False},
        "3": {"rule_positive": False}, "4": {"rule_positive": False},
    }
    models = {
        "1": {"model_code3": True}, "2": {"model_code3": True},
        "3": {"model_code3": False}, "4": {"model_code3": False},
    }
    intersection = policy_metrics(labels, rules, models, "dual_model_plus_rule")
    model = policy_metrics(labels, rules, models, "dual_model")
    assert intersection["precision"] == 1.0
    assert model["precision"] == 1.0
    assert choose_policy([intersection, model])["policy"] == "dual_model"


def test_rank_children_is_deterministic_and_precision_first():
    ids = ["10", "2", "7"]
    rules = {x: {"rule_positive": x != "7"} for x in ids}
    models = {
        "10": {"model_code3": True, "minimum_code3_probability": .8,
               "maximum_code3_probability": .9},
        "2": {"model_code3": True, "minimum_code3_probability": .9,
              "maximum_code3_probability": .91},
        "7": {"model_code3": True, "minimum_code3_probability": .99,
              "maximum_code3_probability": .99},
    }
    assert rank_children(ids, "dual_model", rules, models) == ["2", "10", "7"]


def test_long_provisions_are_windowed_without_losing_the_end():
    text = "a" * 21_000 + "LEGAL END"
    windows = text_windows(text, size=10_000, overlap=500)
    assert len(windows) == 3
    assert windows[-1].endswith("LEGAL END")
    assert windows[0][-500:] == windows[1][:500]
