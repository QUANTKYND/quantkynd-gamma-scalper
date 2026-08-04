from types import SimpleNamespace

import pytest

from app.persistence.postgres.fixtures import deterministic_fixture
from app.persistence.postgres.mappings import (
    MalformedPersistenceRecordError,
    catalogue_from_row,
    catalogue_values,
    future_from_rows,
    future_values,
    market_instrument_values,
    option_from_rows,
    option_values,
    provider_mapping_from_row,
    provider_mapping_values,
    temporal_record_values,
    trading_session_from_row,
    trading_session_values,
    trading_session_version_from_row,
    trading_session_version_values,
    underlying_from_rows,
    underlying_values,
    version_from_row,
    version_values,
)
from app.instruments.temporal_records import (
    catalogue_temporal_record,
    instrument_version_temporal_record,
    provider_mapping_temporal_record,
    trading_session_version_temporal_record,
)


def row(values):
    return SimpleNamespace(**values)


def test_all_data_foundation_models_round_trip_exactly() -> None:
    fixture = deterministic_fixture()
    assert catalogue_from_row(
        row(catalogue_values(fixture.catalogue)),
        row(temporal_record_values(catalogue_temporal_record(fixture.catalogue), "catalogue_version_id")),
    ) == fixture.catalogue
    assert underlying_from_rows(
        row(market_instrument_values(fixture.underlying)),
        row(underlying_values(fixture.underlying)),
    ) == fixture.underlying
    assert future_from_rows(
        row(market_instrument_values(fixture.future)),
        row(future_values(fixture.future)),
    ) == fixture.future
    assert option_from_rows(
        row(market_instrument_values(fixture.option)),
        row(option_values(fixture.option)),
    ) == fixture.option
    assert version_from_row(
        row(version_values(fixture.underlying_version)),
        row(temporal_record_values(instrument_version_temporal_record(fixture.underlying_version), "version_id")),
        "underlying",
    ) == fixture.underlying_version
    assert version_from_row(
        row(version_values(fixture.future_version)),
        row(temporal_record_values(instrument_version_temporal_record(fixture.future_version), "version_id")),
        "future",
    ) == fixture.future_version
    assert version_from_row(
        row(version_values(fixture.option_version)),
        row(temporal_record_values(instrument_version_temporal_record(fixture.option_version), "version_id")),
        "option",
    ) == fixture.option_version
    assert provider_mapping_from_row(
        row(provider_mapping_values(fixture.provider_mapping)),
        row(temporal_record_values(provider_mapping_temporal_record(fixture.provider_mapping), "mapping_id")),
    ) == fixture.provider_mapping
    assert trading_session_from_row(row(trading_session_values(fixture.session))) == fixture.session
    assert trading_session_version_from_row(
        row(trading_session_version_values(fixture.session_version)),
        row(temporal_record_values(trading_session_version_temporal_record(fixture.session_version), "session_version_id")),
    ) == fixture.session_version


def test_decimal_precision_and_nullable_values_are_preserved() -> None:
    fixture = deterministic_fixture()
    option = option_from_rows(
        row(market_instrument_values(fixture.option)),
        row(option_values(fixture.option)),
    )
    version = version_from_row(
        row(version_values(fixture.option_version)),
        row(temporal_record_values(instrument_version_temporal_record(fixture.option_version), "version_id")),
        "option",
    )
    assert option.strike == fixture.option.strike
    assert version.tick_size == fixture.option_version.tick_size
    assert version.valid_until is None
    assert fixture.provider_mapping.source_row_identity is not None


def test_malformed_durable_row_fails_explicitly() -> None:
    fixture = deterministic_fixture()
    values = option_values(fixture.option)
    values["strike"] = -fixture.option.strike
    with pytest.raises(MalformedPersistenceRecordError, match="OptionContractIdentity"):
        option_from_rows(row(market_instrument_values(fixture.option)), row(values))


def test_invalid_enum_and_deterministic_id_mismatch_fail_explicitly() -> None:
    fixture = deterministic_fixture()
    values = option_values(fixture.option)
    values["option_side"] = "unsupported"
    with pytest.raises(MalformedPersistenceRecordError, match="OptionContractIdentity"):
        option_from_rows(row(market_instrument_values(fixture.option)), row(values))
    catalogue_row = catalogue_values(fixture.catalogue)
    catalogue_row["catalogue_version_id"] = "sha256:" + "f" * 64
    with pytest.raises(MalformedPersistenceRecordError, match="identity"):
        catalogue_from_row(
            row(catalogue_row),
            row(temporal_record_values(catalogue_temporal_record(fixture.catalogue), "catalogue_version_id")),
        )
