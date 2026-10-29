"""
Fachada de Integración para el Motor de Dinámica de Fluidos (CFD Engine).
Punto de enlace con el MoAE Router, ToolRegistry y el 3D Viewport de JEV.
"""
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import json
import math
import numpy as np

import sys
from pathlib import Path

# Garantizar resolución de subpaquetes locales cuando el skill es cargado directamente por el SkillRegistry
_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

try:
    from solvers.boundary_conditions import create_boundary_condition
    from solvers.navier_stokes_2d import NavierStokes2DSolver
except (ImportError, ValueError):
    from .solvers.boundary_conditions import create_boundary_condition
    from .solvers.navier_stokes_2d import NavierStokes2DSolver


@dataclass(slots=True)
class SimulationStepResult:
    """Resultado estructurado de un paso de simulación CFD."""
    step: int
    time: float
    dt: float
    cfl: float
    cfl_stable: bool
    max_divergence: float
    mean_divergence: float
    max_velocity: float
    kinetic_energy: float
    grid_shape: Tuple[int, int]
    u: List[List[float]]
    v: List[List[float]]
    pressure: List[List[float]]
    vorticity: List[List[float]]
    threejs_scene: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "step": self.step,
            "time": self.time,
            "dt": self.dt,
            "cfl": self.cfl,
            "cfl_stable": self.cfl_stable,
            "max_divergence": self.max_divergence,
            "mean_divergence": self.mean_divergence,
            "max_velocity": self.max_velocity,
            "kinetic_energy": self.kinetic_energy,
            "grid_shape": list(self.grid_shape),
            "u": self.u,
            "v": self.v,
            "pressure": self.pressure,
            "vorticity": self.vorticity
        }
        if self.threejs_scene:
            res["threejs_scene"] = self.threejs_scene
        return res


class FluidDynamicsEngine:
    """
    Motor unificado de simulación numérica para dinámica de fluidos incompresible.
    Maneja la inicialización, pasos temporales e interoperabilidad con Three.js.
    """

    def __init__(
        self,
        nx: int = 32,
        ny: int = 32,
        lx: float = 1.0,
        ly: float = 1.0,
        reynolds: float = 100.0,
        rho: float = 1.0,
        scenario: str = "lid_driven_cavity"
    ):
        self.nx = int(nx)
        self.ny = int(ny)
        self.lx = float(lx)
        self.ly = float(ly)
        self.reynolds = float(reynolds)
        self.rho = float(rho)
        self.scenario = scenario

        bc = create_boundary_condition(scenario)
        self.solver = NavierStokes2DSolver(
            nx=self.nx,
            ny=self.ny,
            lx=self.lx,
            ly=self.ly,
            reynolds=self.reynolds,
            rho=self.rho,
            boundary_condition=bc
        )

    def solve_step(
        self,
        velocity_field: Optional[Tuple[np.ndarray, np.ndarray]] = None,
        pressure_field: Optional[np.ndarray] = None,
        dt: float = 0.001,
        reynolds: Optional[float] = None,
        export_threejs: bool = False
    ) -> SimulationStepResult:
        """
        Ejecuta un paso numérico. Si se proporcionan campos externos, actualiza el estado.
        """
        if velocity_field is not None:
            u_in, v_in = velocity_field
            self.solver.u = np.array(u_in, dtype=np.float64)
            self.solver.v = np.array(v_in, dtype=np.float64)
        if pressure_field is not None:
            self.solver.p = np.array(pressure_field, dtype=np.float64)
        if reynolds is not None:
            self.solver.reynolds = float(reynolds)
            self.solver.nu = 1.0 / self.solver.reynolds

        diag = self.solver.step(dt=dt)
        vorticity = self.solver.compute_vorticity()

        threejs_data = self.export_threejs_vector_field() if export_threejs else None

        return SimulationStepResult(
            step=diag["step"],
            time=diag["time"],
            dt=diag["dt"],
            cfl=diag["cfl"],
            cfl_stable=diag["cfl_stable"],
            max_divergence=diag["max_divergence"],
            mean_divergence=diag["mean_divergence"],
            max_velocity=diag["max_velocity"],
            kinetic_energy=diag["kinetic_energy"],
            grid_shape=(self.ny, self.nx),
            u=self.solver.u.tolist(),
            v=self.solver.v.tolist(),
            pressure=self.solver.p.tolist(),
            vorticity=vorticity.tolist(),
            threejs_scene=threejs_data
        )

    def run_simulation(
        self,
        steps: int = 10,
        dt: float = 0.001,
        export_threejs: bool = True
    ) -> Dict[str, Any]:
        """
        Avanza la simulación por una cantidad determinada de pasos temporales y retorna un resumen completo.
        """
        history = []
        last_step_result = None

        for _ in range(steps):
            last_step_result = self.solve_step(dt=dt, export_threejs=False)
            history.append({
                "step": last_step_result.step,
                "time": last_step_result.time,
                "cfl": last_step_result.cfl,
                "max_div": last_step_result.max_divergence,
                "max_vel": last_step_result.max_velocity,
                "ke": last_step_result.kinetic_energy
            })

        threejs_scene = self.export_threejs_vector_field() if export_threejs else None

        return {
            "scenario": self.scenario,
            "reynolds": self.reynolds,
            "grid": [self.nx, self.ny],
            "total_steps": steps,
            "final_time": round(self.solver.time, 6),
            "dt": dt,
            "cfl_stable": last_step_result.cfl_stable if last_step_result else True,
            "final_diagnostics": {
                "max_divergence": last_step_result.max_divergence if last_step_result else 0.0,
                "mean_divergence": last_step_result.mean_divergence if last_step_result else 0.0,
                "max_velocity": last_step_result.max_velocity if last_step_result else 0.0,
                "kinetic_energy": last_step_result.kinetic_energy if last_step_result else 0.0,
            },
            "history_sample": history[-5:],
            "threejs_scene": threejs_scene
        }

    def export_threejs_vector_field(self, subsample: int = 2) -> Dict[str, Any]:
        """
        Genera una especificación de escena 3D compatible con Three.js Viewport
        con vectores de velocidad (arrow_helper) coloreados por magnitud y vorticidad.
        """
        u = self.solver.u
        v = self.solver.v
        speed = np.sqrt(u**2 + v**2)
        max_speed = float(np.max(speed)) or 1.0

        elements = []
        # Rejilla base en plano XY centrado
        elements.append({
            "type": "grid_helper",
            "name": "CFD_Domain_Grid",
            "parameters": {
                "size": 10.0,
                "divisions": 10,
                "colorCenterLine": "#00f0ff",
                "colorGrid": "#1e293b"
            },
            "position": [0, -0.05, 0]
        })

        scale_factor = 8.0  # Mapear dominio [0, 1] a [-4, 4] en Three.js
        stride = max(1, subsample)

        for i in range(0, self.ny, stride):
            for j in range(0, self.nx, stride):
                spd = speed[i, j]
                if spd < 1e-4:
                    continue

                # Posición normalizada centrada en el origen
                pos_x = (self.solver.x[j] - 0.5 * self.lx) * scale_factor
                pos_y = (self.solver.y[i] - 0.5 * self.ly) * scale_factor
                pos_z = 0.0

                # Dirección normalizada del vector de velocidad
                dir_x = float(u[i, j] / spd)
                dir_y = float(v[i, j] / spd)
                dir_z = 0.0

                # Longitud proporcional a la magnitud
                arrow_len = float(min(1.2, max(0.2, (spd / max_speed) * 0.9)))

                # Mapa de color: cyan para velocidad baja, amarillo/magenta para alta
                ratio = min(1.0, spd / max_speed)
                if ratio > 0.6:
                    color_hex = 0xff0077  # Magenta de alta velocidad
                elif ratio > 0.3:
                    color_hex = 0xffaa00  # Amarillo medio
                else:
                    color_hex = 0x00f0ff  # Cyan laminar

                elements.append({
                    "type": "arrow_helper",
                    "name": f"Vel_Vector_{i}_{j}",
                    "direction": [dir_x, dir_y, dir_z],
                    "origin": [pos_x, pos_y, pos_z],
                    "length": arrow_len,
                    "color": color_hex,
                    "headLength": arrow_len * 0.35,
                    "headWidth": arrow_len * 0.25
                })

        return {
            "background": "#050811",
            "ambient_light": {"color": "#ffffff", "intensity": 0.7},
            "directional_light": {"color": "#00f0ff", "intensity": 1.2, "position": [5, 10, 7]},
            "elements": elements
        }


def handle(action: str = "run_simulation", **kwargs) -> Dict[str, Any]:
    """Punto de entrada estándar para el SkillRegistry y ToolRegistry de JEV."""
    action_clean = (action or "run_simulation").strip().lower()

    nx = int(kwargs.get("nx", 32))
    ny = int(kwargs.get("ny", 32))
    lx = float(kwargs.get("lx", 1.0))
    ly = float(kwargs.get("ly", 1.0))
    reynolds = float(kwargs.get("reynolds", 100.0))
    scenario = kwargs.get("scenario", "lid_driven_cavity")
    dt = float(kwargs.get("dt", 0.001))
    steps = int(kwargs.get("steps", 10))
    export_3d = bool(kwargs.get("export_viewport_3d", True))

    engine = FluidDynamicsEngine(
        nx=nx,
        ny=ny,
        lx=lx,
        ly=ly,
        reynolds=reynolds,
        scenario=scenario
    )

    if action_clean == "solve_step":
        res = engine.solve_step(dt=dt, export_threejs=export_3d)
        return {
            "status": "success",
            "action": "solve_step",
            "result": res.to_dict()
        }
    elif action_clean == "get_info":
        return {
            "status": "success",
            "action": "get_info",
            "solver": "NavierStokes2DSolver (Chorin Projection)",
            "supported_scenarios": ["lid_driven_cavity", "channel_flow"],
            "features": ["Incompressible flow", "Divergence-free projection", "Vorticity analysis", "Three.js Viewport 3D export"]
        }
    else:
        # Default: run_simulation
        sim_data = engine.run_simulation(steps=steps, dt=dt, export_threejs=export_3d)
        result_payload = {
            "status": "success",
            "action": "run_simulation",
            "simulation": sim_data
        }
        if export_3d and sim_data.get("threejs_scene"):
            result_payload["scene"] = sim_data["threejs_scene"]
        return result_payload
