#!/usr/bin/env python3
"""Focused unit tests for function-parent pilot scoring invariants."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from function_profile_pilot import alignment_coverage,child_coverage_score,content_hash,reciprocal_rank_fusion

def test_child_coverage():
    matrix=np.asarray([[.9,.1],[.2,.8],[.4,.3]])
    assert abs(child_coverage_score(matrix)-.7)<1e-9
def test_one_to_one_penalizes_unmatched_child():
    score,pairs=alignment_coverage(np.asarray([[.9],[.8]]))
    assert abs(score-.45)<1e-9 and len(pairs)==1
def test_rrf_and_hash_stable():
    assert reciprocal_rank_fusion({"a":1,"b":None},60)==1/61
    assert content_hash({"b":2,"a":1})==content_hash({"a":1,"b":2})
if __name__=="__main__":
    test_child_coverage();test_one_to_one_penalizes_unmatched_child();test_rrf_and_hash_stable();print("ok")
