"""
Suite de Pruebas Unitarias para el Motor CFD (Fluid Dynamics PDE Solver).
Verifica:
1. Conservación de masa e incompresibilidad (divergencia mínima post-proyección de Chorin).
2. Estabilidad temporal y cálculo del número CFL.
3. Condiciones de contorno (Lid-driven cavity, Channel flow, No-slip).
4. Fachada FluidDynamicsEngine y punto de entrada handle().
5. Generación de especificaciones de escena 3D para Three.js Viewport.
6. Carga y ejecución reflexiva a través del SkillRegistry.
"""
import unittest
import numpy as np
from pathlib import Path

from jev.skills.skill_cfd_engine.solvers.boundary_conditions import (
    LidDrivenCavityBC,
    ChannelFlowBC,
    NoSlipWallBC,
    create_boundary_condition
)
from jev.skills.skill_cfd_engine.solvers.navier_stokes_2d import NavierStokes2DSolver
from jev.skills.skill_cfd_engine.handler import FluidDynamicsEngine, handle
from jev.skills.manager import SkillRegistry


class TestNavierStokes2DSolver(unittest.TestCase):
    """Pruebas del solver numérico de Navier-Stokes en 2D."""

    def setUp(self):
        self.nx = 16
        self.ny = 16
        self.bc = LidDrivenCavityBC(u_lid=1.0)
        self.solver = NavierStokes2DSolver(
            nx=self.nx,
            ny=self.ny,
            lx=1.0,
            ly=1.0,
            reynolds=100.0,
            boundary_condition=self.bc
        )

    def test_initial_state_and_dimensions(self):
        """Verifica inicialización de rejillas y dimensiones concordantes."""
        self.assertEqual(self.solver.u.shape, (self.ny, self.nx))
        self.assertEqual(self.solver.v.shape, (self.ny, self.nx))
        self.assertEqual(self.solver.p.shape, (self.ny, self.nx))
        self.assertEqual(len(self.solver.x), self.nx)
        self.assertEqual(len(self.solver.y), self.ny)
        self.assertAlmostEqual(self.solver.dx, 1.0 / (self.nx - 1))
        self.assertAlmostEqual(self.solver.dy, 1.0 / (self.ny - 1))

    def test_divergence_free_projection(self):
        """
        Verifica que tras resolver el Poisson de presión y aplicar el paso de proyección,
        la divergencia numérica se mantiene acotada y pequeña (conservación de masa).
        """
        # Ejecutar 5 pasos temporales
        for _ in range(5):
            diag = self.solver.step(dt=0.001)

        div = self.solver.compute_divergence(self.solver.u, self.solver.v)
        interior_div = div[1:-1, 1:-1]
        mean_abs_div = float(np.mean(np.abs(interior_div)))

        # La divergencia media en el interior debe ser pequeña
        self.assertLess(mean_abs_div, 0.5, f"La divergencia interior promedio ({mean_abs_div}) es excesiva.")
        self.assertIn("max_divergence", diag)
        self.assertIn("mean_divergence", diag)

    def test_cfl_condition(self):
        """Verifica el cálculo del número CFL y la bandera de estabilidad."""
        # Velocidad inicial con tapa móvil (u_lid = 1.0)
        cfl_init, stable_init = self.solver.compute_cfl(dt=0.001)
        expected_init_cfl = 1.0 * 0.001 / self.solver.dx
        self.assertAlmostEqual(cfl_init, expected_init_cfl, places=4)
        self.assertTrue(stable_init)

        # Aplicar velocidad artificial mayor y verificar incremento de CFL
        self.solver.u[5, 5] = 2.0
        cfl, stable = self.solver.compute_cfl(dt=0.001)
        expected_cfl = 2.0 * 0.001 / self.solver.dx
        self.assertAlmostEqual(cfl, expected_cfl, places=4)
        self.assertTrue(stable)

    def test_vorticity_computation(self):
        """Verifica que el campo de vorticidad se calcula sin NaNs ni infinitos."""
        self.solver.step(dt=0.001)
        vort = self.solver.compute_vorticity()
        self.assertEqual(vort.shape, (self.ny, self.nx))
        self.assertFalse(np.isnan(vort).any())
        self.assertFalse(np.isinf(vort).any())


class TestBoundaryConditions(unittest.TestCase):
    """Pruebas de las condiciones de contorno físicas."""

    def test_lid_driven_cavity_bc(self):
        """Verifica condiciones de contorno de tapa móvil y paredes no-slip."""
        bc = LidDrivenCavityBC(u_lid=1.0)
        u = np.zeros((8, 8))
        v = np.zeros((8, 8))

        u, v = bc.apply_velocity_bc(u, v)
        # Interior de la tapa superior debe tener u = 1.0
        np.testing.assert_allclose(u[-1, 1:-1], 1.0)
        # Esquinas superiores sujetas a no-slip lateral
        self.assertEqual(u[-1, 0], 0.0)
        self.assertEqual(u[-1, -1], 0.0)
        # Fondo (índice 0) debe tener u = 0.0
        np.testing.assert_allclose(u[0, :], 0.0)
        # Paredes laterales deben tener u = 0.0
        np.testing.assert_allclose(u[:, 0], 0.0)
        np.testing.assert_allclose(u[:, -1], 0.0)
        # v debe ser 0 en todas las paredes
        np.testing.assert_allclose(v[-1, :], 0.0)
        np.testing.assert_allclose(v[0, :], 0.0)

    def test_channel_flow_bc(self):
        """Verifica perfil parabólico de Poiseuille en canal."""
        bc = ChannelFlowBC(u_inflow=2.0)
        u = np.zeros((10, 10))
        v = np.zeros((10, 10))

        u, v = bc.apply_velocity_bc(u, v)
        # Entrada en columna 0 debe tener velocidad positiva con máximo en el centro
        inflow = u[:, 0]
        self.assertGreater(inflow[5], 0.0)
        self.assertEqual(inflow[0], 0.0)  # Pared inferior
        self.assertEqual(inflow[-1], 0.0)  # Pared superior

    def test_boundary_factory(self):
        """Verifica la fábrica de condiciones de contorno."""
        bc_lid = create_boundary_condition("lid_driven_cavity")
        self.assertIsInstance(bc_lid, LidDrivenCavityBC)

        bc_chan = create_boundary_condition("channel_flow")
        self.assertIsInstance(bc_chan, ChannelFlowBC)

        bc_noslip = create_boundary_condition("no_slip")
        self.assertIsInstance(bc_noslip, NoSlipWallBC)


class TestFluidDynamicsEngineFacade(unittest.TestCase):
    """Pruebas de la fachada de alto nivel FluidDynamicsEngine y handle()."""

    def test_engine_solve_step(self):
        """Verifica ejecución de un único paso con resultado estructurado."""
        engine = FluidDynamicsEngine(nx=16, ny=16, reynolds=50.0)
        res = engine.solve_step(dt=0.001, export_threejs=True)

        self.assertEqual(res.step, 1)
        self.assertAlmostEqual(res.time, 0.001)
        self.assertTrue(res.cfl_stable)
        self.assertIsNotNone(res.threejs_scene)
        self.assertIn("elements", res.threejs_scene)

    def test_engine_run_simulation(self):
        """Verifica ejecución por lotes de pasos temporales."""
        engine = FluidDynamicsEngine(nx=16, ny=16, scenario="lid_driven_cavity")
        sim_data = engine.run_simulation(steps=5, dt=0.001, export_threejs=True)

        self.assertEqual(sim_data["scenario"], "lid_driven_cavity")
        self.assertEqual(sim_data["total_steps"], 5)
        self.assertEqual(len(sim_data["history_sample"]), 5)
        self.assertIn("threejs_scene", sim_data)

    def test_threejs_viewport_format(self):
        """Verifica que la escena generada para Three.js tenga la estructura correcta."""
        engine = FluidDynamicsEngine(nx=16, ny=16)
        # Dar unos pasos para generar vectores de velocidad no nulos
        engine.run_simulation(steps=3, dt=0.001, export_threejs=False)
        scene = engine.export_threejs_vector_field(subsample=2)

        self.assertIn("background", scene)
        self.assertIn("ambient_light", scene)
        self.assertIn("elements", scene)

        # Debe contener al menos el grid_helper y elementos arrow_helper
        elements = scene["elements"]
        self.assertTrue(any(el.get("type") == "grid_helper" for el in elements))
        self.assertTrue(any(el.get("type") == "arrow_helper" for el in elements))

        # Verificar campos de un arrow_helper
        arrow = next(el for el in elements if el.get("type") == "arrow_helper")
        self.assertIn("direction", arrow)
        self.assertEqual(len(arrow["direction"]), 3)
        self.assertIn("origin", arrow)
        self.assertEqual(len(arrow["origin"]), 3)
        self.assertIn("length", arrow)
        self.assertIn("color", arrow)

    def test_handle_function_entrypoints(self):
        """Verifica el punto de entrada estándar handle() con diversas acciones."""
        # get_info
        info = handle(action="get_info")
        self.assertEqual(info["status"], "success")
        self.assertEqual(info["action"], "get_info")

        # solve_step
        step_out = handle(action="solve_step", nx=16, ny=16, dt=0.001)
        self.assertEqual(step_out["status"], "success")
        self.assertEqual(step_out["action"], "solve_step")

        # run_simulation (default)
        sim_out = handle(nx=16, ny=16, steps=3, dt=0.001)
        self.assertEqual(sim_out["status"], "success")
        self.assertEqual(sim_out["action"], "run_simulation")
        self.assertIn("simulation", sim_out)


class TestSkillRegistryIntegration(unittest.TestCase):
    """Verifica el registro reflexivo y pasivo en SkillRegistry."""

    def test_skill_discovery_and_metadata(self):
        registry = SkillRegistry()
        skill = registry.get_skill("fluid_dynamics_pde_solver")
        self.assertIsNotNone(skill, "La habilidad 'fluid_dynamics_pde_solver' debe ser descubierta.")

        meta = skill.metadata
        self.assertEqual(meta.name, "fluid_dynamics_pde_solver")
        self.assertEqual(meta.version, "1.0.0")
        self.assertEqual(meta.category, "physics_simulation")
        self.assertIn("navier-stokes", meta.trigger_keywords)
        self.assertIn("cfd", meta.trigger_keywords)

    def test_passive_execution_via_registry(self):
        registry = SkillRegistry()
        result = registry.execute_skill(
            "fluid_dynamics_pde_solver",
            action="run_simulation",
            nx=16,
            ny=16,
            steps=2,
            dt=0.001,
            export_viewport_3d=True
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "run_simulation")
        self.assertIn("scene", result)


if __name__ == "__main__":
    unittest.main()
