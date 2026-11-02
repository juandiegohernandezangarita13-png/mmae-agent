"""
Herramienta de Control de Hardware Externo, Sensores y Dispositivos IoT para JEV.
Permite al agente interactuar con:
  - Puertos Seriales / USB (Arduino, ESP32, STM32, Impresoras 3D con G-Code, Máquinas CNC)
  - Redes de Domótica e Internet de las Cosas (MQTT / Mosquitto / Home Assistant)
  - Dispositivos IoT por HTTP/REST (Shelly, Tasmota, ESPHome, WLED)
"""
from __future__ import annotations

import os
import sys
import time
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class HardwareControllerTool(BaseTool):
    """Controlador de hardware físico (USB Serial, Arduino, ESP32, G-Code) y Domótica IoT (MQTT/HTTP)."""
    name = "hardware_controller"
    description = (
        "Interactúa con hardware físico conectado por USB/COM (Arduino, ESP32, CNC, impresoras 3D) "
        "y dispositivos IoT / Domótica (MQTT, Home Assistant, Tasmota). "
        "Permite listar puertos COM, enviar comandos G-Code o texto serie, y publicar mensajes MQTT."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_ports", "serial_send", "serial_read", "mqtt_publish", "iot_http"],
                "description": "Acción a realizar: 'list_ports', 'serial_send', 'serial_read', 'mqtt_publish', 'iot_http'."
            },
            "port": {
                "type": "string",
                "description": "Puerto serie COM (ej: 'COM3', 'COM4') requerido para acciones serial."
            },
            "baudrate": {
                "type": "integer",
                "description": "Velocidad de baudios (defecto 115200, otros comunes: 9600, 57600, 250000).",
                "default": 115200
            },
            "command": {
                "type": "string",
                "description": "Comando o datos a enviar al puerto serie (ej: 'G28' para home en 3D/CNC, 'STATUS', 'LED_ON\\n')."
            },
            "timeout": {
                "type": "number",
                "description": "Tiempo de espera en segundos para la respuesta serie (defecto 2.0s).",
                "default": 2.0
            },
            "mqtt_broker": {
                "type": "string",
                "description": "Dirección IP o host del broker MQTT (ej: '192.168.1.50', 'localhost').",
                "default": "localhost"
            },
            "mqtt_port": {
                "type": "integer",
                "description": "Puerto del broker MQTT (defecto 1883).",
                "default": 1883
            },
            "mqtt_topic": {
                "type": "string",
                "description": "Tópico MQTT donde publicar (ej: 'cmnd/tasmota/POWER', 'homeassistant/light/toggle')."
            },
            "mqtt_payload": {
                "type": "string",
                "description": "Mensaje o carga útil a publicar en MQTT."
            },
            "url": {
                "type": "string",
                "description": "URL del dispositivo IoT para petición HTTP (ej: 'http://192.168.1.100/cm?cmnd=Power%20TOGGLE')."
            },
            "http_method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "default": "GET",
                "description": "Método HTTP para iot_http ('GET' o 'POST')."
            }
        },
        "required": ["action"]
    }

    def execute(
        self,
        action: str,
        port: Optional[str] = None,
        baudrate: int = 115200,
        command: Optional[str] = None,
        timeout: float = 2.0,
        mqtt_broker: str = "localhost",
        mqtt_port: int = 1883,
        mqtt_topic: Optional[str] = None,
        mqtt_payload: Optional[str] = None,
        url: Optional[str] = None,
        http_method: str = "GET",
        **kwargs
    ) -> ToolResult:
        action = (action or "").strip().lower()

        # -------------------------------------------------------------
        # 1. Listar puertos seriales disponibles
        # -------------------------------------------------------------
        if action == "list_ports":
            try:
                import serial.tools.list_ports
                ports = serial.tools.list_ports.comports()
                if not ports:
                    return ToolResult(
                        success=True,
                        output="🔌 No se detectaron puertos COM o dispositivos USB seriales conectados actualmente.",
                        data={"ports": []}
                    )
                
                port_list = []
                lines = ["🔌 Dispositivos de Hardware / Puertos COM Detectados:"]
                for p in ports:
                    desc = f"• {p.device}: {p.description} [HWID: {p.hwid}]"
                    lines.append(desc)
                    port_list.append({
                        "device": p.device,
                        "description": p.description,
                        "hwid": p.hwid,
                        "manufacturer": getattr(p, "manufacturer", "Desconocido")
                    })
                return ToolResult(
                    success=True,
                    output="\n".join(lines),
                    data={"ports": port_list}
                )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error enumerando puertos COM: {e}")

        # -------------------------------------------------------------
        # 2. Enviar comando serie (Arduino, ESP32, CNC, 3D Printer)
        # -------------------------------------------------------------
        elif action == "serial_send":
            if not port:
                return ToolResult(success=False, output="", error="Debes especificar 'port' (ej: 'COM3').")
            if command is None:
                return ToolResult(success=False, output="", error="Debes especificar 'command' para enviar por serial.")

            try:
                import serial
                with serial.Serial(port, baudrate=baudrate, timeout=timeout) as ser:
                    time.sleep(0.1)
                    # Asegurar terminación de línea
                    cmd_bytes = command.encode("utf-8")
                    if not cmd_bytes.endswith(b"\n"):
                        cmd_bytes += b"\n"
                    
                    ser.write(cmd_bytes)
                    ser.flush()
                    time.sleep(0.2)

                    # Leer respuesta si hay disponible
                    received = []
                    start_time = time.time()
                    while time.time() - start_time < timeout:
                        line = ser.readline()
                        if line:
                            received.append(line.decode("utf-8", errors="replace").strip())
                        else:
                            break

                    resp_text = "\n".join(received) if received else "(Sin respuesta del dispositivo)"
                    return ToolResult(
                        success=True,
                        output=f"✓ Comando enviado a {port} ({baudrate} bps):\n> {command.strip()}\nRespuesta recibida:\n{resp_text}",
                        data={"port": port, "sent": command, "response": resp_text}
                    )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error en comunicación serie con {port}: {e}")

        # -------------------------------------------------------------
        # 3. Leer datos del puerto serie
        # -------------------------------------------------------------
        elif action == "serial_read":
            if not port:
                return ToolResult(success=False, output="", error="Debes especificar 'port' (ej: 'COM3').")
            try:
                import serial
                with serial.Serial(port, baudrate=baudrate, timeout=timeout) as ser:
                    lines = []
                    start = time.time()
                    while time.time() - start < timeout:
                        line = ser.readline()
                        if line:
                            lines.append(line.decode("utf-8", errors="replace").strip())
                        else:
                            break
                    res_str = "\n".join(lines) if lines else "(Buffer vacío o sin datos transmitidos)"
                    return ToolResult(
                        success=True,
                        output=f"📡 Datos leídos de {port} ({baudrate} bps):\n{res_str}",
                        data={"port": port, "lines": lines}
                    )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error leyendo puerto serie {port}: {e}")

        # -------------------------------------------------------------
        # 4. Publicar en MQTT (Home Assistant, Tasmota, ESPHome)
        # -------------------------------------------------------------
        elif action == "mqtt_publish":
            if not mqtt_topic or mqtt_payload is None:
                return ToolResult(success=False, output="", error="Se requiere 'mqtt_topic' y 'mqtt_payload'.")
            try:
                import paho.mqtt.publish as publish
                publish.single(
                    topic=mqtt_topic,
                    payload=mqtt_payload,
                    hostname=mqtt_broker,
                    port=mqtt_port,
                    timeout=5
                )
                return ToolResult(
                    success=True,
                    output=f"✓ Mensaje MQTT publicado con éxito en {mqtt_broker}:{mqtt_port} -> Tópico '{mqtt_topic}'.",
                    data={"broker": mqtt_broker, "port": mqtt_port, "topic": mqtt_topic, "payload": mqtt_payload}
                )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error publicando en MQTT: {e}")

        # -------------------------------------------------------------
        # 5. Petición HTTP a Dispositivo IoT (REST Webhook)
        # -------------------------------------------------------------
        elif action == "iot_http":
            if not url:
                return ToolResult(success=False, output="", error="Se requiere 'url' para iot_http.")
            try:
                import httpx
                with httpx.Client(timeout=10.0) as client:
                    if http_method.upper() == "POST":
                        resp = client.post(url)
                    else:
                        resp = client.get(url)
                    return ToolResult(
                        success=True,
                        output=f"✓ Petición IoT enviada a {url} (Código {resp.status_code}):\n{resp.text[:500]}",
                        data={"url": url, "status_code": resp.status_code, "body": resp.text[:1000]}
                    )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error en petición HTTP IoT: {e}")

        return ToolResult(success=False, output="", error=f"Acción '{action}' desconocida para hardware_controller.")
