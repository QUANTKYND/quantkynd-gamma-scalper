from __future__ import annotations

from pathlib import Path

import pytest

from app.market_data.quality.errors import (
    InvalidQualityPolicyDocumentError,
    UnsupportedQualityPolicyError,
)
from app.market_data.quality.policy_parser import parse_quality_policy


_REPO_ROOT = Path(__file__).resolve().parents[5]
_POLICY_PATH = (
    _REPO_ROOT
    / "config"
    / "data_quality"
    / "upstox-nse-market-observation-quality-v1.yaml"
)


def _source() -> bytes:
    return _POLICY_PATH.read_bytes()


def test_reviewed_policy_parses_to_frozen_semantics() -> None:
    policy = parse_quality_policy(_source())

    assert policy.policy_id == (
        "sha256:eb8daac12517a8e65f25e2a0aee14cda8eeb4a3b2308a80719f747bdcb333d01"
    )
    assert policy.policy_version_id == (
        "sha256:66375faab3876f809670bdd7e2a04ec7ea5d152a0919db65cbcae8ef133f0bfd"
    )
    assert policy.policy_definition_hash == (
        "sha256:0f13b2ddc0a030b470729a99d63c03bbb55f50149949d747ed1fb76f6684b41e"
    )
    assert policy.source_sha256 == (
        "sha256:a7ac9e0540341f1939a34211931b152f9a944356b98f67f11b12f95a676872b4"
    )
    assert policy.source_artifact_id == (
        "sha256:2aad1ef1b420fed3a4434598f370b6d1794013d3e6d14b3301f0181bc958f842"
    )
    assert len(policy.reason_definitions) == 69
    assert tuple(item.ordinal for item in policy.reason_definitions) == tuple(range(1, 70))


def test_formatting_and_line_endings_change_only_source_identity() -> None:
    original = parse_quality_policy(_source())
    formatted = _source().decode("utf-8").replace(
        'schema_version: "1"\n',
        '# equivalent formatting\nschema_version: "1"\n',
        1,
    ).replace("\n", "\r\n").encode("utf-8")

    reparsed = parse_quality_policy(formatted)

    assert reparsed.policy_id == original.policy_id
    assert reparsed.policy_version_id == original.policy_version_id
    assert reparsed.policy_definition_hash == original.policy_definition_hash
    assert reparsed.source_sha256 != original.source_sha256
    assert reparsed.source_artifact_id != original.source_artifact_id


def test_threshold_mutation_changes_semantics_under_same_version_identity() -> None:
    original = parse_quality_policy(_source())
    mutated = _source().replace(
        b'warning_ms: "3000"',
        b'warning_ms: "3001"',
        1,
    )

    reparsed = parse_quality_policy(mutated)

    assert reparsed.policy_version_id == original.policy_version_id
    assert reparsed.policy_definition_hash != original.policy_definition_hash
    assert reparsed.source_artifact_id != original.source_artifact_id


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source.replace(
            b'schema_version: "1"\n',
            b'schema_version: "1"\nschema_version: "1"\n',
            1,
        ),
        lambda source: source.replace(b"policy:\n", b"policy: &policy_anchor\n", 1),
        lambda source: source + b"\n---\nschema_version: \"1\"\n",
        lambda source: source.replace(
            b'schema_version: "1"\n',
            b'schema_version: "1"\nunknown_key: value\n',
            1,
        ),
        lambda source: b"\xef\xbb\xbf" + source,
        lambda source: source + b"\x00",
        lambda source: source.replace(
            b'warning_ticks: "5"',
            b'warning_ticks: "5e0"',
            1,
        ),
        lambda source: source.replace(
            b'warning_ms: "3000"',
            b'warning_ms: "10000"',
            1,
        ),
        lambda source: source.replace(
            b"historical_import_availability",
            b"historical_import_changed",
            1,
        ),
    ],
)
def test_invalid_or_ambiguous_policy_sources_fail_closed(mutator) -> None:
    with pytest.raises(InvalidQualityPolicyDocumentError):
        parse_quality_policy(mutator(_source()))


def test_unsupported_compatibility_fails_with_typed_error() -> None:
    mutated = _source().replace(
        b"market-data-quality-evaluator-1",
        b"market-data-quality-evaluator-2",
        1,
    )

    with pytest.raises(UnsupportedQualityPolicyError):
        parse_quality_policy(mutated)
