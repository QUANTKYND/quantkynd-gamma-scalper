from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.simulation.artifacts import REQUIRED_SIMULATION_ARTIFACTS, SimulationManifest, write_manifest


RUN_ID_PATTERN = re.compile(r"^sim-[a-f0-9]{20}$")


class SimulationRunStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def list_manifests(self) -> list[SimulationManifest]:
        if not self.runs_dir.is_dir():
            return []
        manifests = []
        for run_dir in sorted(self.runs_dir.iterdir()):
            if not run_dir.is_dir() or run_dir.name.startswith(".tmp-"):
                continue
            try:
                manifest = SimulationManifest.model_validate_json((run_dir / "manifest.json").read_text())
            except (OSError, ValueError, ValidationError):
                continue
            if manifest.status == "complete" and not all((run_dir / name).is_file() for name in REQUIRED_SIMULATION_ARTIFACTS):
                continue
            manifests.append(manifest)
        return sorted(manifests, key=lambda item: item.created_at, reverse=True)

    def create_run(
        self,
        base_manifest: SimulationManifest,
        write_artifacts: Callable[[Path], None],
    ) -> SimulationManifest:
        if not RUN_ID_PATTERN.fullmatch(base_manifest.run_id):
            raise ValueError("invalid simulation run ID")
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        final_dir = self.runs_dir / base_manifest.run_id
        temp_dir = self.runs_dir / f".tmp-{base_manifest.run_id}"
        if final_dir.exists():
            raise FileExistsError(f"immutable simulation run already exists: {final_dir}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir()
        running = base_manifest.model_copy(
            update={
                "status": "running",
                "completed_at": None,
                "artifact_directory": str(final_dir),
                "failure_reason": None,
            }
        )
        write_manifest(temp_dir / "manifest.json", running)
        try:
            write_artifacts(temp_dir)
            completed = running.model_copy(update={"status": "complete", "completed_at": datetime.now(UTC)})
            write_manifest(temp_dir / "manifest.json", completed)
            os.replace(temp_dir, final_dir)
            return completed
        except Exception as exc:
            failed = running.model_copy(
                update={"status": "failed", "completed_at": datetime.now(UTC), "failure_reason": str(exc)}
            )
            write_manifest(temp_dir / "manifest.json", failed)
            os.replace(temp_dir, final_dir)
            return failed
