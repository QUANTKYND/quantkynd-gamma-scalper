"""Local artifact-store helpers for RV research runs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.rv import RVRunManifest, RVRunSummary


REQUIRED_COMPLETE_ARTIFACTS = (
    "manifest.json",
    "summary.json",
    "forecast-history.csv",
    "features.csv",
)


def stable_config_hash(config: dict[str, Any]) -> str:
    """Return a stable SHA-256 hash for normalized run configuration."""

    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def current_git_commit(repo_root: Path) -> str | None:
    """Return the current git commit, or ``None`` outside a git checkout."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None


class RVRunStore:
    """Read and write local persisted RV research-run artifacts."""

    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def list_manifests(self) -> list[RVRunManifest]:
        if not self.runs_dir.is_dir():
            return []

        manifests: list[RVRunManifest] = []
        for run_dir in sorted(self.runs_dir.iterdir()):
            if not run_dir.is_dir() or run_dir.name.startswith(".tmp-"):
                continue
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = RVRunManifest.model_validate_json(manifest_path.read_text())
            except (OSError, ValidationError, ValueError):
                continue
            if manifest.status == "complete" and not self._has_complete_artifacts(run_dir):
                continue
            manifests.append(manifest)

        return sorted(manifests, key=lambda item: item.created_at, reverse=True)

    def list_summaries(self) -> list[RVRunSummary]:
        return [
            RVRunSummary(
                run_id=manifest.run_id,
                created_at=manifest.created_at,
                completed_at=manifest.completed_at,
                status=manifest.status,
                symbol=manifest.symbol,
                dataset_id=manifest.dataset_id,
                estimator_id=manifest.estimator_id,
                model=manifest.model,
                model_parameters=manifest.model_parameters,
                horizon_sessions=manifest.horizon_sessions,
                evaluation_method=manifest.evaluation_method,
                failure_reason=manifest.failure_reason,
            )
            for manifest in self.list_manifests()
        ]

    def create_run(
        self,
        *,
        base_manifest: RVRunManifest,
        write_artifacts: Callable[[Path], RVRunManifest | dict[str, Any] | None],
    ) -> RVRunManifest:
        """Write a running manifest, artifacts, and final manifest atomically."""

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        final_dir = self.runs_dir / base_manifest.run_id
        temp_dir = self.runs_dir / f".tmp-{base_manifest.run_id}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if final_dir.exists():
            raise FileExistsError(f"run already exists: {final_dir}")

        temp_dir.mkdir(parents=True)
        running_manifest = base_manifest.model_copy(
            update={
                "status": "running",
                "completed_at": None,
                "artifact_directory": str(final_dir),
                "failure_reason": None,
            }
        )
        self._write_manifest(temp_dir, running_manifest)

        try:
            artifact_updates = write_artifacts(temp_dir)
            if isinstance(artifact_updates, RVRunManifest):
                completed = artifact_updates.model_copy(
                    update={
                        "status": "complete",
                        "completed_at": datetime.now(UTC),
                        "artifact_directory": str(final_dir),
                        "failure_reason": None,
                    }
                )
            else:
                manifest_updates = artifact_updates if isinstance(artifact_updates, dict) else {}
                completed = running_manifest.model_copy(
                    update={
                        **manifest_updates,
                        "status": "complete",
                        "completed_at": datetime.now(UTC),
                        "artifact_directory": str(final_dir),
                        "failure_reason": None,
                    }
                )
            self._write_manifest(temp_dir, completed)
            os.replace(temp_dir, final_dir)
            return completed
        except Exception as exc:
            failed = running_manifest.model_copy(
                update={
                    "status": "failed",
                    "completed_at": datetime.now(UTC),
                    "artifact_directory": str(final_dir),
                    "failure_reason": str(exc),
                }
            )
            self._write_manifest(temp_dir, failed)
            if final_dir.exists():
                shutil.rmtree(final_dir)
            os.replace(temp_dir, final_dir)
            return failed

    def _has_complete_artifacts(self, run_dir: Path) -> bool:
        return all((run_dir / name).is_file() for name in REQUIRED_COMPLETE_ARTIFACTS)

    @staticmethod
    def _write_manifest(run_dir: Path, manifest: RVRunManifest) -> None:
        payload = manifest.model_dump(mode="json")
        (run_dir / "manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        )
