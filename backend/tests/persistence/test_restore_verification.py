from pathlib import Path

import pytest

from app.cli.verify_database_restore import (
    RestoreVerificationError,
    _require_nonzero_data_1_2_counts,
    _run_pg_tool,
    main,
)
from app.core.database_config import DatabaseSettings
from app.persistence.postgres.database_safety import (
    DestructiveDatabasePurpose,
    DestructiveDatabaseSafetyError,
    _validate_destructive_configuration,
)


LOCAL_URL = "postgresql+asyncpg://user:secret@localhost/quantkynd_test"


def settings(**updates) -> DatabaseSettings:
    return DatabaseSettings(
        database_url=LOCAL_URL,
        database_expected_integration_test_name="quantkynd_test",
        _env_file=None,
        **updates,
    )


def test_destructive_safety_defaults_to_denied() -> None:
    with pytest.raises(DestructiveDatabaseSafetyError, match="explicit opt-in"):
        _validate_destructive_configuration(
            LOCAL_URL,
            settings(database_allow_destructive_test_operations=False),
            DestructiveDatabasePurpose.INTEGRATION,
        )


@pytest.mark.parametrize("database_name", ["contest", "devops_prod", "restore_prod", "locality"])
def test_destructive_safety_rejects_substring_only_database_names(database_name: str) -> None:
    url = f"postgresql+asyncpg://user:secret@localhost/{database_name}"
    with pytest.raises(DestructiveDatabaseSafetyError, match="exact destructive expectation"):
        _validate_destructive_configuration(
            url,
            settings(database_allow_destructive_test_operations=True),
            DestructiveDatabasePurpose.INTEGRATION,
        )


def test_destructive_safety_requires_exact_expected_name() -> None:
    with pytest.raises(DestructiveDatabaseSafetyError, match="exact expected"):
        _validate_destructive_configuration(
            LOCAL_URL,
            DatabaseSettings(
                database_url=LOCAL_URL,
                database_allow_destructive_test_operations=True,
                database_expected_integration_test_name=None,
                _env_file=None,
            ),
            DestructiveDatabasePurpose.INTEGRATION,
        )


def test_destructive_safety_rejects_nonlocal_host_without_second_override() -> None:
    url = "postgresql+asyncpg://user:secret@database.internal/quantkynd_test"
    with pytest.raises(DestructiveDatabaseSafetyError, match="loopback host"):
        _validate_destructive_configuration(
            url,
            settings(database_allow_destructive_test_operations=True),
            DestructiveDatabasePurpose.INTEGRATION,
        )


def test_pg_tool_failure_masks_credentials_and_tool_output(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 1
        stdout = "secret"
        stderr = "postgresql+asyncpg://user:secret@localhost/quantkynd_test"

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Completed())
    with pytest.raises(RestoreVerificationError) as captured:
        _run_pg_tool(
            "pg_dump",
            LOCAL_URL,
            [f"--file={tmp_path / 'fixture.dump'}"],
        )
    assert "secret" not in str(captured.value)


def test_invalid_database_configuration_does_not_emit_credentials(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:secret@localhost/quantkynd_test?invalid=%",
    )
    assert main() == 1
    assert "secret" not in capsys.readouterr().out


def test_restore_requires_nonzero_data_1_2_counts() -> None:
    with pytest.raises(RestoreVerificationError, match="catalogue_ingestion_runs"):
        _require_nonzero_data_1_2_counts(
            {
                "catalogue_source_artifacts": 1,
                "catalogue_ingestion_runs": 0,
                "catalogue_row_outcomes": 1,
                "catalogue_memberships": 1,
            }
        )
