"""
Paquete de solucionadores numéricos CFD para JEV.
"""
from .boundary_conditions import (
    BoundaryCondition,
    LidDrivenCavityBC,
    ChannelFlowBC,
    NoSlipWallBC,
    create_boundary_condition
)
from .navier_stokes_2d import NavierStokes2DSolver

__all__ = [
    "BoundaryCondition",
    "LidDrivenCavityBC",
    "ChannelFlowBC",
    "NoSlipWallBC",
    "create_boundary_condition",
    "NavierStokes2DSolver"
]
