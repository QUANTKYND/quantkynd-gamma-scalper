class PersistenceError(Exception):
    pass

class PersistenceCollisionError(PersistenceError):
    pass
class ReferentialIntegrityError(PersistenceError):
    pass
class PersistenceConcurrencyError(PersistenceError):
    pass
class PersistenceTimeBindingError(PersistenceError):
    pass
class MarketEventDurableCorruptionError(PersistenceError):
    pass
class DurableCorruptionError(MarketEventDurableCorruptionError):
    pass

class RawCaptureIdentityConflictError(PersistenceCollisionError): pass
class RawFrameContentMismatchError(PersistenceCollisionError): pass
class NormalizationResultConflictError(PersistenceCollisionError): pass
class NormalizedEventIdentityConflictError(PersistenceCollisionError): pass
class NormalizationFailureIdentityConflictError(PersistenceCollisionError): pass
class LifecycleIdentityConflictError(PersistenceCollisionError): pass
class InstrumentSetDigestCollisionError(PersistenceCollisionError): pass
class CatalogueProvenanceConflictError(PersistenceCollisionError): pass
class MarketEventReferentialIntegrityError(ReferentialIntegrityError): pass
