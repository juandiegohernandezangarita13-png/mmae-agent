"""
Adaptador de conveniencia para jev.core.jev_router importando desde jev_router.
"""
from jev_router import (
    ChoiceResult,
    ScoreResult,
    NoulResult,
    PreFlightDecision,
    TypeSafeSystemOneClient,
    JevRouter,
    default_jev_router,
)

__all__ = [
    "ChoiceResult",
    "ScoreResult",
    "NoulResult",
    "PreFlightDecision",
    "TypeSafeSystemOneClient",
    "JevRouter",
    "default_jev_router",
]
