import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from analysis.qwen_reranker_comparison import summarize


def test_summarizes_top_rank_agreement():
    rows = [
        {"child_id":"c","parent_id":"a","rrf_rank":"1","qwen_full_operative_rank":"2","qwen_matched_pairs_rank":"1"},
        {"child_id":"c","parent_id":"b","rrf_rank":"2","qwen_full_operative_rank":"1","qwen_matched_pairs_rank":"2"},
    ]
    result = summarize(rows)
    assert result == {"children":1,"pairs":2,"full_matched_agreement":0,"full_rrf_agreement":0,"matched_rrf_agreement":1}
