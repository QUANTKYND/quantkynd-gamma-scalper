from datetime import UTC, datetime

import pytest

from app.schemas.rv import RVRunManifest
from app.services.rv_run_store import RVRunStore, stable_config_hash


def _manifest(run_id: str = "rv-test") -> RVRunManifest:
    return RVRunManifest(
        run_id=run_id,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        completed_at=None,
        status="running",
        symbol="NIFTY",
        dataset_id="sha256:" + "a" * 64,
        estimator_id="close_to_close_squared_log_returns_v1",
        model="ewma",
        model_parameters={"ewma_span": 5},
        horizon_sessions=5,
        evaluation_method="sequential_non_overlapping_metrics",
        config_hash="sha256:" + "b" * 64,
        git_commit=None,
        artifact_directory="/tmp/rv-test",
        failure_reason=None,
    )


def test_stable_configuration_hash_ignores_key_order() -> None:
    first = stable_config_hash({"model": "ewma", "params": {"span": 5}})
    second = stable_config_hash({"params": {"span": 5}, "model": "ewma"})

    assert first == second
    assert first.startswith("sha256:")


def test_successful_manifest_creation_writes_artifacts(tmp_path) -> None:
    store = RVRunStore(tmp_path / "rv")

    completed = store.create_run(
        base_manifest=_manifest(),
        write_artifacts=lambda run_dir: [
            (run_dir / "summary.json").write_text("{}\n"),
            (run_dir / "forecast-history.csv").write_text("origin_date\n"),
            (run_dir / "features.csv").write_text("date\n"),
        ],
    )

    run_dir = store.runs_dir / completed.run_id
    assert completed.status == "complete"
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "forecast-history.csv").is_file()
    assert (run_dir / "features.csv").is_file()
    assert store.list_summaries()[0].run_id == completed.run_id


def test_failed_manifest_creation_records_failure(tmp_path) -> None:
    store = RVRunStore(tmp_path / "rv")

    def fail(_run_dir) -> None:
        raise RuntimeError("boom")

    failed = store.create_run(base_manifest=_manifest("rv-failed"), write_artifacts=fail)

    assert failed.status == "failed"
    assert failed.failure_reason == "boom"
    assert store.list_summaries()[0].status == "failed"


def test_incomplete_temporary_directories_are_not_listed(tmp_path) -> None:
    store = RVRunStore(tmp_path / "rv")
    temp_dir = store.runs_dir / ".tmp-rv-test"
    temp_dir.mkdir(parents=True)
    (temp_dir / "manifest.json").write_text(_manifest().model_dump_json())

    assert store.list_summaries() == []


def test_invalid_manifests_are_ignored(tmp_path) -> None:
    store = RVRunStore(tmp_path / "rv")
    run_dir = store.runs_dir / "rv-invalid"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text("{not json")

    assert store.list_summaries() == []


def test_complete_runs_missing_artifacts_are_ignored(tmp_path) -> None:
    store = RVRunStore(tmp_path / "rv")
    run_dir = store.runs_dir / "rv-incomplete"
    run_dir.mkdir(parents=True)
    manifest = _manifest("rv-incomplete").model_copy(
        update={"status": "complete", "completed_at": datetime(2025, 1, 1, tzinfo=UTC)}
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json())

    assert store.list_summaries() == []


def test_create_run_rejects_existing_run_directory(tmp_path) -> None:
    store = RVRunStore(tmp_path / "rv")
    (store.runs_dir / "rv-test").mkdir(parents=True)

    with pytest.raises(FileExistsError):
        store.create_run(base_manifest=_manifest(), write_artifacts=lambda _run_dir: None)
