import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "analysis"))

from emergency_candidate_similarity import is_emergency_authority


def test_emergency_authority_matching():
    assert is_emergency_authority("under the National Emergencies Act")
    assert is_emergency_authority("under the National Emergencies Act (NEA)")
    assert not is_emergency_authority("funding for the NEA")
    assert not is_emergency_authority("a national emergency exists")
    assert not is_emergency_authority("the LINEAR statute")


if __name__ == "__main__":
    test_emergency_authority_matching()
    print("1 passed")
