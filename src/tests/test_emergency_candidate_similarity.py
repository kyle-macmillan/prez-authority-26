import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "analysis"))

from emergency_candidate_similarity import is_emergency_authority


def test_emergency_authority_matching():
    assert is_emergency_authority(
        "By the authority vested in me under the National Emergencies Act, and in order to act,",
        "executive_order",
    )
    assert is_emergency_authority(
        "By the authority vested in me under the National Emergencies Act (NEA), and in order to act,",
        "executive_order",
    )
    assert not is_emergency_authority("This directive later discusses the National Emergencies Act.", "executive_order")
    assert not is_emergency_authority(
        "By the authority vested in me by the Constitution, and in order to act; funding for the NEA.",
        "executive_order",
    )
    assert not is_emergency_authority("By the authority vested in me by the Constitution, and in order to act.", "executive_order")


if __name__ == "__main__":
    test_emergency_authority_matching()
    print("1 passed")
