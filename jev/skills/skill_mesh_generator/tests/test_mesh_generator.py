"""
Pruebas unitarias para skill_mesh_generator.
"""
import unittest
from jev.skills.skill_mesh_generator.handler import handle, create_box, create_sphere, create_cylinder, create_torus


class TestSkillMeshGenerator(unittest.TestCase):

    def test_01_create_box(self):
        res = handle(shape="box", params={"width": 3, "color": "#ff0000"})
        self.assertEqual(res["status"], "success")
        elem = res["element"]
        self.assertEqual(elem["geometry"]["type"], "BoxGeometry")
        self.assertEqual(elem["geometry"]["parameters"]["width"], 3.0)
        self.assertEqual(elem["material"]["color"], "#ff0000")

    def test_02_create_sphere_and_cylinder(self):
        sphere_res = handle(shape="sphere", params={"radius": 2.5})
        self.assertEqual(sphere_res["element"]["geometry"]["type"], "SphereGeometry")

        cyl_res = handle(shape="cylinder", params={"height": 5.0})
        self.assertEqual(cyl_res["element"]["geometry"]["type"], "CylinderGeometry")

    def test_03_composite_scene(self):
        scene_res = handle(shape="composite_scene")
        self.assertIn("scene", scene_res)
        self.assertGreaterEqual(len(scene_res["scene"]["elements"]), 3)


if __name__ == "__main__":
    unittest.main()
