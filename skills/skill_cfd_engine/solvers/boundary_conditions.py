"""
Módulo de Condiciones de Contorno para Solucionadores CFD en 2D.
Provee implementaciones especializadas para:
1. Cavidad con tapa deslizante (Lid-driven cavity).
2. Flujo en canal con entrada/salida (Channel flow: Inflow/Outflow).
3. Paredes sólidas con no-deslizamiento (No-slip walls).
"""
from typing import Tuple, Optional
import numpy as np


class BoundaryCondition:
    """Clase base abstracta para aplicar condiciones de contorno a campos de velocidad y presión."""

    def apply_velocity(self, u: np.ndarray, v: np.ndarray) -> None:
        """Aplica condiciones de contorno in-place sobre los campos u y v."""
        raise NotImplementedError

    def apply_velocity_bc(self, u: np.ndarray, v: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Alias funcional que aplica las condiciones in-place y retorna la tupla (u, v)."""
        self.apply_velocity(u, v)
        return u, v

    def apply_pressure(self, p: np.ndarray) -> None:
        """Aplica condiciones de contorno in-place sobre el campo de presión p."""
        raise NotImplementedError


class LidDrivenCavityBC(BoundaryCondition):
    """
    Condición de contorno para la cavidad clásica con tapa móvil (Lid-driven cavity):
    - Pared superior (y = Ly): u = u_lid, v = 0
    - Pared inferior (y = 0): u = 0, v = 0
    - Pared izquierda (x = 0): u = 0, v = 0
    - Pared derecha (x = Lx): u = 0, v = 0
    - Presión: dp/dn = 0 (Neumann homogéneo en todas las paredes) con anclaje en p[0, 0] = 0
    """

    def __init__(self, u_lid: float = 1.0):
        self.u_lid = float(u_lid)

    def apply_velocity(self, u: np.ndarray, v: np.ndarray) -> None:
        # Pared superior: tapa móvil deslizante
        u[-1, :] = self.u_lid
        v[-1, :] = 0.0

        # Pared inferior: no-slip
        u[0, :] = 0.0
        v[0, :] = 0.0

        # Pared izquierda: no-slip
        u[:, 0] = 0.0
        v[:, 0] = 0.0

        # Pared derecha: no-slip
        u[:, -1] = 0.0
        v[:, -1] = 0.0

    def apply_pressure(self, p: np.ndarray) -> None:
        # Neumann homogéneo en todas las paredes: dp/dn = 0
        p[:, -1] = p[:, -2]  # Derecha (dp/dx = 0)
        p[:, 0] = p[:, 1]    # Izquierda (dp/dx = 0)
        p[-1, :] = p[-2, :]  # Superior (dp/dy = 0)
        p[0, :] = p[1, :]    # Inferior (dp/dy = 0)

        # Fijar presión en punto de referencia para garantizar unicidad del operador de Poisson
        p[0, 0] = 0.0


class ChannelFlowBC(BoundaryCondition):
    """
    Condición de contorno para flujo en canal (Poiseuille / Inflow-Outflow):
    - Entrada (x = 0): Perfil parabólico o constante u = u_in(y), v = 0
    - Salida (x = Lx): Gradiente nulo du/dx = 0, dv/dx = 0, p = 0 (Presión de escape)
    - Paredes sup/inf: No-slip u = 0, v = 0, dp/dy = 0
    """

    def __init__(self, u_inlet: float = 1.0, u_inflow: Optional[float] = None, parabolic: bool = True):
        self.u_inlet = float(u_inflow if u_inflow is not None else u_inlet)
        self.parabolic = bool(parabolic)

    def apply_velocity(self, u: np.ndarray, v: np.ndarray) -> None:
        ny, _ = u.shape

        # Paredes sólidas superior e inferior (no-slip)
        u[0, :] = 0.0
        v[0, :] = 0.0
        u[-1, :] = 0.0
        v[-1, :] = 0.0

        # Entrada (Inlet en x = 0)
        if self.parabolic:
            # Perfil parabólico u(y) = 4 * Umax * y * (1 - y)
            y_norm = np.linspace(0.0, 1.0, ny)
            u[:, 0] = 4.0 * self.u_inlet * y_norm * (1.0 - y_norm)
        else:
            u[:, 0] = self.u_inlet
            u[0, 0] = 0.0
            u[-1, 0] = 0.0
        v[:, 0] = 0.0

        # Salida (Outflow en x = Lx): Convectiva o gradiente nulo du/dx = 0
        u[:, -1] = u[:, -2]
        v[:, -1] = v[:, -2]

    def apply_pressure(self, p: np.ndarray) -> None:
        # Paredes sup/inf: dp/dy = 0
        p[0, :] = p[1, :]
        p[-1, :] = p[-2, :]

        # Entrada: dp/dx = 0
        p[:, 0] = p[:, 1]

        # Salida: Presión manométrica de referencia p = 0
        p[:, -1] = 0.0


class NoSlipWallBC(BoundaryCondition):
    """Condición pura de no-deslizamiento estático en las cuatro fronteras."""

    def apply_velocity(self, u: np.ndarray, v: np.ndarray) -> None:
        u[0, :] = 0.0
        v[0, :] = 0.0
        u[-1, :] = 0.0
        v[-1, :] = 0.0
        u[:, 0] = 0.0
        v[:, 0] = 0.0
        u[:, -1] = 0.0
        v[:, -1] = 0.0

    def apply_pressure(self, p: np.ndarray) -> None:
        p[:, -1] = p[:, -2]
        p[:, 0] = p[:, 1]
        p[-1, :] = p[-2, :]
        p[0, :] = p[1, :]
        p[0, 0] = 0.0


def create_boundary_condition(scenario: str = "lid_driven_cavity", **kwargs) -> BoundaryCondition:
    """Fábrica para instanciar condiciones de contorno por nombre."""
    scenario_clean = (scenario or "lid_driven_cavity").strip().lower()
    if scenario_clean in ["lid_driven_cavity", "cavity", "lid"]:
        u_lid = kwargs.get("u_lid", 1.0)
        return LidDrivenCavityBC(u_lid=u_lid)
    elif scenario_clean in ["channel_flow", "channel", "pipe"]:
        u_inlet = kwargs.get("u_inlet", 1.0)
        parabolic = kwargs.get("parabolic", True)
        return ChannelFlowBC(u_inlet=u_inlet, parabolic=parabolic)
    else:
        return NoSlipWallBC()
