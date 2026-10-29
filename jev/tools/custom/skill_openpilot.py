"""
Decodificador y Analizador de Telemetría Openpilot / Cereal (Comma.ai) para JEV.
Soporta:
1. Decodificación de mensajes y eventos de conducción autónoma (carState, controlsState, modelV2, lateralPlan).
2. Análisis de trayectoria predicha por la red neuronal (Splines 3D de carril, curvatura y velocidad planificada).
3. Monitoreo de actuadores (ángulo de volante, par de dirección, acelerador, freno, eventos de desenganche).
4. Proyección visual de la trayectoria del vehículo y límites del carril en el 3D Viewport de Three.js.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import math
import time

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class OpenpilotTelemetryTool(BaseTool):
    """Herramienta de análisis de telemetría y modelos de conducción Comma.ai Openpilot."""
    name = "skill_openpilot_telemetry"
    description = (
        "Analiza registros de telemetría CAN y mensajes Cereal de Comma.ai Openpilot. "
        "Decodifica carState (velocidad, volante, gas/freno), modelV2 (trayectoria predicha, carriles) "
        "y genera visualizaciones del camino y vehículo en el 3D Viewport de JEV."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción: 'parse_telemetry_event', 'analyze_driving_log', 'generate_drive_3d_scene', 'simulate_driving_step'",
                "enum": ["parse_telemetry_event", "analyze_driving_log", "generate_drive_3d_scene", "simulate_driving_step"],
                "default": "simulate_driving_step"
            },
            "raw_log_data": {
                "type": "object",
                "description": "Diccionario con datos o tramas Cereal (carState, modelV2, controlsState)",
                "default": {}
            },
            "speed_mps": {
                "type": "number",
                "description": "Velocidad actual en metros por segundo (m/s) para simulación",
                "default": 25.0
            },
            "steering_angle_deg": {
                "type": "number",
                "description": "Ángulo de giro del volante en grados (°)",
                "default": -2.5
            },
            "curvature": {
                "type": "number",
                "description": "Curvatura del camino (1/radio, 0 = recto, >0 izquierda, <0 derecha)",
                "default": 0.003
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "simulate_driving_step")
        raw_log = kwargs.get("raw_log_data") or {}
        speed_mps = float(kwargs.get("speed_mps", 25.0))
        steer_deg = float(kwargs.get("steering_angle_deg", -2.5))
        curvature = float(kwargs.get("curvature", 0.003))

        try:
            if action == "parse_telemetry_event":
                parsed = self.parse_cereal_message(raw_log)
                scene = self.build_driving_scene(parsed.get("trajectory", []), parsed.get("vehicle_state", {}))
                return ToolResult(
                    success=True,
                    output=f"Trama Openpilot procesada: Vel {parsed['vehicle_state'].get('v_ego_kph', 0)} km/h, Volante {parsed['vehicle_state'].get('steering_angle_deg', 0)}°.",
                    data={"parsed": parsed, "scene": scene}
                )

            elif action == "analyze_driving_log":
                summary = self.analyze_safety_metrics(raw_log)
                return ToolResult(
                    success=True,
                    output=f"Auditoría Openpilot: {summary['total_events']} eventos evaluados. Desenganches: {summary['disengagements']}. Conducción {summary['safety_verdict']}.",
                    data=summary
                )

            elif action == "generate_drive_3d_scene":
                traj = self._generate_synthetic_trajectory(speed_mps, curvature)
                v_state = {
                    "v_ego_kph": round(speed_mps * 3.6, 1),
                    "steering_angle_deg": steer_deg,
                    "gas": 0.15,
                    "brake": 0.0,
                    "steering_torque": 0.82
                }
                scene = self.build_driving_scene(traj, v_state)
                return ToolResult(
                    success=True,
                    output="Escena 3D de conducción y trayectoria Openpilot generada para el Viewport.",
                    data={"scene": scene, "trajectory_points": len(traj), "vehicle_state": v_state}
                )

            else:
                # simulate_driving_step
                traj = self._generate_synthetic_trajectory(speed_mps, curvature)
                v_state = {
                    "v_ego_mps": speed_mps,
                    "v_ego_kph": round(speed_mps * 3.6, 1),
                    "steering_angle_deg": steer_deg,
                    "steering_rate_deg_s": 1.2,
                    "gas_pressed": True,
                    "brake_pressed": False,
                    "steering_pressed": False,
                    "standstill": False
                }
                scene = self.build_driving_scene(traj, v_state)
                return ToolResult(
                    success=True,
                    output=f"Simulación Openpilot: {v_state['v_ego_kph']} km/h | Giro {steer_deg}° | Curvatura {curvature}. Escena 3D proyectada.",
                    data={
                        "vehicle_state": v_state,
                        "trajectory_sample": traj[:5],
                        "scene": scene
                    }
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error en procesador Openpilot/Cereal: {str(e)}"
            )

    # -------------------------------------------------------------------------
    # PARSEO DE MENSAJES CEREAL (Cap'n Proto / JSON Openpilot)
    # -------------------------------------------------------------------------
    def parse_cereal_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrae datos clave de mensajes estructurados de Openpilot:
        - carState (vEgo, steeringAngleDeg, gas, brake)
        - modelV2 (position.x, position.y, position.z, orientation)
        - controlsState (enabled, alertText, disengageReasons)
        """
        cs = data.get("carState") or {}
        model = data.get("modelV2") or {}
        controls = data.get("controlsState") or {}

        v_ego = cs.get("vEgo", 0.0)
        steer_angle = cs.get("steeringAngleDeg", 0.0)
        gas = cs.get("gas", 0.0)
        brake = cs.get("brake", 0.0)
        enabled = controls.get("enabled", True)

        # Extraer puntos de trayectoria 3D de la red neuronal (modelV2.position)
        pos = model.get("position", {})
        xs = pos.get("x", [])
        ys = pos.get("y", [])
        zs = pos.get("z", [])

        trajectory = []
        if xs and ys:
            for i in range(min(len(xs), len(ys))):
                x_val = float(xs[i])
                y_val = float(ys[i])
                z_val = float(zs[i]) if i < len(zs) else 0.0
                trajectory.append({"x": x_val, "y": y_val, "z": z_val})
        else:
            trajectory = self._generate_synthetic_trajectory(v_ego or 20.0, 0.002)

        return {
            "vehicle_state": {
                "v_ego_mps": round(v_ego, 2),
                "v_ego_kph": round(v_ego * 3.6, 1),
                "steering_angle_deg": round(steer_angle, 2),
                "gas": round(gas, 2),
                "brake": round(brake, 2),
                "openpilot_enabled": enabled
            },
            "trajectory": trajectory,
            "disengage_detected": not enabled and cs.get("steeringPressed", False)
        }

    def analyze_safety_metrics(self, log_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula métricas de estabilidad y seguridad de la sesión de conducción."""
        events = log_dict.get("events") or [log_dict]
        disengagements = 0
        max_speed = 0.0
        abrupt_steer = 0

        for evt in events:
            cs = evt.get("carState", {})
            v = cs.get("vEgo", 0.0) * 3.6
            if v > max_speed: max_speed = v
            if abs(cs.get("steeringRateDeg", 0.0)) > 150.0: abrupt_steer += 1
            if evt.get("controlsState", {}).get("state") == "disabling": disengagements += 1

        is_safe = (disengagements == 0 and abrupt_steer < 2)
        return {
            "total_events": len(events),
            "max_speed_kph": round(max_speed, 1),
            "disengagements": disengagements,
            "abrupt_steering_events": abrupt_steer,
            "safety_verdict": "NOMINAL (Estable)" if is_safe else "ATENCIÓN REQUERIDA"
        }

    # -------------------------------------------------------------------------
    # GENERADOR DE TRAYECTORIA Y ESCENA THREE.JS
    # -------------------------------------------------------------------------
    def _generate_synthetic_trajectory(self, speed_mps: float, curvature: float) -> List[Dict[str, float]]:
        """Genera una trayectoria hacia adelante de 30 metros modelada por una curva parabólica."""
        points = []
        n_pts = 20
        max_dist = max(20.0, speed_mps * 1.5)  # Alcance temporal de 1.5s
        dx = max_dist / n_pts

        for i in range(n_pts):
            forward_x = i * dx
            # Desplazamiento lateral y = 0.5 * curvature * x^2
            lateral_y = 0.5 * curvature * (forward_x ** 2)
            points.append({
                "x": round(forward_x, 3),
                "y": round(lateral_y, 3),
                "z": 0.0
            })
        return points

    def build_driving_scene(
        self,
        trajectory: List[Dict[str, float]],
        vehicle_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Construye una escena Three.js con la carretera, el vehículo y los vectores de la trayectoria.
        En Three.js: X = Lateral, Y = Altura, Z = Hacia adelante (-Z hacia adelante).
        """
        elements = []

        # Carretera / Asfalto (Grid helper)
        elements.append({
            "type": "grid_helper",
            "name": "Road_Surface_Grid",
            "parameters": {"size": 30.0, "divisions": 15, "colorCenterLine": "#38bdf8", "colorGrid": "#1e293b"},
            "position": [0, -0.05, -10]
        })

        # Vehículo propio (Caja estilizada)
        steer_rad = math.radians(vehicle_state.get("steering_angle_deg", 0.0) * -0.1)
        elements.append({
            "type": "mesh",
            "name": "Ego_Vehicle",
            "geometry": {
                "type": "BoxGeometry",
                "parameters": {"width": 1.8, "height": 1.4, "depth": 4.2}
            },
            "material": {
                "type": "MeshStandardMaterial",
                "color": "#00f0ff",
                "roughness": 0.3,
                "metalness": 0.8
            },
            "position": [0, 0.7, 0],
            "rotation": [0, steer_rad, 0]
        })

        # Marcadores de carril izquierdo y derecho
        lane_width = 3.6
        for offset_x in [-lane_width / 2, lane_width / 2]:
            elements.append({
                "type": "mesh",
                "name": f"Lane_Marker_{'L' if offset_x < 0 else 'R'}",
                "geometry": {
                    "type": "BoxGeometry",
                    "parameters": {"width": 0.15, "height": 0.05, "depth": 25.0}
                },
                "material": {
                    "type": "MeshStandardMaterial",
                    "color": "#ffffff",
                    "roughness": 0.9,
                    "metalness": 0.1
                },
                "position": [offset_x, 0.02, -12]
            })

        # Proyectar trayectoria predicha mediante flechas secuenciales (ArrowHelper)
        for i in range(len(trajectory) - 1):
            p1 = trajectory[i]
            p2 = trajectory[i + 1]

            # Mapear x (adelante) a -Z, y (lateral) a X
            orig_x = p1["y"]
            orig_z = -p1["x"]
            target_x = p2["y"]
            target_z = -p2["x"]

            dir_x = target_x - orig_x
            dir_z = target_z - orig_z
            dist = math.sqrt(dir_x**2 + dir_z**2) or 1.0

            elements.append({
                "type": "arrow_helper",
                "name": f"Path_Segment_{i}",
                "direction": [dir_x / dist, 0.0, dir_z / dist],
                "origin": [round(orig_x, 3), 0.1, round(orig_z, 3)],
                "length": max(0.5, dist * 0.9),
                "color": 0x10b981 if i < 10 else 0x38bdf8,
                "headLength": 0.3,
                "headWidth": 0.2
            })

        return {
            "background": "#020617",
            "ambient_light": {"color": "#ffffff", "intensity": 0.8},
            "elements": elements
        }
