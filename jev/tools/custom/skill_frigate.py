"""
Puente y Conector de Visión Artificial Frigate NVR para JEV.
Soporta:
1. Procesamiento y decodificación de eventos MQTT de Frigate NVR (topic frigate/events).
2. Consulta de API REST (/api/events, /api/stats) con timeouts estrictos para no bloquear.
3. Evaluación de reglas de seguridad, intrusión y zonas perimetrales en tiempo real.
4. Generación de alertas para el bucle cognitivo del agente JEV ante presencia de personas/vehículos.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import time
import urllib.request
import urllib.error

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class FrigateVisionBridgeTool(BaseTool):
    """Herramienta de integración con el sistema de visión artificial y NVR Frigate."""
    name = "skill_frigate_vision_bridge"
    description = (
        "Conector para el NVR de visión artificial local Frigate. Consume alertas MQTT y REST, "
        "rastrea detecciones de personas, vehículos y objetos por zonas perimetrales, evalúa reglas "
        "de intrusión y dispara eventos en el bucle cognitivo de JEV."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción: 'parse_mqtt_event', 'query_api_events', 'evaluate_security_rule', 'get_snapshot_info'",
                "enum": ["parse_mqtt_event", "query_api_events", "evaluate_security_rule", "get_snapshot_info"],
                "default": "parse_mqtt_event"
            },
            "mqtt_payload": {
                "type": "object",
                "description": "Objeto o diccionario del evento MQTT 'frigate/events'",
                "default": {}
            },
            "frigate_url": {
                "type": "string",
                "description": "URL base del servidor Frigate NVR (ej. 'http://localhost:5000')",
                "default": "http://127.0.0.1:5000"
            },
            "camera": {
                "type": "string",
                "description": "Nombre de la cámara a filtrar (ej. 'cam_frontal', 'cam_patio')",
                "default": ""
            },
            "label": {
                "type": "string",
                "description": "Objeto detectado a filtrar ('person', 'car', 'dog', 'cat', 'bicycle')",
                "default": "person"
            },
            "zone": {
                "type": "string",
                "description": "Nombre de la zona de seguridad monitoreada (ej. 'zona_acceso', 'perimetro_norte')",
                "default": ""
            },
            "confidence_threshold": {
                "type": "number",
                "description": "Umbral mínimo de confianza para disparar la alerta (0.0 a 1.0)",
                "default": 0.70
            },
            "limit": {
                "type": "integer",
                "description": "Cantidad máxima de eventos a recuperar en consultas API",
                "default": 10
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "parse_mqtt_event")
        mqtt_payload = kwargs.get("mqtt_payload") or {}
        frigate_url = kwargs.get("frigate_url", "http://127.0.0.1:5000").rstrip("/")
        camera = kwargs.get("camera", "")
        label = kwargs.get("label", "person")
        zone = kwargs.get("zone", "")
        conf_thresh = float(kwargs.get("confidence_threshold", 0.70))
        limit = int(kwargs.get("limit", 10))

        try:
            if action == "parse_mqtt_event":
                parsed = self.parse_mqtt_event(mqtt_payload)
                rule_eval = self.evaluate_rule(parsed, target_label=label, target_zone=zone, min_conf=conf_thresh)
                res_data = {
                    "event": parsed,
                    "rule_evaluation": rule_eval,
                    "trigger_agent_alert": rule_eval["alert_triggered"]
                }
                msg = f"Evento MQTT Frigate procesado: {parsed['label']} en {parsed['camera']} (Alerta: {rule_eval['alert_triggered']})"

            elif action == "evaluate_security_rule":
                parsed = self.parse_mqtt_event(mqtt_payload)
                rule_eval = self.evaluate_rule(parsed, target_label=label, target_zone=zone, min_conf=conf_thresh)
                res_data = {
                    "rule_result": rule_eval,
                    "camera": parsed.get("camera"),
                    "label": parsed.get("label")
                }
                msg = f"Regla evaluada: {'DISPARADA' if rule_eval['alert_triggered'] else 'NORMAL'} ({rule_eval['reason']})"

            elif action == "query_api_events":
                events, status = self._query_frigate_api_events(frigate_url, camera, label, zone, limit)
                res_data = {
                    "frigate_url": frigate_url,
                    "connection_status": status,
                    "event_count": len(events),
                    "events": events
                }
                msg = f"Consulta Frigate API ({status}): {len(events)} eventos encontrados."

            else:
                # get_snapshot_info
                event_id = mqtt_payload.get("id") or mqtt_payload.get("after", {}).get("id", "sample_event_123")
                snapshot_url = f"{frigate_url}/api/events/{event_id}/snapshot.jpg"
                clip_url = f"{frigate_url}/api/events/{event_id}/clip.mp4"
                res_data = {
                    "event_id": event_id,
                    "snapshot_url": snapshot_url,
                    "clip_url": clip_url
                }
                msg = f"Enlaces multimedia para evento Frigate {event_id} construidos."

            return ToolResult(
                success=True,
                output=msg,
                data=res_data
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error en puente Frigate NVR: {str(e)}"
            )

    # -------------------------------------------------------------------------
    # PARSEO DE EVENTOS MQTT Y REGLAS DE SEGURIDAD
    # -------------------------------------------------------------------------
    def parse_mqtt_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decodifica la estructura de evento enviada por Frigate en 'frigate/events'.
        Campos típicos de Frigate:
        - type: 'new', 'update', 'end'
        - before / after: { id, camera, label, top_score, score, current_zones, entered_zones, box, stationary }
        """
        if not payload:
            return {
                "id": "unknown",
                "type": "empty",
                "camera": "unknown",
                "label": "unknown",
                "confidence": 0.0,
                "zones": [],
                "stationary": False,
                "box": []
            }

        event_type = payload.get("type", "update")
        data = payload.get("after") or payload.get("before") or payload

        event_id = data.get("id", "evt_unknown")
        camera = data.get("camera", "default_cam")
        label = data.get("label", "unknown")
        confidence = float(data.get("top_score") or data.get("score") or 0.0)
        zones = data.get("current_zones") or data.get("entered_zones") or []
        stationary = bool(data.get("stationary", False))
        box = data.get("box") or []

        return {
            "id": event_id,
            "type": event_type,
            "camera": camera,
            "label": label,
            "confidence": round(confidence, 3),
            "zones": zones,
            "stationary": stationary,
            "box": box,
            "timestamp": time.time()
        }

    def evaluate_rule(
        self,
        event: Dict[str, Any],
        target_label: str = "person",
        target_zone: str = "",
        min_conf: float = 0.70
    ) -> Dict[str, Any]:
        """Evalúa si un evento califica como anomalía o intrusión para alertar a JEV."""
        label_match = (event.get("label") == target_label) if target_label else True
        conf_match = event.get("confidence", 0.0) >= min_conf
        
        zone_match = True
        if target_zone:
            current_zones = event.get("zones", [])
            zone_match = target_zone in current_zones

        alert = label_match and conf_match and zone_match
        reason = []
        if label_match: reason.append(f"Etiqueta '{event.get('label')}' coincide")
        if conf_match: reason.append(f"Confianza {event.get('confidence')} >= {min_conf}")
        if target_zone:
            if zone_match: reason.append(f"Zona '{target_zone}' detectada")
            else: reason.append(f"Zona '{target_zone}' no coincide (detectadas: {event.get('zones')})")

        return {
            "alert_triggered": alert,
            "severity": "CRITICAL" if (alert and event.get("label") == "person") else "INFO",
            "reason": "; ".join(reason),
            "suggested_action": "Notificar a usuario y enfocar cámara" if alert else "Registrar en log silencioso"
        }

    # -------------------------------------------------------------------------
    # CLIENTE REST CON TIMEOUT SEGURO
    # -------------------------------------------------------------------------
    def _query_frigate_api_events(
        self,
        base_url: str,
        camera: str,
        label: str,
        zone: str,
        limit: int
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Consulta la API de eventos de Frigate con timeout de 2.0s sin bloquear."""
        url = f"{base_url}/api/events?limit={limit}"
        if camera: url += f"&camera={camera}"
        if label: url += f"&label={label}"
        if zone: url += f"&zone={zone}"

        req = urllib.request.Request(url, headers={"User-Agent": "JEV-Vision-Bridge/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=2.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return data if isinstance(data, list) else [], "Conectado (200 OK)"
                return [], f"Respuesta no esperada: HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return [], f"Servidor Frigate no accesible en {base_url} ({e.__class__.__name__})"
