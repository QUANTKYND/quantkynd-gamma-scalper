from pathlib import Path

import pytest

from app.cli.verify_database_restore import (
    RestoreVerificationError,
    _require_test_safe,
    _run_pg_tool,
)


def test_restore_safety_rejects_non_test_database() -> None:
    with pytest.raises(RestoreVerificationError, match="test-safe"):
        _require_test_safe("postgresql+asyncpg://user:secret@localhost/quantkynd")


def test_pg_tool_failure_masks_credentials_and_tool_output(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 1
        stdout = "secret"
        stderr = "postgresql+asyncpg://user:secret@localhost/quantkynd_test"

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Completed())
    with pytest.raises(RestoreVerificationError) as captured:
        _run_pg_tool(
            "pg_dump",
            "postgresql+asyncpg://user:secret@localhost/quantkynd_test",
            [f"--file={tmp_path / 'fixture.dump'}"],
        )
    assert "secret" not in str(captured.value)
