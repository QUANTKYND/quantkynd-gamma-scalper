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

