from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.persistence.postgres.base import Base
from app.persistence.postgres import models as _postgres_models


DATA15_TABLES = {
    "market_data_quality_policies",
    "market_data_quality_policy_versions",
    "market_data_quality_policy_source_artifacts",
    "market_data_quality_policy_reason_definitions",
    "market_data_quality_assessment_runs",
    "market_data_quality_assessments",
    "market_data_quality_assessment_reasons",
    "market_data_quality_assessment_dependencies",
    "market_data_quality_dependency_candidates",
    "market_data_quality_run_assessments",
    "market_data_quality_provider_mapping_receipts",
    "market_data_quality_instrument_version_receipts",
    "market_data_quality_catalogue_version_receipts",
    "market_data_quality_trading_session_receipts",
    "market_data_quality_catalogue_membership_receipts",
}


def test_data15_metadata_registers_exact_table_set():
    assert DATA15_TABLES <= set(Base.metadata.tables)


def test_data15_receipts_have_exact_primary_keys_and_targets():
    targets = {
        "market_data_quality_provider_mapping_receipts": "provider_mapping_records",
        "market_data_quality_instrument_version_receipts": "instrument_version_records",
        "market_data_quality_catalogue_version_receipts": "catalogue_version_records",
        "market_data_quality_trading_session_receipts": "trading_session_version_records",
    }
    for table_name, target_name in targets.items():
        table = Base.metadata.tables[table_name]
        assert tuple(column.name for column in table.primary_key.columns) == ("record_id",)
        assert any(
            isinstance(constraint, ForeignKeyConstraint)
            and {element.column.table.name for element in constraint.elements}
            == {target_name}
            for constraint in table.constraints
        )
        assert {
            "receipt_at",
            "receipt_basis",
            "bootstrap_revision",
            "canonical_payload_hash",
        } <= set(table.c.keys())

    membership = Base.metadata.tables[
        "market_data_quality_catalogue_membership_receipts"
    ]
    assert tuple(column.name for column in membership.primary_key.columns) == (
        "membership_id",
    )
    assert {"membership_id", "ingestion_run_id"} <= set(membership.c.keys())


def test_data15_candidate_table_uses_typed_fk_columns():
    table = Base.metadata.tables["market_data_quality_dependency_candidates"]
    expected = {
        "market_event_id",
        "market_result_id",
        "market_raw_event_id",
        "provider_mapping_record_id",
        "provider_mapping_id",
        "instrument_version_record_id",
        "instrument_version_id",
        "catalogue_record_id",
        "catalogue_version_id",
        "catalogue_ingestion_run_id",
        "catalogue_membership_id",
        "membership_ingestion_run_id",
        "trading_session_record_id",
        "trading_session_version_id",
        "lifecycle_event_id",
        "lifecycle_kind",
        "lifecycle_batch_id",
        "instrument_keys_digest",
    }
    assert expected <= set(table.c.keys())
    assert len(
        [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        ]
    ) >= 10


def test_trading_session_record_has_exact_record_semantic_unique_key():
    table = Base.metadata.tables["trading_session_version_records"]
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_trading_session_version_records_record_semantic"
        and tuple(column.name for column in constraint.columns)
        == ("record_id", "session_version_id")
        for constraint in table.constraints
    )
