"""
Conector y Decodificador de Telemetría ADS-B / Dump1090 para JEV.
Soporta:
1. Decodificación de mensajes SBS-1 (BaseStation CSV port 30003).
2. Procesamiento de telemetría JSON de Dump1090 / Readsb (aircraft.json).
3. Conexión no bloqueante a sockets TCP ADS-B con timeout de protección.
4. Generación de trayectorias y posiciones 3D para el Viewport Three.js de JEV.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import math
import socket
import time

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class RFAdsbTrackerTool(BaseTool):
    """Herramienta de seguimiento de aeronaves y telemetría RF ADS-B."""
    name = "skill_rf_adsb_tracker"
    description = (
        "Decodifica telemetría de aviación ADS-B/Mode-S en tiempo real (SBS-1 BaseStation y Dump1090 JSON), "
        "extrae ICAO, callsign, altitud, velocidad, coordenadas y rumbo, y proyecta vectores de vuelo 3D "
        "en el Viewport Three.js de JEV."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción: 'parse_sbs1', 'parse_dump1090_json', 'fetch_socket_stream', 'generate_3d_flight_scene'",
                "enum": ["parse_sbs1", "parse_dump1090_json", "fetch_socket_stream", "generate_3d_flight_scene"],
                "default": "parse_dump1090_json"
            },
            "raw_data": {
                "type": "string",
                "description": "Texto crudo de tramas SBS-1 (separadas por salto de línea) o cadena JSON de Dump1090",
                "default": ""
            },
            "host": {
                "type": "string",
                "description": "Host del receptor Dump1090/RTL-SDR (ej. '127.0.0.1' o IP LAN)",
                "default": "127.0.0.1"
            },
            "port": {
                "type": "integer",
                "description": "Puerto TCP del stream (30003 para SBS-1 BaseStation, 30002 para RAW Beast)",
                "default": 30003
            },
            "timeout_sec": {
                "type": "number",
                "description": "Timeout en segundos para la conexión socket de red (máx 3.0s)",
                "default": 1.5
            },
            "max_lines": {
                "type": "integer",
                "description": "Límite de líneas a leer del socket antes de procesar",
                "default": 30
            },
            "reference_lat": {
                "type": "number",
                "description": "Latitud del observador / antena receptora para centrar el Viewport 3D",
                "default": 40.4168
            },
            "reference_lon": {
                "type": "number",
                "description": "Longitud del observador / antena receptora para centrar el Viewport 3D",
                "default": -3.7038
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "parse_dump1090_json")
        raw_data = kwargs.get("raw_data", "")
        host = kwargs.get("host", "127.0.0.1")
        port = int(kwargs.get("port", 30003))
        timeout_sec = min(float(kwargs.get("timeout_sec", 1.5)), 5.0)
        max_lines = int(kwargs.get("max_lines", 30))
        ref_lat = float(kwargs.get("reference_lat", 40.4168))
        ref_lon = float(kwargs.get("reference_lon", -3.7038))

        try:
            aircraft_list: List[Dict[str, Any]] = []

            if action == "parse_sbs1":
                aircraft_list = self.parse_sbs1_stream(raw_data)
            elif action == "parse_dump1090_json":
                aircraft_list = self.parse_dump1090_json(raw_data)
            elif action == "fetch_socket_stream":
                lines, conn_info = self._fetch_socket_lines(host, port, timeout_sec, max_lines)
                if lines:
                    aircraft_list = self.parse_sbs1_stream("\n".join(lines))
                else:
                    return ToolResult(
                        success=True,
                        output=f"Conexión con Dump1090 ({host}:{port}) verificada: {conn_info}. 0 tramas recibidas dentro del timeout.",
                        data={"aircraft": [], "connection": conn_info, "status": "offline_or_idle"}
                    )
            elif action == "generate_3d_flight_scene":
                # Si se proporcionan datos en raw_data, parsearlos primero
                if raw_data.strip().startswith("{"):
                    aircraft_list = self.parse_dump1090_json(raw_data)
                elif raw_data.strip().startswith("MSG"):
                    aircraft_list = self.parse_sbs1_stream(raw_data)

            # Generar escena 3D Three.js
            scene_3d = self.build_threejs_flight_scene(aircraft_list, ref_lat, ref_lon)

            # Guardar telemetría de sesión en workspace
            telemetry_path = self.workspace_dir / "telemetry" / "adsb_latest.json"
            telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            telemetry_payload = {
                "timestamp": time.time(),
                "aircraft_count": len(aircraft_list),
                "aircraft": aircraft_list,
                "reference_origin": {"lat": ref_lat, "lon": ref_lon}
            }
            telemetry_path.write_text(json.dumps(telemetry_payload, indent=2), encoding="utf-8")

            return ToolResult(
                success=True,
                output=(
                    f"Telemetría ADS-B procesada: {len(aircraft_list)} aeronaves activas identificadas. "
                    f"Escena 3D generada con {len(scene_3d.get('elements', []))} elementos para el Viewport."
                ),
                data={
                    "aircraft_count": len(aircraft_list),
                    "aircraft": aircraft_list,
                    "scene": scene_3d,
                    "persisted_file": str(telemetry_path)
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error en procesador ADS-B: {str(e)}"
            )

    # -------------------------------------------------------------------------
    # PARSERS DE PROTOCOLO ADS-B
    # -------------------------------------------------------------------------
    def parse_sbs1_stream(self, text: str) -> List[Dict[str, Any]]:
        """
        Parsea tramas SBS-1 (BaseStation CSV format port 30003).
        Campos típicos SBS-1:
        MSG, transmission_type, session_id, aircraft_id, hex_ident, flight_id,
        date_gen, time_gen, date_log, time_log, callsign, altitude, ground_speed,
        track, lat, lon, vertical_rate, squawk, alert, emergency, spi, is_on_ground
        """
        aircraft_map: Dict[str, Dict[str, Any]] = {}

        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 11:
                continue
            if parts[0] != "MSG":
                continue

            msg_type = parts[1]
            icao = parts[4].upper()
            if not icao:
                continue

            if icao not in aircraft_map:
                aircraft_map[icao] = {
                    "icao": icao,
                    "callsign": None,
                    "altitude_feet": None,
                    "ground_speed_knots": None,
                    "track_deg": None,
                    "lat": None,
                    "lon": None,
                    "vertical_rate_fpm": None,
                    "squawk": None,
                    "last_seen": time.time()
                }

            ac = aircraft_map[icao]

            # MSG 1: Identificación y llamada
            if msg_type == "1" and len(parts) > 10 and parts[10]:
                ac["callsign"] = parts[10]

            # MSG 3: Posición en vuelo
            if msg_type == "3" and len(parts) > 15:
                if parts[11]:
                    try: ac["altitude_feet"] = int(parts[11])
                    except ValueError: pass
                if parts[14] and parts[15]:
                    try:
                        ac["lat"] = float(parts[14])
                        ac["lon"] = float(parts[15])
                    except ValueError: pass

            # MSG 4: Vector de velocidad
            if msg_type == "4" and len(parts) > 16:
                if parts[12]:
                    try: ac["ground_speed_knots"] = float(parts[12])
                    except ValueError: pass
                if parts[13]:
                    try: ac["track_deg"] = float(parts[13])
                    except ValueError: pass
                if parts[16]:
                    try: ac["vertical_rate_fpm"] = float(parts[16])
                    except ValueError: pass

            # Squawk presente en MSG 6
            if len(parts) > 17 and parts[17]:
                ac["squawk"] = parts[17]

        return list(aircraft_map.values())

    def parse_dump1090_json(self, json_str: str) -> List[Dict[str, Any]]:
        """Parsea la salida JSON de dump1090/readsb (aircraft.json)."""
        if not json_str.strip():
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return []

        raw_list = data.get("aircraft", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        parsed = []

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            icao = (item.get("hex") or item.get("icao") or "").upper()
            if not icao:
                continue

            callsign = (item.get("flight") or item.get("callsign") or "").strip() or None
            alt = item.get("altitude") or item.get("alt_baro") or item.get("alt_geom")
            speed = item.get("speed") or item.get("gs")
            track = item.get("track")
            lat = item.get("lat")
            lon = item.get("lon")
            vr = item.get("vert_rate") or item.get("baro_rate")
            squawk = item.get("squawk")

            parsed.append({
                "icao": icao,
                "callsign": callsign,
                "altitude_feet": int(alt) if alt is not None and str(alt).isdigit() else None,
                "ground_speed_knots": float(speed) if speed is not None else None,
                "track_deg": float(track) if track is not None else None,
                "lat": float(lat) if lat is not None else None,
                "lon": float(lon) if lon is not None else None,
                "vertical_rate_fpm": float(vr) if vr is not None else None,
                "squawk": str(squawk) if squawk is not None else None,
                "rssi": item.get("rssi")
            })

        return parsed

    # -------------------------------------------------------------------------
    # CONEXIÓN NO BLOQUEANTE A SOCKETS TCP
    # -------------------------------------------------------------------------
    def _fetch_socket_lines(
        self,
        host: str,
        port: int,
        timeout_sec: float,
        max_lines: int
    ) -> Tuple[List[str], str]:
        """Realiza una lectura segura y acotada desde un socket TCP ADS-B."""
        lines = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)

        try:
            sock.connect((host, port))
            buffer = ""
            start_time = time.time()

            while len(lines) < max_lines and (time.time() - start_time) < timeout_sec:
                try:
                    chunk = sock.recv(2048).decode("ascii", errors="ignore")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        clean_line = line.strip()
                        if clean_line:
                            lines.append(clean_line)
                            if len(lines) >= max_lines:
                                break
                except socket.timeout:
                    break
            conn_status = f"Conectado exitosamente ({len(lines)} líneas leídas)"
        except (socket.error, ConnectionRefusedError, OSError) as e:
            conn_status = f"Receptor no alcanzable en {host}:{port} ({e.__class__.__name__})"
        finally:
            try: sock.close()
            except Exception: pass

        return lines, conn_status

    # -------------------------------------------------------------------------
    # PROYECCIÓN Y VISUALIZACIÓN EN 3D VIEWPORT
    # -------------------------------------------------------------------------
    def build_threejs_flight_scene(
        self,
        aircraft_list: List[Dict[str, Any]],
        ref_lat: float,
        ref_lon: float
    ) -> Dict[str, Any]:
        """
        Proyecta posiciones y vectores de velocidad ADS-B en coordenadas métricas
        locales de Three.js (X = Este, Z = Sur/Norte, Y = Altitud escalada).
        """
        elements = []

        # Rejilla base de radar aeronáutico
        elements.append({
            "type": "grid_helper",
            "name": "Radar_Horizon_Grid",
            "parameters": {
                "size": 40.0,
                "divisions": 20,
                "colorCenterLine": "#00f0ff",
                "colorGrid": "#111827"
            },
            "position": [0, 0, 0]
        })

        # Marcador de estación receptora local
        elements.append({
            "type": "mesh",
            "name": "Local_Ground_Station",
            "geometry": {
                "type": "CylinderGeometry",
                "parameters": {"radiusTop": 0.2, "radiusBottom": 0.4, "height": 0.6, "radialSegments": 16}
            },
            "material": {
                "type": "MeshStandardMaterial",
                "color": "#10b981",
                "metalness": 0.9,
                "roughness": 0.2
            },
            "position": [0, 0.3, 0]
        })

        # Escalar coordenadas geográficas a espacio de visualización local (km aproximados)
        # 1 grado de latitud ~ 111 km
        # 1 grado de longitud ~ 111 km * cos(lat)
        cos_lat = math.cos(math.radians(ref_lat)) or 1.0
        km_to_units = 0.5  # 1 km = 0.5 unidades Three.js
        alt_scale = 0.0003  # 10,000 ft ~ 3 unidades de altura

        for ac in aircraft_list:
            lat = ac.get("lat")
            lon = ac.get("lon")
            alt = ac.get("altitude_feet") or 5000
            icao = ac.get("icao", "UNKNOWN")
            callsign = ac.get("callsign") or icao
            track = ac.get("track_deg") or 0.0

            if lat is None or lon is None:
                # Si no tiene coordenadas geográficas, omitir de la proyección 3D
                continue

            dx_km = (lon - ref_lon) * 111.32 * cos_lat
            dz_km = -(lat - ref_lat) * 110.57  # Invertir para orientar Norte a -Z
            pos_x = dx_km * km_to_units
            pos_y = max(0.5, alt * alt_scale)
            pos_z = dz_km * km_to_units

            # Malla representativa del avión (Cono fuselaje)
            elements.append({
                "type": "mesh",
                "name": f"Flight_{callsign}",
                "geometry": {
                    "type": "CylinderGeometry",
                    "parameters": {"radiusTop": 0.05, "radiusBottom": 0.35, "height": 1.2, "radialSegments": 12}
                },
                "material": {
                    "type": "MeshStandardMaterial",
                    "color": "#00f0ff",
                    "roughness": 0.3,
                    "metalness": 0.7
                },
                "position": [round(pos_x, 3), round(pos_y, 3), round(pos_z, 3)]
            })

            # Vector de dirección de vuelo (ArrowHelper orientado por track)
            rad_track = math.radians(track)
            dir_x = math.sin(rad_track)
            dir_z = -math.cos(rad_track)
            elements.append({
                "type": "arrow_helper",
                "name": f"Vector_{icao}",
                "direction": [round(dir_x, 3), 0.0, round(dir_z, 3)],
                "origin": [round(pos_x, 3), round(pos_y, 3), round(pos_z, 3)],
                "length": 1.8,
                "color": 0x00f0ff,
                "headLength": 0.5,
                "headWidth": 0.35
            })

        return {
            "background": "#02040a",
            "ambient_light": {"color": "#ffffff", "intensity": 0.8},
            "elements": elements
        }
