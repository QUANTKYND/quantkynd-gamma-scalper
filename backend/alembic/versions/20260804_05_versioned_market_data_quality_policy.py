from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
import hashlib
import json
from typing import Any, Mapping

from alembic import op
import sqlalchemy as sa


revision = "20260804_05"
down_revision = "20260804_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DATA15_TABLES = (
    "market_data_quality_provider_mapping_receipts",
    "market_data_quality_instrument_version_receipts",
    "market_data_quality_catalogue_version_receipts",
    "market_data_quality_trading_session_receipts",
    "market_data_quality_catalogue_membership_receipts",
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
)

RECEIPT_TARGETS = (
    (
        "provider_mapping_records",
        "market_data_quality_provider_mapping_receipts",
        "provider_mapping_record",
        "data15_provider_mapping_receipt_complete",
    ),
    (
        "instrument_version_records",
        "market_data_quality_instrument_version_receipts",
        "instrument_version_record",
        "data15_instrument_version_receipt_complete",
    ),
    (
        "catalogue_version_records",
        "market_data_quality_catalogue_version_receipts",
        "catalogue_version_record",
        "data15_catalogue_version_receipt_complete",
    ),
    (
        "trading_session_version_records",
        "market_data_quality_trading_session_receipts",
        "trading_session_record",
        "data15_trading_session_receipt_complete",
    ),
)

DATA15_FUNCTIONS = (
    "data15_reject_row_mutation",
    "data15_reject_truncate",
    "data15_validate_receipt_completeness",
    "data15_validate_policy_reason_registry",
    "data15_validate_assessment_aggregate",
    "data15_validate_dependency_aggregate",
    "data15_validate_run_membership",
)

SCHEMA_DDL = (
    "CREATE TABLE market_data_quality_provider_mapping_receipts (\n\trecord_id VARCHAR(71) NOT NULL, \n\treceipt_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\treceipt_basis VARCHAR(32) NOT NULL, \n\tbootstrap_revision VARCHAR(32), \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_provider_mapping_receipts PRIMARY KEY (record_id), \n\tCONSTRAINT fk_data15_mapping_receipts_record FOREIGN KEY(record_id) REFERENCES provider_mapping_records (record_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_market_data_quality_provider_mapping_receipts_record_sha256 CHECK (record_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_provider_mapping_receipts_payloa_39e4 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_provider_mapping_receipts_receipt_finite CHECK (receipt_at <> 'infinity'::timestamptz AND receipt_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_market_data_quality_provider_mapping_receipts_basis_shape CHECK ((receipt_basis = 'legacy_bootstrap' AND bootstrap_revision = '20260804_05') OR (receipt_basis = 'repository_insert' AND bootstrap_revision IS NULL))\n);",
    'CREATE INDEX ix_market_data_quality_provider_mapping_receipts_receipt ON market_data_quality_provider_mapping_receipts (receipt_at, record_id);',
    "CREATE TABLE market_data_quality_instrument_version_receipts (\n\trecord_id VARCHAR(71) NOT NULL, \n\treceipt_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\treceipt_basis VARCHAR(32) NOT NULL, \n\tbootstrap_revision VARCHAR(32), \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_instrument_version_receipts PRIMARY KEY (record_id), \n\tCONSTRAINT fk_data15_instrument_receipts_record FOREIGN KEY(record_id) REFERENCES instrument_version_records (record_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_market_data_quality_instrument_version_receipts_reco_50ee CHECK (record_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_instrument_version_receipts_payl_58b2 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_instrument_version_receipts_rece_c0b1 CHECK (receipt_at <> 'infinity'::timestamptz AND receipt_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_market_data_quality_instrument_version_receipts_basis_shape CHECK ((receipt_basis = 'legacy_bootstrap' AND bootstrap_revision = '20260804_05') OR (receipt_basis = 'repository_insert' AND bootstrap_revision IS NULL))\n);",
    'CREATE INDEX ix_market_data_quality_instrument_version_receipts_receipt ON market_data_quality_instrument_version_receipts (receipt_at, record_id);',
    "CREATE TABLE market_data_quality_catalogue_version_receipts (\n\trecord_id VARCHAR(71) NOT NULL, \n\treceipt_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\treceipt_basis VARCHAR(32) NOT NULL, \n\tbootstrap_revision VARCHAR(32), \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_catalogue_version_receipts PRIMARY KEY (record_id), \n\tCONSTRAINT fk_data15_catalogue_receipts_record FOREIGN KEY(record_id) REFERENCES catalogue_version_records (record_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_market_data_quality_catalogue_version_receipts_record_sha256 CHECK (record_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_catalogue_version_receipts_paylo_f92f CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_catalogue_version_receipts_recei_de90 CHECK (receipt_at <> 'infinity'::timestamptz AND receipt_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_market_data_quality_catalogue_version_receipts_basis_shape CHECK ((receipt_basis = 'legacy_bootstrap' AND bootstrap_revision = '20260804_05') OR (receipt_basis = 'repository_insert' AND bootstrap_revision IS NULL))\n);",
    'CREATE INDEX ix_market_data_quality_catalogue_version_receipts_receipt ON market_data_quality_catalogue_version_receipts (receipt_at, record_id);',
    "CREATE TABLE market_data_quality_trading_session_receipts (\n\trecord_id VARCHAR(71) NOT NULL, \n\treceipt_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\treceipt_basis VARCHAR(32) NOT NULL, \n\tbootstrap_revision VARCHAR(32), \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_trading_session_receipts PRIMARY KEY (record_id), \n\tCONSTRAINT fk_data15_session_receipts_record FOREIGN KEY(record_id) REFERENCES trading_session_version_records (record_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_market_data_quality_trading_session_receipts_record_sha256 CHECK (record_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_trading_session_receipts_payload_66cf CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_market_data_quality_trading_session_receipts_receipt_finite CHECK (receipt_at <> 'infinity'::timestamptz AND receipt_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_market_data_quality_trading_session_receipts_basis_shape CHECK ((receipt_basis = 'legacy_bootstrap' AND bootstrap_revision = '20260804_05') OR (receipt_basis = 'repository_insert' AND bootstrap_revision IS NULL))\n);",
    'CREATE INDEX ix_market_data_quality_trading_session_receipts_receipt ON market_data_quality_trading_session_receipts (receipt_at, record_id);',
    "CREATE TABLE market_data_quality_catalogue_membership_receipts (\n\tmembership_id VARCHAR(71) NOT NULL, \n\tingestion_run_id VARCHAR(71) NOT NULL, \n\treceipt_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\treceipt_basis VARCHAR(32) NOT NULL, \n\tbootstrap_revision VARCHAR(32), \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_catalogue_membership_receipts PRIMARY KEY (membership_id), \n\tCONSTRAINT fk_data15_membership_receipts_membership FOREIGN KEY(membership_id) REFERENCES catalogue_memberships (membership_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_membership_receipts_run FOREIGN KEY(ingestion_run_id) REFERENCES catalogue_ingestion_runs (ingestion_run_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_membership_receipts_id_sha256 CHECK (membership_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_membership_receipts_run_sha256 CHECK (ingestion_run_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_membership_receipts_payload_hash_sha256 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_membership_receipts_receipt_finite CHECK (receipt_at <> 'infinity'::timestamptz AND receipt_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_membership_receipts_basis_shape CHECK ((receipt_basis = 'legacy_bootstrap' AND bootstrap_revision = '20260804_05') OR (receipt_basis = 'repository_insert' AND bootstrap_revision IS NULL)), \n\tCONSTRAINT uq_data15_membership_receipts_exact UNIQUE (membership_id, ingestion_run_id)\n);",
    'CREATE INDEX ix_data15_membership_receipts_receipt ON market_data_quality_catalogue_membership_receipts (receipt_at, membership_id);',
    "CREATE TABLE market_data_quality_policies (\n\tpolicy_id VARCHAR(71) NOT NULL, \n\tpolicy_name VARCHAR(128) NOT NULL, \n\tprovider VARCHAR(128) NOT NULL, \n\tobservation_domain VARCHAR(128) NOT NULL, \n\tcanonical_payload JSONB NOT NULL, \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tregistered_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_market_data_quality_policies PRIMARY KEY (policy_id), \n\tCONSTRAINT ck_data15_policies_id_sha256 CHECK (policy_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policies_payload_hash_sha256 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policies_payload_object CHECK (jsonb_typeof(canonical_payload) = 'object'), \n\tCONSTRAINT ck_data15_policies_registered_finite CHECK (registered_at <> 'infinity'::timestamptz AND registered_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_policies_provider CHECK (provider = 'upstox'), \n\tCONSTRAINT uq_data15_policy_semantic_identity UNIQUE (policy_name, provider, observation_domain), \n\tCONSTRAINT uq_data15_policy_id_provider UNIQUE (policy_id, provider)\n);",
    'CREATE INDEX ix_data15_policies_provider_name ON market_data_quality_policies (provider, policy_name, policy_id);',
    "CREATE TABLE market_data_quality_policy_versions (\n\tpolicy_version_id VARCHAR(71) NOT NULL, \n\tpolicy_id VARCHAR(71) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tpolicy_definition JSONB NOT NULL, \n\tpolicy_definition_hash VARCHAR(71) NOT NULL, \n\tquality_policy_schema_version INTEGER NOT NULL, \n\tquality_evaluator_implementation_version VARCHAR(128) NOT NULL, \n\tnormalization_schema_version INTEGER NOT NULL, \n\tnormalizer_implementation_version VARCHAR(128) NOT NULL, \n\treason_definition_count INTEGER NOT NULL, \n\tregistered_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_market_data_quality_policy_versions PRIMARY KEY (policy_version_id), \n\tCONSTRAINT fk_data15_policy_versions_policy FOREIGN KEY(policy_id) REFERENCES market_data_quality_policies (policy_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_policy_versions_id_sha256 CHECK (policy_version_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policy_versions_policy_sha256 CHECK (policy_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policy_versions_definition_hash_sha256 CHECK (policy_definition_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policy_versions_definition_object CHECK (jsonb_typeof(policy_definition) = 'object'), \n\tCONSTRAINT ck_data15_policy_versions_registered_finite CHECK (registered_at <> 'infinity'::timestamptz AND registered_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_policy_versions_positive CHECK (version > 0), \n\tCONSTRAINT ck_data15_policy_versions_schema_v1 CHECK (quality_policy_schema_version = 1), \n\tCONSTRAINT ck_data15_policy_versions_evaluator_v1 CHECK (quality_evaluator_implementation_version = 'market-data-quality-evaluator-1'), \n\tCONSTRAINT ck_data15_policy_versions_normalizer_v1 CHECK (normalization_schema_version = 1 AND normalizer_implementation_version = 'upstox-v3-normalizer-1'), \n\tCONSTRAINT ck_data15_policy_versions_reason_count CHECK (reason_definition_count = 69), \n\tCONSTRAINT uq_data15_policy_versions_policy_version UNIQUE (policy_id, version), \n\tCONSTRAINT uq_data15_policy_versions_id_policy UNIQUE (policy_version_id, policy_id)\n);",
    'CREATE INDEX ix_data15_policy_versions_definition_hash ON market_data_quality_policy_versions (policy_definition_hash, policy_version_id);',
    "CREATE TABLE market_data_quality_policy_source_artifacts (\n\tsource_artifact_id VARCHAR(71) NOT NULL, \n\tpolicy_version_id VARCHAR(71) NOT NULL, \n\tsource_sha256 VARCHAR(71) NOT NULL, \n\tsource_byte_count INTEGER NOT NULL, \n\tmedia_type VARCHAR(128) NOT NULL, \n\tparser_label VARCHAR(128) NOT NULL, \n\tsource_bytes BYTEA NOT NULL, \n\tregistered_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_market_data_quality_policy_source_artifacts PRIMARY KEY (source_artifact_id), \n\tCONSTRAINT fk_data15_policy_source_version FOREIGN KEY(policy_version_id) REFERENCES market_data_quality_policy_versions (policy_version_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_policy_source_id_sha256 CHECK (source_artifact_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policy_source_version_sha256 CHECK (policy_version_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policy_source_sha256 CHECK (source_sha256 ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_policy_source_registered_finite CHECK (registered_at <> 'infinity'::timestamptz AND registered_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_policy_source_byte_count CHECK (source_byte_count BETWEEN 1 AND 262144 AND octet_length(source_bytes) = source_byte_count), \n\tCONSTRAINT ck_data15_policy_source_labels CHECK (media_type = 'application/yaml' AND parser_label = 'data15-strict-yaml-1'), \n\tCONSTRAINT uq_data15_policy_source_artifact UNIQUE (policy_version_id, source_sha256, source_byte_count, media_type, parser_label)\n);",
    'CREATE INDEX ix_data15_policy_source_version ON market_data_quality_policy_source_artifacts (policy_version_id, source_artifact_id);',
    'CREATE INDEX ix_data15_policy_source_sha ON market_data_quality_policy_source_artifacts (source_sha256, source_artifact_id);',
    "CREATE TABLE market_data_quality_policy_reason_definitions (\n\treason_definition_id VARCHAR(71) NOT NULL, \n\tpolicy_version_id VARCHAR(71) NOT NULL, \n\treason_code VARCHAR(128) NOT NULL, \n\tregistry_ordinal INTEGER NOT NULL, \n\tseverity VARCHAR(16) NOT NULL, \n\tapplicable_target_kinds JSONB NOT NULL, \n\tsubject_keys JSONB NOT NULL, \n\tevidence_profile VARCHAR(128) NOT NULL, \n\tcanonical_payload JSONB NOT NULL, \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_policy_reason_definitions PRIMARY KEY (reason_definition_id), \n\tCONSTRAINT fk_data15_reason_definition_version FOREIGN KEY(policy_version_id) REFERENCES market_data_quality_policy_versions (policy_version_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_reason_definition_id_sha256 CHECK (reason_definition_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_reason_definition_version_sha256 CHECK (policy_version_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_reason_definition_payload_hash_sha256 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_reason_definition_payload_object CHECK (jsonb_typeof(canonical_payload) = 'object'), \n\tCONSTRAINT ck_data15_reason_definition_ordinal CHECK (registry_ordinal BETWEEN 1 AND 69), \n\tCONSTRAINT ck_data15_reason_definition_severity CHECK (severity IN ('warning', 'error')), \n\tCONSTRAINT ck_data15_reason_definition_target_kinds CHECK (jsonb_typeof(applicable_target_kinds) = 'array' AND jsonb_array_length(applicable_target_kinds) > 0), \n\tCONSTRAINT ck_data15_reason_definition_subject_keys CHECK (jsonb_typeof(subject_keys) = 'array' AND jsonb_array_length(subject_keys) > 0), \n\tCONSTRAINT uq_data15_reason_definition_code UNIQUE (policy_version_id, reason_code), \n\tCONSTRAINT uq_data15_reason_definition_ordinal UNIQUE (policy_version_id, registry_ordinal), \n\tCONSTRAINT uq_data15_reason_definition_exact UNIQUE (reason_definition_id, policy_version_id, reason_code, registry_ordinal, severity)\n);",
    'CREATE INDEX ix_data15_reason_definition_code ON market_data_quality_policy_reason_definitions (reason_code, policy_version_id);',
    'CREATE INDEX ix_data15_reason_definition_version_ordinal ON market_data_quality_policy_reason_definitions (policy_version_id, registry_ordinal);',
    "CREATE TABLE market_data_quality_assessment_runs (\n\tassessment_run_id VARCHAR(71) NOT NULL, \n\tassessment_run_schema_version INTEGER NOT NULL, \n\tpolicy_version_id VARCHAR(71) NOT NULL, \n\tevaluation_market_as_of TIMESTAMP WITH TIME ZONE NOT NULL, \n\tevaluation_known_as_of TIMESTAMP WITH TIME ZONE NOT NULL, \n\tquality_evaluator_implementation_version VARCHAR(128) NOT NULL, \n\ttarget_count INTEGER NOT NULL, \n\tordered_target_event_ids JSONB NOT NULL, \n\tcanonical_payload JSONB NOT NULL, \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tpersistence_recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_market_data_quality_assessment_runs PRIMARY KEY (assessment_run_id), \n\tCONSTRAINT fk_data15_assessment_runs_policy_version FOREIGN KEY(policy_version_id) REFERENCES market_data_quality_policy_versions (policy_version_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_assessment_runs_id_sha256 CHECK (assessment_run_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_runs_policy_sha256 CHECK (policy_version_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_runs_payload_hash_sha256 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_runs_market_finite CHECK (evaluation_market_as_of <> 'infinity'::timestamptz AND evaluation_market_as_of <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_assessment_runs_known_finite CHECK (evaluation_known_as_of <> 'infinity'::timestamptz AND evaluation_known_as_of <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_assessment_runs_persistence_finite CHECK (persistence_recorded_at <> 'infinity'::timestamptz AND persistence_recorded_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_assessment_runs_payload_object CHECK (jsonb_typeof(canonical_payload) = 'object'), \n\tCONSTRAINT ck_data15_assessment_runs_schema_v1 CHECK (assessment_run_schema_version = 1), \n\tCONSTRAINT ck_data15_assessment_runs_evaluator_v1 CHECK (quality_evaluator_implementation_version = 'market-data-quality-evaluator-1'), \n\tCONSTRAINT ck_data15_assessment_runs_cutoff_order CHECK (evaluation_known_as_of >= evaluation_market_as_of), \n\tCONSTRAINT ck_data15_assessment_runs_target_shape CHECK (target_count BETWEEN 1 AND 5000 AND jsonb_typeof(ordered_target_event_ids) = 'array' AND jsonb_array_length(ordered_target_event_ids) = target_count), \n\tCONSTRAINT uq_data15_assessment_runs_exact UNIQUE (assessment_run_id, policy_version_id, evaluation_market_as_of, evaluation_known_as_of)\n);",
    'CREATE INDEX ix_data15_assessment_runs_exact ON market_data_quality_assessment_runs (policy_version_id, evaluation_market_as_of, evaluation_known_as_of, assessment_run_id);',
    'CREATE INDEX ix_data15_assessment_runs_persistence ON market_data_quality_assessment_runs (persistence_recorded_at, assessment_run_id);',
    "CREATE TABLE market_data_quality_assessments (\n\tassessment_id VARCHAR(71) NOT NULL, \n\tevent_id VARCHAR(71) NOT NULL, \n\traw_event_id VARCHAR(71) NOT NULL, \n\tresult_id VARCHAR(71) NOT NULL, \n\tpolicy_id VARCHAR(71) NOT NULL, \n\tpolicy_version_id VARCHAR(71) NOT NULL, \n\tevaluation_market_as_of TIMESTAMP WITH TIME ZONE NOT NULL, \n\tevaluation_known_as_of TIMESTAMP WITH TIME ZONE NOT NULL, \n\tdependency_market_as_of TIMESTAMP WITH TIME ZONE NOT NULL, \n\tmarket_time_basis VARCHAR(128) NOT NULL, \n\ttarget_kind VARCHAR(32) NOT NULL, \n\tdisposition VARCHAR(16) NOT NULL, \n\treason_count INTEGER NOT NULL, \n\tdependency_count INTEGER NOT NULL, \n\treason_set_hash VARCHAR(71) NOT NULL, \n\tdependency_closure_hash VARCHAR(71) NOT NULL, \n\tcanonical_payload JSONB NOT NULL, \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tpolicy_registered_after_known_as_of BOOLEAN NOT NULL, \n\tpersistence_recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_market_data_quality_assessments PRIMARY KEY (assessment_id), \n\tCONSTRAINT fk_data15_assessments_event_raw FOREIGN KEY(event_id, raw_event_id) REFERENCES market_observations (event_id, raw_event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_assessments_result_raw FOREIGN KEY(result_id, raw_event_id) REFERENCES market_normalization_results (result_id, raw_event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_assessments_result_event FOREIGN KEY(result_id, event_id) REFERENCES market_normalization_result_events (result_id, event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_assessments_policy_version FOREIGN KEY(policy_version_id, policy_id) REFERENCES market_data_quality_policy_versions (policy_version_id, policy_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_assessments_id_sha256 CHECK (assessment_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_event_sha256 CHECK (event_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_raw_sha256 CHECK (raw_event_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_result_sha256 CHECK (result_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_policy_sha256 CHECK (policy_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_version_sha256 CHECK (policy_version_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_reason_hash_sha256 CHECK (reason_set_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_dependency_hash_sha256 CHECK (dependency_closure_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_payload_hash_sha256 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessments_market_finite CHECK (evaluation_market_as_of <> 'infinity'::timestamptz AND evaluation_market_as_of <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_assessments_known_finite CHECK (evaluation_known_as_of <> 'infinity'::timestamptz AND evaluation_known_as_of <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_assessments_dependency_market_finite CHECK (dependency_market_as_of <> 'infinity'::timestamptz AND dependency_market_as_of <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_assessments_persistence_finite CHECK (persistence_recorded_at <> 'infinity'::timestamptz AND persistence_recorded_at <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_assessments_payload_object CHECK (jsonb_typeof(canonical_payload) = 'object'), \n\tCONSTRAINT ck_data15_assessments_cutoff_order CHECK (evaluation_known_as_of >= evaluation_market_as_of AND dependency_market_as_of <= evaluation_market_as_of), \n\tCONSTRAINT ck_data15_assessments_market_time_basis CHECK (market_time_basis = 'provider_timestamp_v1'), \n\tCONSTRAINT ck_data15_assessments_target_kind CHECK (target_kind IN ('underlying_quote', 'futures_quote', 'option_quote', 'market_segment_status')), \n\tCONSTRAINT ck_data15_assessments_disposition CHECK (disposition IN ('eligible', 'warning', 'ineligible')), \n\tCONSTRAINT ck_data15_assessments_count_bounds CHECK (reason_count BETWEEN 0 AND 127 AND dependency_count BETWEEN 1 AND 16), \n\tCONSTRAINT uq_data15_assessments_exact_lookup UNIQUE (event_id, policy_version_id, evaluation_market_as_of, evaluation_known_as_of), \n\tCONSTRAINT uq_data15_assessments_id_event UNIQUE (assessment_id, event_id)\n);",
    'CREATE INDEX ix_data15_assessments_policy_context ON market_data_quality_assessments (policy_version_id, evaluation_market_as_of, evaluation_known_as_of, assessment_id);',
    'CREATE INDEX ix_data15_assessments_exact_lookup ON market_data_quality_assessments (event_id, policy_version_id, evaluation_market_as_of, evaluation_known_as_of);',
    'CREATE INDEX ix_data15_assessments_persistence ON market_data_quality_assessments (persistence_recorded_at, assessment_id);',
    "CREATE TABLE market_data_quality_assessment_reasons (\n\treason_occurrence_id VARCHAR(71) NOT NULL, \n\tassessment_id VARCHAR(71) NOT NULL, \n\tpolicy_version_id VARCHAR(71) NOT NULL, \n\treason_definition_id VARCHAR(71) NOT NULL, \n\treason_code VARCHAR(128) NOT NULL, \n\tregistry_ordinal INTEGER NOT NULL, \n\tseverity VARCHAR(16) NOT NULL, \n\tsubject_key VARCHAR(128) NOT NULL, \n\treason_ordinal INTEGER NOT NULL, \n\tevidence JSONB NOT NULL, \n\tevidence_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_assessment_reasons PRIMARY KEY (reason_occurrence_id), \n\tCONSTRAINT fk_data15_assessment_reasons_assessment FOREIGN KEY(assessment_id) REFERENCES market_data_quality_assessments (assessment_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_assessment_reasons_definition FOREIGN KEY(reason_definition_id, policy_version_id, reason_code, registry_ordinal, severity) REFERENCES market_data_quality_policy_reason_definitions (reason_definition_id, policy_version_id, reason_code, registry_ordinal, severity) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_assessment_reasons_id_sha256 CHECK (reason_occurrence_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_reasons_assessment_sha256 CHECK (assessment_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_reasons_version_sha256 CHECK (policy_version_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_reasons_definition_sha256 CHECK (reason_definition_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_reasons_evidence_sha256 CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_assessment_reasons_evidence_object CHECK (jsonb_typeof(evidence) = 'object'), \n\tCONSTRAINT ck_data15_assessment_reasons_ordinal CHECK (reason_ordinal BETWEEN 0 AND 127), \n\tCONSTRAINT ck_data15_assessment_reasons_severity CHECK (severity IN ('warning', 'error')), \n\tCONSTRAINT uq_data15_assessment_reason_occurrence UNIQUE (assessment_id, reason_code, subject_key), \n\tCONSTRAINT uq_data15_assessment_reason_ordinal UNIQUE (assessment_id, reason_ordinal)\n);",
    'CREATE INDEX ix_data15_assessment_reasons_order ON market_data_quality_assessment_reasons (assessment_id, reason_ordinal);',
    'CREATE INDEX ix_data15_assessment_reasons_code ON market_data_quality_assessment_reasons (reason_code, assessment_id);',
    "CREATE TABLE market_data_quality_assessment_dependencies (\n\tassessment_dependency_id VARCHAR(71) NOT NULL, \n\tassessment_id VARCHAR(71) NOT NULL, \n\tdependency_ordinal INTEGER NOT NULL, \n\tdependency_kind VARCHAR(128) NOT NULL, \n\tsubject_key VARCHAR(128) NOT NULL, \n\toutcome VARCHAR(16) NOT NULL, \n\tmarket_cutoff TIMESTAMP WITH TIME ZONE NOT NULL, \n\tknowledge_cutoff TIMESTAMP WITH TIME ZONE NOT NULL, \n\tselection_rule_version VARCHAR(128) NOT NULL, \n\tcandidate_count INTEGER NOT NULL, \n\tselected_candidate_ordinal INTEGER, \n\tsearch_scope_payload JSONB NOT NULL, \n\tsearch_scope_hash VARCHAR(71) NOT NULL, \n\tcanonical_payload JSONB NOT NULL, \n\tcanonical_payload_hash VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_market_data_quality_assessment_dependencies PRIMARY KEY (assessment_dependency_id), \n\tCONSTRAINT fk_data15_dependencies_assessment FOREIGN KEY(assessment_id) REFERENCES market_data_quality_assessments (assessment_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_dependencies_id_sha256 CHECK (assessment_dependency_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_dependencies_assessment_sha256 CHECK (assessment_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_dependencies_scope_hash_sha256 CHECK (search_scope_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_dependencies_payload_hash_sha256 CHECK (canonical_payload_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_dependencies_market_finite CHECK (market_cutoff <> 'infinity'::timestamptz AND market_cutoff <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_dependencies_known_finite CHECK (knowledge_cutoff <> 'infinity'::timestamptz AND knowledge_cutoff <> '-infinity'::timestamptz), \n\tCONSTRAINT ck_data15_dependencies_scope_object CHECK (jsonb_typeof(search_scope_payload) = 'object'), \n\tCONSTRAINT ck_data15_dependencies_payload_object CHECK (jsonb_typeof(canonical_payload) = 'object'), \n\tCONSTRAINT ck_data15_dependencies_ordinal CHECK (dependency_ordinal BETWEEN 0 AND 15), \n\tCONSTRAINT ck_data15_dependencies_kind CHECK (dependency_kind IN ('provider_mapping', 'instrument_version', 'catalogue_version', 'catalogue_membership', 'trading_session', 'market_segment_status', 'connection_session', 'subscription_scope')), \n\tCONSTRAINT ck_data15_dependencies_cutoff_order CHECK (knowledge_cutoff >= market_cutoff), \n\tCONSTRAINT ck_data15_dependencies_outcome_shape CHECK ((outcome = 'selected' AND candidate_count = 1 AND selected_candidate_ordinal = 0) OR (outcome = 'absent' AND candidate_count = 0 AND selected_candidate_ordinal IS NULL) OR (outcome = 'ambiguous' AND candidate_count BETWEEN 2 AND 5000 AND selected_candidate_ordinal IS NULL)), \n\tCONSTRAINT uq_data15_dependency_semantic UNIQUE (assessment_id, dependency_kind, subject_key), \n\tCONSTRAINT uq_data15_dependency_ordinal UNIQUE (assessment_id, dependency_ordinal), \n\tCONSTRAINT uq_data15_dependency_id_kind UNIQUE (assessment_dependency_id, dependency_kind)\n);",
    'CREATE INDEX ix_data15_dependencies_kind_outcome ON market_data_quality_assessment_dependencies (dependency_kind, outcome, assessment_dependency_id);',
    'CREATE INDEX ix_data15_dependencies_assessment_order ON market_data_quality_assessment_dependencies (assessment_id, dependency_ordinal);',
    "CREATE TABLE market_data_quality_dependency_candidates (\n\tassessment_dependency_id VARCHAR(71) NOT NULL, \n\tcandidate_ordinal INTEGER NOT NULL, \n\tdependency_kind VARCHAR(128) NOT NULL, \n\tcandidate_content_hash VARCHAR(71) NOT NULL, \n\tcandidate_payload JSONB NOT NULL, \n\tmarket_event_id VARCHAR(71), \n\tmarket_result_id VARCHAR(71), \n\tmarket_raw_event_id VARCHAR(71), \n\tprovider_mapping_record_id VARCHAR(71), \n\tprovider_mapping_id VARCHAR(71), \n\tinstrument_version_record_id VARCHAR(71), \n\tinstrument_version_id VARCHAR(71), \n\tcatalogue_record_id VARCHAR(71), \n\tcatalogue_version_id VARCHAR(71), \n\tcatalogue_ingestion_run_id VARCHAR(71), \n\tcatalogue_membership_id VARCHAR(71), \n\tmembership_ingestion_run_id VARCHAR(71), \n\ttrading_session_record_id VARCHAR(71), \n\ttrading_session_version_id VARCHAR(71), \n\tlifecycle_event_id VARCHAR(71), \n\tlifecycle_kind VARCHAR(32), \n\tlifecycle_batch_id VARCHAR(71), \n\tinstrument_keys_digest VARCHAR(71), \n\tCONSTRAINT pk_data15_dependency_candidates PRIMARY KEY (assessment_dependency_id, candidate_ordinal), \n\tCONSTRAINT fk_data15_candidates_dependency FOREIGN KEY(assessment_dependency_id, dependency_kind) REFERENCES market_data_quality_assessment_dependencies (assessment_dependency_id, dependency_kind) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_market_event_raw FOREIGN KEY(market_event_id, market_raw_event_id) REFERENCES market_observations (event_id, raw_event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_result_event FOREIGN KEY(market_result_id, market_event_id) REFERENCES market_normalization_result_events (result_id, event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_result_raw FOREIGN KEY(market_result_id, market_raw_event_id) REFERENCES market_normalization_results (result_id, raw_event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_provider_mapping FOREIGN KEY(provider_mapping_record_id, provider_mapping_id) REFERENCES provider_mapping_records (record_id, mapping_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_instrument_version FOREIGN KEY(instrument_version_record_id, instrument_version_id) REFERENCES instrument_version_records (record_id, version_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_catalogue_version FOREIGN KEY(catalogue_record_id, catalogue_version_id) REFERENCES catalogue_version_records (record_id, catalogue_version_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_catalogue_run FOREIGN KEY(catalogue_ingestion_run_id) REFERENCES catalogue_ingestion_runs (ingestion_run_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_membership FOREIGN KEY(catalogue_membership_id) REFERENCES catalogue_memberships (membership_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_membership_run FOREIGN KEY(membership_ingestion_run_id) REFERENCES catalogue_ingestion_runs (ingestion_run_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_membership_receipt FOREIGN KEY(catalogue_membership_id, membership_ingestion_run_id) REFERENCES market_data_quality_catalogue_membership_receipts (membership_id, ingestion_run_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_trading_session FOREIGN KEY(trading_session_record_id, trading_session_version_id) REFERENCES trading_session_version_records (record_id, session_version_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_lifecycle_event FOREIGN KEY(lifecycle_event_id, lifecycle_kind) REFERENCES provider_lifecycle_observations (event_id, lifecycle_kind) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_lifecycle_batch FOREIGN KEY(lifecycle_batch_id, lifecycle_kind) REFERENCES provider_lifecycle_batches (lifecycle_batch_id, lifecycle_kind) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_candidates_instrument_set FOREIGN KEY(instrument_keys_digest) REFERENCES provider_subscription_instrument_sets (instrument_keys_digest) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_candidates_dependency_sha256 CHECK (assessment_dependency_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_candidates_content_hash_sha256 CHECK (candidate_content_hash ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_candidates_payload_object CHECK (jsonb_typeof(candidate_payload) = 'object'), \n\tCONSTRAINT ck_data15_candidates_ordinal CHECK (candidate_ordinal BETWEEN 0 AND 4999), \n\tCONSTRAINT ck_data15_dependency_candidate_ids_sha256 CHECK ((market_event_id IS NULL OR market_event_id ~ '^sha256:[0-9a-f]{64}$') AND (market_result_id IS NULL OR market_result_id ~ '^sha256:[0-9a-f]{64}$') AND (market_raw_event_id IS NULL OR market_raw_event_id ~ '^sha256:[0-9a-f]{64}$') AND (provider_mapping_record_id IS NULL OR provider_mapping_record_id ~ '^sha256:[0-9a-f]{64}$') AND (provider_mapping_id IS NULL OR provider_mapping_id ~ '^sha256:[0-9a-f]{64}$') AND (instrument_version_record_id IS NULL OR instrument_version_record_id ~ '^sha256:[0-9a-f]{64}$') AND (instrument_version_id IS NULL OR instrument_version_id ~ '^sha256:[0-9a-f]{64}$') AND (catalogue_record_id IS NULL OR catalogue_record_id ~ '^sha256:[0-9a-f]{64}$') AND (catalogue_version_id IS NULL OR catalogue_version_id ~ '^sha256:[0-9a-f]{64}$') AND (catalogue_ingestion_run_id IS NULL OR catalogue_ingestion_run_id ~ '^sha256:[0-9a-f]{64}$') AND (catalogue_membership_id IS NULL OR catalogue_membership_id ~ '^sha256:[0-9a-f]{64}$') AND (membership_ingestion_run_id IS NULL OR membership_ingestion_run_id ~ '^sha256:[0-9a-f]{64}$') AND (trading_session_record_id IS NULL OR trading_session_record_id ~ '^sha256:[0-9a-f]{64}$') AND (trading_session_version_id IS NULL OR trading_session_version_id ~ '^sha256:[0-9a-f]{64}$') AND (lifecycle_event_id IS NULL OR lifecycle_event_id ~ '^sha256:[0-9a-f]{64}$') AND (lifecycle_batch_id IS NULL OR lifecycle_batch_id ~ '^sha256:[0-9a-f]{64}$') AND (instrument_keys_digest IS NULL OR instrument_keys_digest ~ '^sha256:[0-9a-f]{64}$')), \n\tCONSTRAINT ck_data15_dependency_candidate_kind_shape CHECK ((dependency_kind = 'market_segment_status' AND market_event_id IS NOT NULL AND market_result_id IS NOT NULL AND market_raw_event_id IS NOT NULL AND provider_mapping_record_id IS NULL AND provider_mapping_id IS NULL AND instrument_version_record_id IS NULL AND instrument_version_id IS NULL AND catalogue_record_id IS NULL AND catalogue_version_id IS NULL AND catalogue_ingestion_run_id IS NULL AND catalogue_membership_id IS NULL AND membership_ingestion_run_id IS NULL AND trading_session_record_id IS NULL AND trading_session_version_id IS NULL AND lifecycle_event_id IS NULL AND lifecycle_kind IS NULL AND lifecycle_batch_id IS NULL AND instrument_keys_digest IS NULL) OR (dependency_kind = 'provider_mapping' AND provider_mapping_record_id IS NOT NULL AND provider_mapping_id IS NOT NULL AND market_event_id IS NULL AND market_result_id IS NULL AND market_raw_event_id IS NULL AND instrument_version_record_id IS NULL AND instrument_version_id IS NULL AND catalogue_record_id IS NULL AND catalogue_version_id IS NULL AND catalogue_ingestion_run_id IS NULL AND catalogue_membership_id IS NULL AND membership_ingestion_run_id IS NULL AND trading_session_record_id IS NULL AND trading_session_version_id IS NULL AND lifecycle_event_id IS NULL AND lifecycle_kind IS NULL AND lifecycle_batch_id IS NULL AND instrument_keys_digest IS NULL) OR (dependency_kind = 'instrument_version' AND instrument_version_record_id IS NOT NULL AND instrument_version_id IS NOT NULL AND market_event_id IS NULL AND market_result_id IS NULL AND market_raw_event_id IS NULL AND provider_mapping_record_id IS NULL AND provider_mapping_id IS NULL AND catalogue_record_id IS NULL AND catalogue_version_id IS NULL AND catalogue_ingestion_run_id IS NULL AND catalogue_membership_id IS NULL AND membership_ingestion_run_id IS NULL AND trading_session_record_id IS NULL AND trading_session_version_id IS NULL AND lifecycle_event_id IS NULL AND lifecycle_kind IS NULL AND lifecycle_batch_id IS NULL AND instrument_keys_digest IS NULL) OR (dependency_kind = 'catalogue_version' AND catalogue_record_id IS NOT NULL AND catalogue_version_id IS NOT NULL AND catalogue_ingestion_run_id IS NOT NULL AND market_event_id IS NULL AND market_result_id IS NULL AND market_raw_event_id IS NULL AND provider_mapping_record_id IS NULL AND provider_mapping_id IS NULL AND instrument_version_record_id IS NULL AND instrument_version_id IS NULL AND catalogue_membership_id IS NULL AND membership_ingestion_run_id IS NULL AND trading_session_record_id IS NULL AND trading_session_version_id IS NULL AND lifecycle_event_id IS NULL AND lifecycle_kind IS NULL AND lifecycle_batch_id IS NULL AND instrument_keys_digest IS NULL) OR (dependency_kind = 'catalogue_membership' AND catalogue_membership_id IS NOT NULL AND membership_ingestion_run_id IS NOT NULL AND market_event_id IS NULL AND market_result_id IS NULL AND market_raw_event_id IS NULL AND provider_mapping_record_id IS NULL AND provider_mapping_id IS NULL AND instrument_version_record_id IS NULL AND instrument_version_id IS NULL AND catalogue_record_id IS NULL AND catalogue_version_id IS NULL AND catalogue_ingestion_run_id IS NULL AND trading_session_record_id IS NULL AND trading_session_version_id IS NULL AND lifecycle_event_id IS NULL AND lifecycle_kind IS NULL AND lifecycle_batch_id IS NULL AND instrument_keys_digest IS NULL) OR (dependency_kind = 'trading_session' AND trading_session_record_id IS NOT NULL AND trading_session_version_id IS NOT NULL AND market_event_id IS NULL AND market_result_id IS NULL AND market_raw_event_id IS NULL AND provider_mapping_record_id IS NULL AND provider_mapping_id IS NULL AND instrument_version_record_id IS NULL AND instrument_version_id IS NULL AND catalogue_record_id IS NULL AND catalogue_version_id IS NULL AND catalogue_ingestion_run_id IS NULL AND catalogue_membership_id IS NULL AND membership_ingestion_run_id IS NULL AND lifecycle_event_id IS NULL AND lifecycle_kind IS NULL AND lifecycle_batch_id IS NULL AND instrument_keys_digest IS NULL) OR (dependency_kind = 'connection_session' AND lifecycle_event_id IS NOT NULL AND lifecycle_kind = 'connection' AND lifecycle_batch_id IS NOT NULL AND instrument_keys_digest IS NULL AND market_event_id IS NULL AND market_result_id IS NULL AND market_raw_event_id IS NULL AND provider_mapping_record_id IS NULL AND provider_mapping_id IS NULL AND instrument_version_record_id IS NULL AND instrument_version_id IS NULL AND catalogue_record_id IS NULL AND catalogue_version_id IS NULL AND catalogue_ingestion_run_id IS NULL AND catalogue_membership_id IS NULL AND membership_ingestion_run_id IS NULL AND trading_session_record_id IS NULL AND trading_session_version_id IS NULL) OR (dependency_kind = 'subscription_scope' AND lifecycle_event_id IS NOT NULL AND lifecycle_kind = 'subscription' AND lifecycle_batch_id IS NOT NULL AND instrument_keys_digest IS NOT NULL AND market_event_id IS NULL AND market_result_id IS NULL AND market_raw_event_id IS NULL AND provider_mapping_record_id IS NULL AND provider_mapping_id IS NULL AND instrument_version_record_id IS NULL AND instrument_version_id IS NULL AND catalogue_record_id IS NULL AND catalogue_version_id IS NULL AND catalogue_ingestion_run_id IS NULL AND catalogue_membership_id IS NULL AND membership_ingestion_run_id IS NULL AND trading_session_record_id IS NULL AND trading_session_version_id IS NULL)), \n\tCONSTRAINT uq_data15_candidate_content UNIQUE (assessment_dependency_id, candidate_content_hash)\n);",
    'CREATE INDEX ix_data15_candidates_dependency_order ON market_data_quality_dependency_candidates (assessment_dependency_id, candidate_ordinal);',
    'CREATE INDEX ix_data15_candidates_session ON market_data_quality_dependency_candidates (trading_session_record_id);',
    'CREATE INDEX ix_data15_candidates_instrument ON market_data_quality_dependency_candidates (instrument_version_record_id);',
    'CREATE INDEX ix_data15_candidates_market_event ON market_data_quality_dependency_candidates (market_event_id);',
    'CREATE INDEX ix_data15_candidates_lifecycle ON market_data_quality_dependency_candidates (lifecycle_event_id);',
    'CREATE INDEX ix_data15_candidates_catalogue ON market_data_quality_dependency_candidates (catalogue_record_id);',
    'CREATE INDEX ix_data15_candidates_mapping ON market_data_quality_dependency_candidates (provider_mapping_record_id);',
    'CREATE INDEX ix_data15_candidates_membership ON market_data_quality_dependency_candidates (catalogue_membership_id);',
    "CREATE TABLE market_data_quality_run_assessments (\n\tassessment_run_id VARCHAR(71) NOT NULL, \n\ttarget_ordinal INTEGER NOT NULL, \n\tevent_id VARCHAR(71) NOT NULL, \n\tassessment_id VARCHAR(71) NOT NULL, \n\tCONSTRAINT pk_data15_run_assessments PRIMARY KEY (assessment_run_id, target_ordinal), \n\tCONSTRAINT fk_data15_run_assessments_run FOREIGN KEY(assessment_run_id) REFERENCES market_data_quality_assessment_runs (assessment_run_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_run_assessments_assessment FOREIGN KEY(assessment_id, event_id) REFERENCES market_data_quality_assessments (assessment_id, event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT fk_data15_run_assessments_event FOREIGN KEY(event_id) REFERENCES market_observations (event_id) ON DELETE NO ACTION ON UPDATE NO ACTION, \n\tCONSTRAINT ck_data15_run_assessments_run_sha256 CHECK (assessment_run_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_run_assessments_event_sha256 CHECK (event_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_run_assessments_assessment_sha256 CHECK (assessment_id ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_data15_run_assessments_ordinal CHECK (target_ordinal BETWEEN 0 AND 4999), \n\tCONSTRAINT uq_data15_run_assessments_event UNIQUE (assessment_run_id, event_id), \n\tCONSTRAINT uq_data15_run_assessments_assessment UNIQUE (assessment_run_id, assessment_id)\n);",
    'CREATE INDEX ix_data15_run_assessments_assessment ON market_data_quality_run_assessments (assessment_id, assessment_run_id);',
    'CREATE INDEX ix_data15_run_assessments_event ON market_data_quality_run_assessments (event_id, assessment_run_id);',
)


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical mappings require string keys")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical numeric values must be finite")
        if value.is_zero():
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return _normalize(Decimal(str(value)))
    if isinstance(value, int):
        return format(Decimal(value).normalize(), "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(
        _normalize(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _backfill_receipts() -> None:
    connection = op.get_bind()
    receipt_at = connection.execute(
        sa.text("SELECT transaction_timestamp()")
    ).scalar_one()

    for source_table, receipt_table, target_kind, _trigger_name in RECEIPT_TARGETS:
        record_ids = tuple(
            connection.execute(
                sa.text(f"SELECT record_id FROM {source_table} ORDER BY record_id")
            ).scalars()
        )
        if not record_ids:
            continue
        rows = []
        for record_id in record_ids:
            canonical_payload = {
                "target_kind": target_kind,
                "record_id": record_id,
                "receipt_at": receipt_at,
                "receipt_basis": "legacy_bootstrap",
                "bootstrap_revision": revision,
            }
            rows.append(
                {
                    "record_id": record_id,
                    "receipt_at": receipt_at,
                    "receipt_basis": "legacy_bootstrap",
                    "bootstrap_revision": revision,
                    "canonical_payload_hash": _stable_hash(canonical_payload),
                }
            )
        connection.execute(
            sa.text(
                f"INSERT INTO {receipt_table} ("
                "record_id, receipt_at, receipt_basis, bootstrap_revision, "
                "canonical_payload_hash"
                ") VALUES ("
                ":record_id, :receipt_at, :receipt_basis, :bootstrap_revision, "
                ":canonical_payload_hash)"
            ),
            rows,
        )

    membership_rows = tuple(
        connection.execute(
            sa.text(
                "SELECT membership.membership_id, outcome.ingestion_run_id "
                "FROM catalogue_memberships AS membership "
                "JOIN catalogue_row_outcomes AS outcome "
                "ON outcome.row_outcome_id = membership.row_outcome_id "
                "ORDER BY membership.membership_id"
            )
        ).mappings()
    )
    if membership_rows:
        values = []
        for row in membership_rows:
            canonical_payload = {
                "membership_id": row["membership_id"],
                "ingestion_run_id": row["ingestion_run_id"],
                "receipt_at": receipt_at,
                "receipt_basis": "legacy_bootstrap",
                "bootstrap_revision": revision,
            }
            values.append(
                {
                    "membership_id": row["membership_id"],
                    "ingestion_run_id": row["ingestion_run_id"],
                    "receipt_at": receipt_at,
                    "receipt_basis": "legacy_bootstrap",
                    "bootstrap_revision": revision,
                    "canonical_payload_hash": _stable_hash(canonical_payload),
                }
            )
        connection.execute(
            sa.text(
                "INSERT INTO market_data_quality_catalogue_membership_receipts ("
                "membership_id, ingestion_run_id, receipt_at, receipt_basis, "
                "bootstrap_revision, canonical_payload_hash"
                ") VALUES ("
                ":membership_id, :ingestion_run_id, :receipt_at, :receipt_basis, "
                ":bootstrap_revision, :canonical_payload_hash)"
            ),
            values,
        )


def _create_append_only_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION data15_reject_row_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'DATA-1.5 append-only table % rejects %',
                TG_TABLE_NAME, TG_OP
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION data15_reject_truncate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'DATA-1.5 append-only table % rejects TRUNCATE',
                TG_TABLE_NAME
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    for table_name in DATA15_TABLES:
        op.execute(
            f"CREATE TRIGGER {table_name}_append_only "
            f"BEFORE UPDATE OR DELETE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION data15_reject_row_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {table_name}_reject_truncate "
            f"BEFORE TRUNCATE ON {table_name} "
            "FOR EACH STATEMENT EXECUTE FUNCTION data15_reject_truncate()"
        )


def _create_receipt_completeness_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION data15_validate_receipt_completeness()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            target_id text;
            receipt_table text;
            receipt_present boolean;
            expected_run text;
            receipt_run text;
        BEGIN
            IF TG_TABLE_NAME = 'catalogue_memberships' THEN
                target_id := to_jsonb(NEW) ->> 'membership_id';
                SELECT outcome.ingestion_run_id
                INTO expected_run
                FROM catalogue_row_outcomes AS outcome
                WHERE outcome.row_outcome_id = NEW.row_outcome_id;

                SELECT receipt.ingestion_run_id
                INTO receipt_run
                FROM market_data_quality_catalogue_membership_receipts AS receipt
                WHERE receipt.membership_id = target_id;

                IF receipt_run IS NULL OR receipt_run <> expected_run THEN
                    RAISE EXCEPTION
                        'DATA-1.5 catalogue membership % lacks an exact receipt',
                        target_id
                        USING ERRCODE = '23514';
                END IF;
                RETURN NULL;
            END IF;

            target_id := to_jsonb(NEW) ->> 'record_id';
            receipt_table := CASE TG_TABLE_NAME
                WHEN 'provider_mapping_records'
                    THEN 'market_data_quality_provider_mapping_receipts'
                WHEN 'instrument_version_records'
                    THEN 'market_data_quality_instrument_version_receipts'
                WHEN 'catalogue_version_records'
                    THEN 'market_data_quality_catalogue_version_receipts'
                WHEN 'trading_session_version_records'
                    THEN 'market_data_quality_trading_session_receipts'
                ELSE NULL
            END;

            IF receipt_table IS NULL THEN
                RAISE EXCEPTION 'unsupported DATA-1.5 receipt target %', TG_TABLE_NAME
                    USING ERRCODE = '23514';
            END IF;

            EXECUTE format(
                'SELECT EXISTS (SELECT 1 FROM %I WHERE record_id = $1)',
                receipt_table
            ) INTO receipt_present USING target_id;

            IF NOT receipt_present THEN
                RAISE EXCEPTION
                    'DATA-1.5 temporal record %.% lacks a receipt',
                    TG_TABLE_NAME, target_id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    for source_table, _receipt_table, _target_kind, trigger_name in RECEIPT_TARGETS:
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger_name} "
            f"AFTER INSERT ON {source_table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION data15_validate_receipt_completeness()"
        )
    op.execute(
        "CREATE CONSTRAINT TRIGGER data15_catalogue_membership_receipt_complete "
        "AFTER INSERT ON catalogue_memberships "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION data15_validate_receipt_completeness()"
    )


def _create_aggregate_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION data15_validate_policy_reason_registry()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            version_id text;
            expected_count integer;
            actual_count integer;
            distinct_count integer;
            minimum_ordinal integer;
            maximum_ordinal integer;
        BEGIN
            version_id := COALESCE(
                to_jsonb(NEW) ->> 'policy_version_id',
                to_jsonb(OLD) ->> 'policy_version_id'
            );
            SELECT reason_definition_count
            INTO expected_count
            FROM market_data_quality_policy_versions
            WHERE policy_version_id = version_id;
            IF expected_count IS NULL THEN
                RETURN NULL;
            END IF;
            SELECT count(*), count(DISTINCT registry_ordinal),
                   min(registry_ordinal), max(registry_ordinal)
            INTO actual_count, distinct_count, minimum_ordinal, maximum_ordinal
            FROM market_data_quality_policy_reason_definitions
            WHERE policy_version_id = version_id;
            IF actual_count <> expected_count
               OR distinct_count <> expected_count
               OR minimum_ordinal <> 1
               OR maximum_ordinal <> expected_count THEN
                RAISE EXCEPTION
                    'DATA-1.5 policy version % has an incomplete reason registry',
                    version_id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER data15_policy_version_reason_registry "
        "AFTER INSERT ON market_data_quality_policy_versions "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION data15_validate_policy_reason_registry()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER data15_reason_definition_registry "
        "AFTER INSERT ON market_data_quality_policy_reason_definitions "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION data15_validate_policy_reason_registry()"
    )

    op.execute(
        """
        CREATE FUNCTION data15_validate_assessment_aggregate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            target_assessment_id text;
            expected_reason_count integer;
            expected_dependency_count integer;
            expected_disposition text;
            actual_reason_count integer;
            actual_dependency_count integer;
            minimum_reason_ordinal integer;
            maximum_reason_ordinal integer;
            minimum_dependency_ordinal integer;
            maximum_dependency_ordinal integer;
            reduced_disposition text;
            inconsistent_reason_count integer;
        BEGIN
            target_assessment_id := COALESCE(
                to_jsonb(NEW) ->> 'assessment_id',
                to_jsonb(OLD) ->> 'assessment_id'
            );
            SELECT reason_count, dependency_count, disposition
            INTO expected_reason_count, expected_dependency_count, expected_disposition
            FROM market_data_quality_assessments
            WHERE assessment_id = target_assessment_id;
            IF expected_reason_count IS NULL THEN
                RETURN NULL;
            END IF;

            SELECT count(*), min(reason_ordinal), max(reason_ordinal),
                   CASE
                       WHEN bool_or(severity = 'error') THEN 'ineligible'
                       WHEN bool_or(severity = 'warning') THEN 'warning'
                       ELSE 'eligible'
                   END
            INTO actual_reason_count, minimum_reason_ordinal,
                 maximum_reason_ordinal, reduced_disposition
            FROM market_data_quality_assessment_reasons
            WHERE assessment_id = target_assessment_id;

            SELECT count(*), min(dependency_ordinal), max(dependency_ordinal)
            INTO actual_dependency_count, minimum_dependency_ordinal,
                 maximum_dependency_ordinal
            FROM market_data_quality_assessment_dependencies
            WHERE assessment_id = target_assessment_id;

            SELECT count(*)
            INTO inconsistent_reason_count
            FROM market_data_quality_assessment_reasons AS reason
            JOIN market_data_quality_assessments AS assessment
              ON assessment.assessment_id = reason.assessment_id
            WHERE reason.assessment_id = target_assessment_id
              AND reason.policy_version_id <> assessment.policy_version_id;

            IF actual_reason_count <> expected_reason_count
               OR (actual_reason_count > 0 AND (
                    minimum_reason_ordinal <> 0
                    OR maximum_reason_ordinal <> actual_reason_count - 1))
               OR actual_dependency_count <> expected_dependency_count
               OR minimum_dependency_ordinal <> 0
               OR maximum_dependency_ordinal <> actual_dependency_count - 1
               OR reduced_disposition <> expected_disposition
               OR inconsistent_reason_count <> 0 THEN
                RAISE EXCEPTION
                    'DATA-1.5 assessment % aggregate mismatch',
                    target_assessment_id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    for table_name in (
        "market_data_quality_assessments",
        "market_data_quality_assessment_reasons",
        "market_data_quality_assessment_dependencies",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table_name}_aggregate "
            f"AFTER INSERT ON {table_name} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION data15_validate_assessment_aggregate()"
        )

    op.execute(
        """
        CREATE FUNCTION data15_validate_dependency_aggregate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            dependency_id text;
            expected_count integer;
            expected_outcome text;
            expected_selected integer;
            actual_count integer;
            minimum_ordinal integer;
            maximum_ordinal integer;
        BEGIN
            dependency_id := COALESCE(
                to_jsonb(NEW) ->> 'assessment_dependency_id',
                to_jsonb(OLD) ->> 'assessment_dependency_id'
            );
            SELECT candidate_count, outcome, selected_candidate_ordinal
            INTO expected_count, expected_outcome, expected_selected
            FROM market_data_quality_assessment_dependencies
            WHERE assessment_dependency_id = dependency_id;
            IF expected_count IS NULL THEN
                RETURN NULL;
            END IF;
            SELECT count(*), min(candidate_ordinal), max(candidate_ordinal)
            INTO actual_count, minimum_ordinal, maximum_ordinal
            FROM market_data_quality_dependency_candidates
            WHERE assessment_dependency_id = dependency_id;
            IF actual_count <> expected_count
               OR (actual_count > 0 AND (
                    minimum_ordinal <> 0
                    OR maximum_ordinal <> actual_count - 1))
               OR (expected_outcome = 'selected' AND expected_selected <> 0)
               OR (expected_outcome <> 'selected' AND expected_selected IS NOT NULL) THEN
                RAISE EXCEPTION
                    'DATA-1.5 dependency % aggregate mismatch',
                    dependency_id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    for table_name in (
        "market_data_quality_assessment_dependencies",
        "market_data_quality_dependency_candidates",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table_name}_candidate_aggregate "
            f"AFTER INSERT ON {table_name} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION data15_validate_dependency_aggregate()"
        )

    op.execute(
        """
        CREATE FUNCTION data15_validate_run_membership()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            run_id text;
            expected_count integer;
            expected_events jsonb;
            run_policy text;
            run_market timestamptz;
            run_known timestamptz;
            actual_count integer;
            actual_events jsonb;
            minimum_ordinal integer;
            maximum_ordinal integer;
            inconsistent_count integer;
        BEGIN
            run_id := COALESCE(
                to_jsonb(NEW) ->> 'assessment_run_id',
                to_jsonb(OLD) ->> 'assessment_run_id'
            );
            SELECT target_count, ordered_target_event_ids, policy_version_id,
                   evaluation_market_as_of, evaluation_known_as_of
            INTO expected_count, expected_events, run_policy, run_market, run_known
            FROM market_data_quality_assessment_runs
            WHERE assessment_run_id = run_id;
            IF expected_count IS NULL THEN
                RETURN NULL;
            END IF;
            SELECT count(*), min(target_ordinal), max(target_ordinal),
                   COALESCE(jsonb_agg(event_id ORDER BY target_ordinal), '[]'::jsonb)
            INTO actual_count, minimum_ordinal, maximum_ordinal, actual_events
            FROM market_data_quality_run_assessments
            WHERE assessment_run_id = run_id;
            SELECT count(*)
            INTO inconsistent_count
            FROM market_data_quality_run_assessments AS membership
            JOIN market_data_quality_assessments AS assessment
              ON assessment.assessment_id = membership.assessment_id
            WHERE membership.assessment_run_id = run_id
              AND (
                  assessment.policy_version_id <> run_policy
                  OR assessment.evaluation_market_as_of <> run_market
                  OR assessment.evaluation_known_as_of <> run_known
              );
            IF actual_count <> expected_count
               OR minimum_ordinal <> 0
               OR maximum_ordinal <> actual_count - 1
               OR actual_events <> expected_events
               OR inconsistent_count <> 0 THEN
                RAISE EXCEPTION
                    'DATA-1.5 assessment run % membership mismatch',
                    run_id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    for table_name in (
        "market_data_quality_assessment_runs",
        "market_data_quality_run_assessments",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table_name}_membership_aggregate "
            f"AFTER INSERT ON {table_name} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION data15_validate_run_membership()"
        )


def _non_empty_data15_tables() -> tuple[str, ...]:
    connection = op.get_bind()
    non_empty: list[str] = []
    for table_name in sorted(DATA15_TABLES):
        if connection.execute(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
        ).scalar_one():
            non_empty.append(table_name)
    return tuple(non_empty)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_trading_session_version_records_record_semantic",
        "trading_session_version_records",
        ("record_id", "session_version_id"),
    )
    for statement in SCHEMA_DDL:
        op.execute(sa.text(statement))
    _backfill_receipts()
    _create_receipt_completeness_guards()
    _create_aggregate_guards()
    _create_append_only_guards()


def downgrade() -> None:
    non_empty = _non_empty_data15_tables()
    if non_empty:
        raise RuntimeError(
            "DATA-1.5 downgrade refused; non-empty tables: "
            + ", ".join(non_empty)
        )

    for source_table, _receipt_table, _target_kind, trigger_name in RECEIPT_TARGETS:
        op.execute(f"DROP TRIGGER {trigger_name} ON {source_table}")
    op.execute(
        "DROP TRIGGER data15_catalogue_membership_receipt_complete "
        "ON catalogue_memberships"
    )

    for table_name in DATA15_TABLES:
        op.execute(f"DROP TRIGGER {table_name}_append_only ON {table_name}")
        op.execute(f"DROP TRIGGER {table_name}_reject_truncate ON {table_name}")

    for table_name in (
        "market_data_quality_policy_versions",
        "market_data_quality_policy_reason_definitions",
    ):
        trigger_name = (
            "data15_policy_version_reason_registry"
            if table_name == "market_data_quality_policy_versions"
            else "data15_reason_definition_registry"
        )
        op.execute(f"DROP TRIGGER {trigger_name} ON {table_name}")
    for table_name in (
        "market_data_quality_assessments",
        "market_data_quality_assessment_reasons",
        "market_data_quality_assessment_dependencies",
    ):
        op.execute(f"DROP TRIGGER {table_name}_aggregate ON {table_name}")
    for table_name in (
        "market_data_quality_assessment_dependencies",
        "market_data_quality_dependency_candidates",
    ):
        op.execute(f"DROP TRIGGER {table_name}_candidate_aggregate ON {table_name}")
    for table_name in (
        "market_data_quality_assessment_runs",
        "market_data_quality_run_assessments",
    ):
        op.execute(f"DROP TRIGGER {table_name}_membership_aggregate ON {table_name}")

    for function_name in reversed(DATA15_FUNCTIONS):
        op.execute(f"DROP FUNCTION {function_name}()")

    for table_name in reversed(DATA15_TABLES):
        op.drop_table(table_name)

    op.drop_constraint(
        "uq_trading_session_version_records_record_semantic",
        "trading_session_version_records",
        type_="unique",
    )
