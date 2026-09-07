import csv
from pathlib import Path

from rebuild_strict_holdout import rebuild, rebuild_from_holdout_ids, verify_complete_partition


def write_csv(path: Path, ids: range | list[int]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["", "url"])
        writer.writeheader()
        for document_id in ids:
            writer.writerow({"": document_id, "url": f"https://example.test/{document_id}"})


def test_rebuild_uses_prior_union_as_development(monkeypatch, tmp_path):
    master = tmp_path / "master.csv"
    dev = tmp_path / "dev.csv"
    holdout = tmp_path / "holdout.csv"
    write_csv(master, range(1, 7))
    write_csv(dev, [1, 2, 4])
    write_csv(holdout, [3])

    monkeypatch.setattr("rebuild_strict_holdout.EXPECTED_MASTER", 6)
    monkeypatch.setattr("rebuild_strict_holdout.EXPECTED_DEVELOPMENT", 4)
    monkeypatch.setattr("rebuild_strict_holdout.EXPECTED_HOLDOUT", 2)
    rebuilt_dev, rebuilt_holdout, manifest = rebuild(master, dev, holdout)

    assert [row[""] for row in rebuilt_dev] == ["1", "2", "3", "4"]
    assert [row[""] for row in rebuilt_holdout] == ["5", "6"]
    assert manifest["invariants"]["holdout_intersection_with_previously_used_partitions"] == 0


def test_rebuild_from_holdout_ids_preserves_complete_master(monkeypatch, tmp_path):
    master_path = tmp_path / "master.csv"
    write_csv(master_path, range(1, 7))
    with master_path.open(newline="", encoding="utf-8") as handle:
        master = list(csv.DictReader(handle))

    monkeypatch.setattr("rebuild_strict_holdout.EXPECTED_MASTER", 6)
    monkeypatch.setattr("rebuild_strict_holdout.EXPECTED_DEVELOPMENT", 4)
    monkeypatch.setattr("rebuild_strict_holdout.EXPECTED_HOLDOUT", 2)
    development, holdout, manifest = rebuild_from_holdout_ids(
        master, {5, 6}, "test-master",
    )

    assert [row[""] for row in development] == ["1", "2", "3", "4"]
    assert [row[""] for row in holdout] == ["5", "6"]
    assert development + holdout == master
    assert manifest["counts"] == {
        "master": 6,
        "development_exposed": 4,
        "holdout_unexposed": 2,
    }
    verify_complete_partition(master, development, holdout)


def test_partition_verification_rejects_changed_row(tmp_path):
    master_path = tmp_path / "master.csv"
    write_csv(master_path, [1, 2])
    with master_path.open(newline="", encoding="utf-8") as handle:
        master = list(csv.DictReader(handle))
    changed = [dict(master[0], url="https://example.test/changed")]

    try:
        verify_complete_partition(master, changed, [master[1]])
    except ValueError as error:
        assert "differs" in str(error)
    else:
        raise AssertionError("changed partition row was accepted")
