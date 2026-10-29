"""
Suite de Pruebas Unitarias para Protocolos Edge, IoT y Hardware (JEV Extended Skills):
1. skill_rf_adsb_tracker (Dump1090 / ADS-B / Mode-S / SBS-1)
2. skill_meshtastic_gateway (Meshtastic LoRa Off-Grid)
3. skill_frigate_vision_bridge (Frigate NVR / MQTT / Computer Vision)
4. skill_odm_photogrammetry (OpenDroneMap / NodeODM / 3D Reconstruction)
5. skill_openpilot_telemetry (Comma.ai Openpilot / Cereal / Autonomous Driving)
6. Integración con SkillRegistry y ToolRegistry
"""
import unittest
import json
import time
from pathlib import Path

from jev.tools.custom.skill_rf_adsb import RFAdsbTrackerTool
from jev.tools.custom.skill_meshtastic import MeshtasticGatewayTool
from jev.tools.custom.skill_frigate import FrigateVisionBridgeTool
from jev.tools.custom.skill_odm import OdmPhotogrammetryTool
from jev.tools.custom.skill_openpilot import OpenpilotTelemetryTool
from jev.skills.manager import SkillRegistry
from jev.tools.base import ToolRegistry
from jev.tools.dynamic_loader import DynamicToolManager


class TestRFAdsbTracker(unittest.TestCase):
    """Pruebas del decodificador ADS-B y Dump1090."""

    def setUp(self):
        self.tool = RFAdsbTrackerTool()

    def test_parse_sbs1_stream(self):
        """Verifica parseo de líneas CSV de BaseStation SBS-1."""
        sample_sbs = (
            "MSG,1,111,11111,3442DE,111111,2026/10/13,12:00:00.000,2026/10/13,12:00:00.000,IBE3842,,,,,,,,,,,\n"
            "MSG,3,111,11111,3442DE,111111,2026/10/13,12:00:01.000,2026/10/13,12:00:01.000,,32000,,,40.4500,-3.6500,,,0,0,0,0\n"
            "MSG,4,111,11111,3442DE,111111,2026/10/13,12:00:02.000,2026/10/13,12:00:02.000,,,450,210,,,-800,,,,,,"
        )
        res = self.tool.execute(action="parse_sbs1", raw_data=sample_sbs)
        self.assertTrue(res.success)
        ac_list = res.data["aircraft"]
        self.assertEqual(len(ac_list), 1)
        ac = ac_list[0]
        self.assertEqual(ac["icao"], "3442DE")
        self.assertEqual(ac["callsign"], "IBE3842")
        self.assertEqual(ac["altitude_feet"], 32000)
        self.assertEqual(ac["lat"], 40.4500)
        self.assertEqual(ac["lon"], -3.6500)
        self.assertEqual(ac["ground_speed_knots"], 450.0)
        self.assertEqual(ac["track_deg"], 210.0)

    def test_parse_dump1090_json_and_3d_scene(self):
        """Verifica parseo de JSON dump1090 y generación de escena 3D."""
        dump_data = {
            "now": 1770000000.0,
            "aircraft": [
                {
                    "hex": "4CA812",
                    "flight": "RYR1024 ",
                    "alt_baro": 18500,
                    "gs": 380.5,
                    "track": 145.0,
                    "lat": 40.5200,
                    "lon": -3.5800,
                    "squawk": "2145"
                }
            ]
        }
        res = self.tool.execute(action="parse_dump1090_json", raw_data=json.dumps(dump_data))
        self.assertTrue(res.success)
        self.assertEqual(res.data["aircraft_count"], 1)
        scene = res.data["scene"]
        self.assertIn("elements", scene)
        self.assertTrue(any(el.get("name") == "Flight_RYR1024" for el in scene["elements"]))
        self.assertTrue(any(el.get("type") == "arrow_helper" for el in scene["elements"]))

    def test_socket_timeout_handling(self):
        """Verifica que un socket no alcanzable retorne de inmediato sin bloquear ni lanzar excepciones."""
        t0 = time.time()
        res = self.tool.execute(action="fetch_socket_stream", host="127.0.0.1", port=59999, timeout_sec=0.5)
        elapsed = time.time() - t0
        self.assertTrue(res.success)
        self.assertLess(elapsed, 2.0)
        self.assertEqual(res.data["aircraft"], [])


class TestMeshtasticGateway(unittest.TestCase):
    """Pruebas del conector LoRa Meshtastic."""

    def setUp(self):
        self.tool = MeshtasticGatewayTool()

    def test_send_text_message(self):
        """Verifica ensamblado y transmisión de paquete de texto."""
        res = self.tool.execute(
            action="send_text",
            destination="!8f2a1b0c",
            message="CMD: STATUS_CHECK",
            channel_index=1,
            interface_type="mock"
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data["status"], "transmitted")
        pkt = res.data["packet"]
        self.assertEqual(pkt["portnum"], 1)
        self.assertEqual(pkt["payload"]["text"], "CMD: STATUS_CHECK")

    def test_broadcast_telemetry(self):
        """Verifica emisión de métricas de telemetría del agente."""
        res = self.tool.execute(
            action="broadcast_telemetry",
            telemetry_data={"battery_level": 85, "agent_status": "SEARCHING"}
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data["status"], "broadcasted")
        self.assertEqual(res.data["telemetry"]["battery_level"], 85)

    def test_parse_meshtastic_packet(self):
        """Verifica decodificación de paquetes entrantes."""
        raw_pkt = {
            "from": "!node_alpha",
            "to": "!jev_core",
            "portnum": 1,
            "rx_rssi": -88,
            "payload": {"text": "/exec run_diagnostics"}
        }
        res = self.tool.execute(action="parse_packet", raw_packet=raw_pkt)
        self.assertTrue(res.success)
        decoded = res.data["data"]
        self.assertEqual(decoded["type"], "TEXT_MESSAGE")
        self.assertTrue(decoded["is_command"])


class TestFrigateVisionBridge(unittest.TestCase):
    """Pruebas del conector de visión artificial Frigate NVR."""

    def setUp(self):
        self.tool = FrigateVisionBridgeTool()

    def test_parse_mqtt_event_and_security_rule(self):
        """Verifica procesamiento de evento MQTT y evaluación de regla de intrusión."""
        mqtt_evt = {
            "type": "new",
            "after": {
                "id": "1770000100.123-abc",
                "camera": "cam_patio_trasero",
                "label": "person",
                "top_score": 0.88,
                "current_zones": ["perimetro_norte", "zona_acceso"],
                "box": [120, 200, 300, 450],
                "stationary": False
            }
        }
        res = self.tool.execute(
            action="parse_mqtt_event",
            mqtt_payload=mqtt_evt,
            label="person",
            zone="zona_acceso",
            confidence_threshold=0.75
        )
        self.assertTrue(res.success)
        self.assertTrue(res.data["trigger_agent_alert"])
        self.assertEqual(res.data["rule_evaluation"]["severity"], "CRITICAL")

    def test_api_query_offline_handling(self):
        """Verifica que la consulta REST a Frigate gestione la desconexión limpiamente."""
        res = self.tool.execute(action="query_api_events", frigate_url="http://127.0.0.1:59998")
        self.assertTrue(res.success)
        self.assertEqual(res.data["event_count"], 0)
        self.assertIn("no accesible", res.data["connection_status"].lower())


class TestOdmPhotogrammetry(unittest.TestCase):
    """Pruebas del conector OpenDroneMap (NodeODM)."""

    def setUp(self):
        self.tool = OdmPhotogrammetryTool()

    def test_inspect_dataset_and_task_spec(self):
        """Verifica inspección de dataset y construcción de opciones ODM."""
        spec_res = self.tool.execute(
            action="create_task_spec",
            task_id="survey_mision_01",
            options={"mesh-size": 80000, "dsm": True}
        )
        self.assertTrue(spec_res.success)
        self.assertEqual(spec_res.data["task_id"], "survey_mision_01")
        self.assertEqual(spec_res.data["options"]["mesh-size"], 80000)

    def test_import_mesh_to_viewport(self):
        """Verifica generación e importación de escena Three.js para el terreno 3D."""
        res = self.tool.execute(action="import_mesh_to_viewport")
        self.assertTrue(res.success)
        scene = res.data["scene"]
        self.assertIn("elements", scene)
        self.assertTrue(any(el.get("name") == "ODM_Reconstructed_Terrain" for el in scene["elements"]))


class TestOpenpilotTelemetry(unittest.TestCase):
    """Pruebas del decodificador de telemetría Comma.ai Openpilot."""

    def setUp(self):
        self.tool = OpenpilotTelemetryTool()

    def test_simulate_driving_step_and_scene(self):
        """Verifica simulación de paso de conducción y proyección 3D del vehículo y carril."""
        res = self.tool.execute(
            action="simulate_driving_step",
            speed_mps=28.0,
            steering_angle_deg=-4.0,
            curvature=0.005
        )
        self.assertTrue(res.success)
        v_state = res.data["vehicle_state"]
        self.assertEqual(v_state["v_ego_mps"], 28.0)
        self.assertAlmostEqual(v_state["v_ego_kph"], 100.8, places=1)

        scene = res.data["scene"]
        self.assertIn("elements", scene)
        self.assertTrue(any(el.get("name") == "Ego_Vehicle" for el in scene["elements"]))
        self.assertTrue(any("Lane_Marker" in el.get("name", "") for el in scene["elements"]))
        self.assertTrue(any("Path_Segment" in el.get("name", "") for el in scene["elements"]))

    def test_analyze_driving_safety_log(self):
        """Verifica análisis de estabilidad y desenganches de Openpilot."""
        sample_log = {
            "events": [
                {"carState": {"vEgo": 25.0, "steeringRateDeg": 12.0}, "controlsState": {"state": "enabled"}},
                {"carState": {"vEgo": 30.0, "steeringRateDeg": 45.0}, "controlsState": {"state": "enabled"}}
            ]
        }
        res = self.tool.execute(action="analyze_driving_log", raw_log_data=sample_log)
        self.assertTrue(res.success)
        self.assertEqual(res.data["disengagements"], 0)
        self.assertIn("NOMINAL", res.data["safety_verdict"])


class TestHardwareSkillsRegistryIntegration(unittest.TestCase):
    """Verifica que los 5 adaptadores estén registrados en SkillRegistry y DynamicToolManager."""

    def test_skills_discovered_in_registry(self):
        registry = SkillRegistry()
        skill_names = list(registry._skills.keys())

        expected_skills = [
            "skill_rf_adsb_tracker",
            "skill_meshtastic_gateway",
            "skill_frigate_vision_bridge",
            "skill_odm_photogrammetry",
            "skill_openpilot_telemetry"
        ]
        for name in expected_skills:
            self.assertIn(name, skill_names, f"Habilidad '{name}' no encontrada en el registro.")

    def test_execution_via_registry(self):
        registry = SkillRegistry()

        # 1. adsb
        res_adsb = registry.execute_skill("skill_rf_adsb_tracker", action="parse_dump1090_json", raw_data="{}")
        self.assertEqual(res_adsb.get("status"), "success")

        # 2. meshtastic
        res_mesh = registry.execute_skill("skill_meshtastic_gateway", action="check_gateway_status")
        self.assertEqual(res_mesh.get("status"), "success")

        # 3. frigate
        res_frig = registry.execute_skill("skill_frigate_vision_bridge", action="parse_mqtt_event", mqtt_payload={})
        self.assertEqual(res_frig.get("status"), "success")

        # 4. odm
        res_odm = registry.execute_skill("skill_odm_photogrammetry", action="check_node_status")
        self.assertEqual(res_odm.get("status"), "success")

        # 5. openpilot
        res_op = registry.execute_skill("skill_openpilot_telemetry", action="simulate_driving_step")
        self.assertEqual(res_op.get("status"), "success")

    def test_dynamic_tool_manager_loads_all_hardware_tools(self):
        tool_reg = ToolRegistry()
        dyn_mgr = DynamicToolManager(tool_reg)
        loaded = dyn_mgr.load_all()

        for name in [
            "skill_rf_adsb_tracker",
            "skill_meshtastic_gateway",
            "skill_frigate_vision_bridge",
            "skill_odm_photogrammetry",
            "skill_openpilot_telemetry"
        ]:
            self.assertIn(name, loaded)


if __name__ == "__main__":
    unittest.main()
