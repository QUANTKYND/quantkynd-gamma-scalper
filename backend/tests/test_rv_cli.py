from app.cli import run_rv_research
from app.services.rv_run_store import RVRunStore


def test_cli_persists_failed_manifest_before_snapshot_is_built(monkeypatch, tmp_path) -> None:
    def fail_snapshot(**_kwargs):
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(run_rv_research, "build_research_snapshot", fail_snapshot)

    code = run_rv_research.main(
        [
            "--symbol",
            "NIFTY",
            "--model",
            "ewma",
            "--horizon-sessions",
            "5",
            "--artifact-root",
            str(tmp_path / "rv"),
        ]
    )

    manifests = RVRunStore(tmp_path / "rv").list_manifests()
    assert code == 1
    assert len(manifests) == 1
    assert manifests[0].status == "failed"
    assert manifests[0].dataset_id == "pending"
    assert manifests[0].failure_reason == "snapshot failed"
