"""
Solucionador Numérico de Navier-Stokes en 2D para Flujo Incompresible.
Implementa el Método de Proyección de Chorin en Malla Estructurada con Diferencias Finitas.

Ecuaciones Fundamentales:
1. Continuidad: div(u) = 0
2. Momento: du/dt + (u . grad)u = -1/rho * grad(p) + nu * laplacian(u)
"""
from typing import Tuple, Dict, Any, Optional
import numpy as np

from .boundary_conditions import BoundaryCondition, create_boundary_condition


class NavierStokes2DSolver:
    """
    Solucionador 2D incompresible basado en proyección fraccionada de Chorin.
    
    Etapas por paso temporal:
    1. Campo de velocidad tentativa u* predicho mediante advección-difusión.
    2. Imposición de condiciones de contorno a u*.
    3. Solución iterativa de Poisson para la presión: laplacian(p) = (rho / dt) * div(u*).
    4. Proyección de velocidad: u^{n+1} = u* - (dt / rho) * grad(p).
    5. Imposición final de condiciones de contorno a u^{n+1}.
    """

    def __init__(
        self,
        nx: int = 32,
        ny: int = 32,
        lx: float = 1.0,
        ly: float = 1.0,
        reynolds: float = 100.0,
        rho: float = 1.0,
        boundary_condition: Optional[BoundaryCondition] = None
    ):
        self.nx = int(nx)
        self.ny = int(ny)
        self.lx = float(lx)
        self.ly = float(ly)
        self.reynolds = max(float(reynolds), 1e-6)
        self.rho = max(float(rho), 1e-6)
        self.nu = 1.0 / self.reynolds  # Viscosidad cinemática

        # Discretización espacial
        self.dx = self.lx / (self.nx - 1)
        self.dy = self.ly / (self.ny - 1)
        self.x = np.linspace(0.0, self.lx, self.nx)
        self.y = np.linspace(0.0, self.ly, self.ny)

        # Campos físicos (u: velocidad en X, v: velocidad en Y, p: presión)
        self.u = np.zeros((self.ny, self.nx), dtype=np.float64)
        self.v = np.zeros((self.ny, self.nx), dtype=np.float64)
        self.p = np.zeros((self.ny, self.nx), dtype=np.float64)

        self.bc = boundary_condition or create_boundary_condition("lid_driven_cavity")
        self.bc.apply_velocity(self.u, self.v)
        self.bc.apply_pressure(self.p)

        self.time = 0.0
        self.step_count = 0

    def compute_divergence(self, u: Optional[np.ndarray] = None, v: Optional[np.ndarray] = None) -> np.ndarray:
        """Calcula el campo de divergencia: div(u) = du/dx + dv/dy usando diferencias centradas."""
        u_field = self.u if u is None else u
        v_field = self.v if v is None else v
        div = np.zeros((self.ny, self.nx), dtype=np.float64)

        div[1:-1, 1:-1] = (
            (u_field[1:-1, 2:] - u_field[1:-1, :-2]) / (2.0 * self.dx) +
            (v_field[2:, 1:-1] - v_field[:-2, 1:-1]) / (2.0 * self.dy)
        )
        return div

    def compute_vorticity(self, u: Optional[np.ndarray] = None, v: Optional[np.ndarray] = None) -> np.ndarray:
        """Calcula el campo de vorticidad escalar 2D: omega = dv/dx - du/dy."""
        u_field = self.u if u is None else u
        v_field = self.v if v is None else v
        vort = np.zeros((self.ny, self.nx), dtype=np.float64)

        vort[1:-1, 1:-1] = (
            (v_field[1:-1, 2:] - v_field[1:-1, :-2]) / (2.0 * self.dx) -
            (u_field[2:, 1:-1] - u_field[:-2, 1:-1]) / (2.0 * self.dy)
        )
        return vort

    def check_cfl(self, dt: float) -> Tuple[float, bool]:
        """
        Verifica la condición de estabilidad numérica CFL:
        CFL = dt * (max|u|/dx + max|v|/dy) <= 1.0
        """
        max_u = float(np.max(np.abs(self.u)))
        max_v = float(np.max(np.abs(self.v)))
        cfl = dt * ((max_u / self.dx) + (max_v / self.dy))
        return cfl, cfl <= 1.0

    compute_cfl = check_cfl

    def solve_pressure_poisson(
        self,
        b: np.ndarray,
        p_init: np.ndarray,
        max_iter: int = 250,
        tol: float = 1e-4
    ) -> Tuple[np.ndarray, int, float]:
        """
        Resuelve la ecuación elíptica de Poisson: laplacian(p) = b
        mediante relajación iterativa de Jacobi vectorizada con condiciones Neumann.
        """
        dx2 = self.dx * self.dx
        dy2 = self.dy * self.dy
        denom = 2.0 * (dx2 + dy2)
        p = p_init.copy()

        last_diff = 0.0
        iterations = 0

        for it in range(max_iter):
            iterations = it + 1
            p_new = p.copy()

            # Operador de 5 puntos en el interior del dominio
            p_new[1:-1, 1:-1] = (
                dy2 * (p[1:-1, 2:] + p[1:-1, :-2]) +
                dx2 * (p[2:, 1:-1] + p[:-2, 1:-1]) -
                dx2 * dy2 * b[1:-1, 1:-1]
            ) / denom

            # Imponer condiciones de frontera de presión
            self.bc.apply_pressure(p_new)

            last_diff = float(np.max(np.abs(p_new - p)))
            p = p_new

            if last_diff < tol:
                break

        return p, iterations, last_diff

    def step(
        self,
        dt: float,
        max_poisson_iter: int = 200,
        poisson_tol: float = 1e-4
    ) -> Dict[str, Any]:
        """
        Ejecuta un paso temporal completo mediante el algoritmo de proyección de Chorin.
        """
        u = self.u
        v = self.v
        dx, dy = self.dx, self.dy
        dx2, dy2 = dx * dx, dy * dy

        # -------------------------------------------------------------
        # 1. Velocidad Tentativa u*, v* (Advección + Difusión)
        # -------------------------------------------------------------
        u_star = u.copy()
        v_star = v.copy()

        # Advección (diferencias centradas en interior)
        u_adv_x = u[1:-1, 1:-1] * (u[1:-1, 2:] - u[1:-1, :-2]) / (2.0 * dx)
        u_adv_y = v[1:-1, 1:-1] * (u[2:, 1:-1] - u[:-2, 1:-1]) / (2.0 * dy)

        v_adv_x = u[1:-1, 1:-1] * (v[1:-1, 2:] - v[1:-1, :-2]) / (2.0 * dx)
        v_adv_y = v[1:-1, 1:-1] * (v[2:, 1:-1] - v[:-2, 1:-1]) / (2.0 * dy)

        # Difusión (Laplaciano centrado de 2do orden)
        u_diff = self.nu * (
            (u[1:-1, 2:] - 2.0 * u[1:-1, 1:-1] + u[1:-1, :-2]) / dx2 +
            (u[2:, 1:-1] - 2.0 * u[1:-1, 1:-1] + u[:-2, 1:-1]) / dy2
        )

        v_diff = self.nu * (
            (v[1:-1, 2:] - 2.0 * v[1:-1, 1:-1] + v[1:-1, :-2]) / dx2 +
            (v[2:, 1:-1] - 2.0 * v[1:-1, 1:-1] + v[:-2, 1:-1]) / dy2
        )

        u_star[1:-1, 1:-1] = u[1:-1, 1:-1] + dt * (- (u_adv_x + u_adv_y) + u_diff)
        v_star[1:-1, 1:-1] = v[1:-1, 1:-1] + dt * (- (v_adv_x + v_adv_y) + v_diff)

        # Aplicar condiciones de frontera al campo tentativo
        self.bc.apply_velocity(u_star, v_star)

        # -------------------------------------------------------------
        # 2. Término Fuente del Solucionador de Poisson para la Presión
        #    b = (rho / dt) * div(u*)
        # -------------------------------------------------------------
        b = np.zeros((self.ny, self.nx), dtype=np.float64)
        div_star = (
            (u_star[1:-1, 2:] - u_star[1:-1, :-2]) / (2.0 * dx) +
            (v_star[2:, 1:-1] - v_star[:-2, 1:-1]) / (2.0 * dy)
        )
        b[1:-1, 1:-1] = (self.rho / dt) * div_star

        # -------------------------------------------------------------
        # 3. Resolver Poisson para Presión: laplacian(p) = b
        # -------------------------------------------------------------
        p_new, poisson_iters, poisson_residual = self.solve_pressure_poisson(
            b=b,
            p_init=self.p,
            max_iter=max_poisson_iter,
            tol=poisson_tol
        )
        self.p = p_new

        # -------------------------------------------------------------
        # 4. Proyección / Corrección de Velocidad hacia Divergencia Cero
        #    u^{n+1} = u* - (dt / rho) * dp/dx
        #    v^{n+1} = v* - (dt / rho) * dp/dy
        # -------------------------------------------------------------
        self.u[1:-1, 1:-1] = u_star[1:-1, 1:-1] - (dt / self.rho) * (
            (self.p[1:-1, 2:] - self.p[1:-1, :-2]) / (2.0 * dx)
        )
        self.v[1:-1, 1:-1] = v_star[1:-1, 1:-1] - (dt / self.rho) * (
            (self.p[2:, 1:-1] - self.p[:-2, 1:-1]) / (2.0 * dy)
        )

        # Imponer condiciones finales de frontera
        self.bc.apply_velocity(self.u, self.v)

        # -------------------------------------------------------------
        # 5. Diagnósticos y Métricas de Convergencia
        # -------------------------------------------------------------
        self.time += dt
        self.step_count += 1

        final_div = self.compute_divergence()
        cfl_val, is_cfl_stable = self.check_cfl(dt)
        max_vel = float(np.max(np.sqrt(self.u**2 + self.v**2)))
        kinetic_energy = float(0.5 * np.sum(self.u**2 + self.v**2) * dx * dy)

        return {
            "step": self.step_count,
            "time": float(round(self.time, 6)),
            "dt": dt,
            "cfl": float(round(cfl_val, 4)),
            "cfl_stable": is_cfl_stable,
            "max_divergence": float(np.max(np.abs(final_div[1:-1, 1:-1]))),
            "mean_divergence": float(np.mean(np.abs(final_div[1:-1, 1:-1]))),
            "max_velocity": float(round(max_vel, 4)),
            "kinetic_energy": float(round(kinetic_energy, 6)),
            "poisson_iterations": poisson_iters,
            "poisson_residual": float(round(poisson_residual, 6))
        }
