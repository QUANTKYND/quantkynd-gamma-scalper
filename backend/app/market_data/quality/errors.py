"""Typed DATA-1.5 errors.

Market-quality defects are represented by controlled reasons, not these
exceptions. These exceptions represent invalid commands, unsupported policy
artifacts, identity collisions, referential failures, durable corruption, or
transaction failures that abort the whole operation.
"""


class MarketDataQualityError(Exception):
    """Base class for DATA-1.5 failures."""


class InvalidQualityPolicyDocumentError(MarketDataQualityError, ValueError):
    """The policy source is malformed, ambiguous, or outside schema v1."""


class UnsupportedQualityPolicyError(MarketDataQualityError, ValueError):
    """The policy schema/evaluator compatibility tuple is unsupported."""


class QualityIdentityCollisionError(MarketDataQualityError):
    """A deterministic identity is already bound to different content."""


class QualityPolicyCollisionError(QualityIdentityCollisionError):
    pass


class QualityPolicyVersionCollisionError(QualityIdentityCollisionError):
    pass


class QualityReasonRegistryCollisionError(QualityIdentityCollisionError):
    pass


class QualityAssessmentCollisionError(QualityIdentityCollisionError):
    pass


class QualityAssessmentRunCollisionError(QualityIdentityCollisionError):
    pass


class QualityDependencyClosureCollisionError(QualityIdentityCollisionError):
    pass


class QualityRunMembershipCollisionError(QualityIdentityCollisionError):
    pass


class InvalidQualityEvaluationCommandError(MarketDataQualityError, ValueError):
    """The explicit event/policy/cutoff command is invalid."""


class UnsupportedQualityObservationKindError(MarketDataQualityError, ValueError):
    """The evaluator received an observation kind outside DATA-1.5 v1."""


class QualityDependencyAmbiguityError(MarketDataQualityError):
    """Reserved for orchestration-level ambiguity that cannot become a reason."""


class QualityReferentialIntegrityError(MarketDataQualityError):
    """A required durable foreign-key relationship is missing or inconsistent."""


class QualityDurableCorruptionError(MarketDataQualityError):
    """Durable content fails identity, hash, graph, count, or payload checks."""


class QualityConcurrencyError(MarketDataQualityError):
    """A serialization/deadlock failure exhausted the bounded retry policy."""
