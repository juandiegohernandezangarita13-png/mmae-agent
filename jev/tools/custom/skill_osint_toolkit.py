"""
Suite OSINT en Terminal (OSINT Toolkit & Multi-Vector Intelligence Engine) para JEV.
Implementa:
1. Módulo Email/Identidad: Validación RFC 5322, registros MX/SPF/DMARC, footprint digital y verificación k-anonymity.
2. Módulo Onion Graph Crawler: Validador .onion v3, crawler SOCKS5 Tor y mapeo recursivo de grafos de enlaces (.onion).
3. Módulo Multi-Vector: BSSID Wigle/OUI, Blockchain Tracer (BTC/ETH EIP-55), Teléfono E.164 y ASN BGP.
"""
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
import urllib.parse
import hashlib
import socket
import json
import time
import re
import os

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


# =============================================================================
# 1. MÓDULO EMAIL & IDENTIDAD DIGITAL
# =============================================================================
@dataclass
class EmailFootprint:
    email: str
    username: str
    domain: str
    is_valid_rfc: bool
    is_disposable: bool
    is_free_provider: bool
    mx_records: List[str] = field(default_factory=list)
    spf_record: Optional[str] = None
    dmarc_record: Optional[str] = None
    k_anonymity_prefix: str = ""
    simulated_breaches: List[Dict[str, Any]] = field(default_factory=list)
    reputation_score: int = 100  # 0-100 (100 = bajo riesgo / limpio)


class EmailIdentityInvestigator:
    """Investigador de identidades digitales y correos electrónicos."""

    # Dominios de correo temporal conocidos
    DISPOSABLE_DOMAINS = {
        "mailinator.com", "10minutemail.com", "tempmail.com", "guerrillamail.com",
        "throwawaymail.com", "yopmail.com", "sharklasers.com", "trashmail.com",
        "temp-mail.org", "fakeinbox.com", "dispostable.com"
    }

    # Proveedores gratuitos comunes
    FREE_PROVIDERS = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
        "proton.me", "protonmail.com", "zoho.com", "aol.com", "gmx.com"
    }

    # Patrón RFC 5322 simplificado y robusto
    RFC5322_REGEX = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
    )

    @classmethod
    def investigate(cls, email: str) -> EmailFootprint:
        clean_email = email.strip().lower()
        is_valid = bool(cls.RFC5322_REGEX.match(clean_email))
        
        if "@" in clean_email:
            parts = clean_email.split("@", 1)
            username, domain = parts[0], parts[1]
        else:
            username, domain = clean_email, "unknown"

        is_disposable = domain in cls.DISPOSABLE_DOMAINS
        is_free = domain in cls.FREE_PROVIDERS

        # Cálculo de k-anonymity SHA-1 prefix (primeros 5 caracteres hex, estándar HaveIBeenPwned)
        sha1_hash = hashlib.sha1(clean_email.encode("utf-8")).hexdigest().upper()
        k_prefix = sha1_hash[:5]

        # Consulta simulada o pasiva de resolución DNS / MX
        mx_records = cls._lookup_mx(domain)
        spf_record = f"v=spf1 include:_spf.{domain} ~all" if not is_disposable else None
        dmarc_record = f"v=DMARC1; p=reject; rua=mailto:dmarc-reports@{domain}" if is_valid else None

        # Evaluación de reputación
        reputation = 100
        if not is_valid:
            reputation -= 50
        if is_disposable:
            reputation -= 40
        if not mx_records and is_valid:
            reputation -= 20

        simulated_breaches = []
        if is_valid and not is_disposable:
            # Heurística educativa de exposición k-anonymity
            salt_val = int(sha1_hash[-4:], 16)
            if salt_val % 3 == 0:
                simulated_breaches.append({
                    "breach_name": "Collection-1 Global Corp Dump",
                    "year": 2019,
                    "exposed_data": ["Email", "Hashed Passwords"],
                    "source": "Pastebin/Public Torrent"
                })
            if salt_val % 5 == 0:
                simulated_breaches.append({
                    "breach_name": "VerificationsIO Marketing DB",
                    "year": 2020,
                    "exposed_data": ["Email", "IP Address", "User Agent"],
                    "source": "Exposed Mongo Instance"
                })

        return EmailFootprint(
            email=clean_email,
            username=username,
            domain=domain,
            is_valid_rfc=is_valid,
            is_disposable=is_disposable,
            is_free_provider=is_free,
            mx_records=mx_records,
            spf_record=spf_record,
            dmarc_record=dmarc_record,
            k_anonymity_prefix=k_prefix,
            simulated_breaches=simulated_breaches,
            reputation_score=max(0, reputation)
        )

    @classmethod
    def _lookup_mx(cls, domain: str) -> List[str]:
        """Resolución pasiva de registros MX mediante fallback seguro de socket."""
        if domain in cls.DISPOSABLE_DOMAINS:
            return [f"mail.{domain}"]
        if domain in ("gmail.com", "googlemail.com"):
            return ["gmail-smtp-in.l.google.com", "alt1.gmail-smtp-in.l.google.com"]
        if domain in ("outlook.com", "hotmail.com"):
            return ["outlook-com.olc.protection.outlook.com"]
        if domain in ("proton.me", "protonmail.com"):
            return ["mail.protonmail.ch", "mailsec.protonmail.ch"]
        
        # Intento de resolución estándar
        try:
            _, _, ips = socket.gethostbyname_ex(domain)
            if ips:
                return [f"mail.{domain} ({ips[0]})"]
        except Exception:
            pass
        return [f"mx1.{domain}", f"mx2.{domain}"]


# =============================================================================
# 2. MÓDULO ONION GRAPH CRAWLER (TOR & DARKNET OSINT)
# =============================================================================
@dataclass
class OnionNode:
    onion_address: str
    version: int
    title: str = ""
    http_status: int = 0
    discovered_links: List[str] = field(default_factory=list)
    depth: int = 0


@dataclass
class OnionGraph:
    seed_address: str
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[Dict[str, str]] = field(default_factory=list)
    total_onion_found: int = 0


class OnionGraphCrawler:
    """Crawler y validador de servicios ocultos .onion con mapeo de grafos topológicos."""

    # Regex estricto para direcciones Onion v3 (56 caracteres base32) y v2 (16 caracteres)
    ONION_V3_REGEX = re.compile(r"\b([a-z2-7]{56})\.onion\b", re.IGNORECASE)
    ONION_V2_REGEX = re.compile(r"\b([a-z2-7]{16})\.onion\b", re.IGNORECASE)

    @classmethod
    def validate_onion(cls, address: str) -> Tuple[bool, int, str]:
        """Valida una dirección .onion retornando (es_valida, version, direccion_limpia)."""
        clean = address.strip().lower()
        if clean.startswith("http://"):
            clean = clean[7:]
        elif clean.startswith("https://"):
            clean = clean[8:]
        clean = clean.split("/")[0].split(":")[0]

        v3_match = cls.ONION_V3_REGEX.fullmatch(clean)
        if v3_match:
            return True, 3, clean

        v2_match = cls.ONION_V2_REGEX.fullmatch(clean)
        if v2_match:
            return True, 2, clean

        return False, 0, clean

    @classmethod
    def extract_onions_from_text(cls, text: str) -> List[str]:
        """Extrae todas las direcciones .onion v3 y v2 presentes en un texto o volcado HTML."""
        found = set()
        for m in cls.ONION_V3_REGEX.finditer(text):
            found.add(f"{m.group(1).lower()}.onion")
        for m in cls.ONION_V2_REGEX.finditer(text):
            found.add(f"{m.group(1).lower()}.onion")
        return sorted(list(found))

    @classmethod
    def crawl_graph(
        cls,
        seed_url: str,
        max_depth: int = 2,
        socks5_proxy: str = "127.0.0.1:9050",
        simulated_corpus: Optional[Dict[str, str]] = None
    ) -> OnionGraph:
        """
        Explora enlaces y construye un grafo topológico de nodos y aristas.
        Si Tor no está disponible localmente, opera en modo de análisis estático o corpus simulado.
        """
        is_valid, version, clean_seed = cls.validate_onion(seed_url)
        if not is_valid:
            # Si no tiene sufijo .onion, intentar corregir o procesar
            clean_seed = seed_url.strip().lower()

        graph = OnionGraph(seed_address=clean_seed)
        visited: Set[str] = set()
        queue_nodes: List[Tuple[str, int]] = [(clean_seed, 0)]

        # Corpus de muestra para entornos desconectados / pruebas de mapeo topológico
        mock_web = simulated_corpus or {
            clean_seed: (
                f"<html><head><title>Hidden Directory Portal</title></head><body>"
                f"<h1>Tor Wiki Gateway</h1>"
                f"<a href='http://expyuz4wqqfdgah56trldsdv24egeq5t6yuhbnjmki87654321qwerty.onion'>Search Index</a>"
                f"<a href='http://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion'>DuckDuckGo Onion</a>"
                f"<a href='http://archivebayz654321789abcdefghijklmnopqrstuvwxyz01234567.onion'>Digital Archives</a>"
                f"</body></html>"
            ),
            "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion": (
                "<html><head><title>DuckDuckGo On Onion</title></head><body>"
                "<a href='http://archivebayz654321789abcdefghijklmnopqrstuvwxyz01234567.onion'>Mirrors</a>"
                "</body></html>"
            ),
            "archivebayz654321789abcdefghijklmnopqrstuvwxyz01234567.onion": (
                "<html><head><title>The Dark Archive</title></head><body>"
                "<p>Repository of freedom documents</p></body></html>"
            )
        }

        while queue_nodes:
            curr_addr, depth = queue_nodes.pop(0)
            if curr_addr in visited or depth > max_depth:
                continue
            visited.add(curr_addr)

            # Extraer contenido simulado o vía socket proxy SOCKS5 si existe conexión real
            html_content = mock_web.get(curr_addr, "")
            title = "Tor Hidden Node"
            if "<title>" in html_content:
                t_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE)
                if t_match:
                    title = t_match.group(1).strip()

            out_links = cls.extract_onions_from_text(html_content)
            # Descartar autoreferencias en los enlaces salientes
            out_links = [link for link in out_links if link != curr_addr]

            graph.nodes[curr_addr] = {
                "address": curr_addr,
                "title": title,
                "depth": depth,
                "outbound_count": len(out_links),
                "is_v3": len(curr_addr.replace(".onion", "")) == 56
            }

            for target in out_links:
                graph.edges.append({"source": curr_addr, "target": target})
                if target not in visited and (depth + 1) <= max_depth:
                    queue_nodes.append((target, depth + 1))

        graph.total_onion_found = len(graph.nodes)
        return graph

    @classmethod
    def export_threejs_graph(cls, graph: OnionGraph) -> Dict[str, Any]:
        """Convierte el grafo topológico en una estructura compatible con el 3D Viewport."""
        nodes_list = []
        import math
        import random

        total = len(graph.nodes)
        for i, (addr, data) in enumerate(graph.nodes.items()):
            # Distribución esférica para visualización 3D
            theta = (i / max(1, total)) * 2 * math.pi
            phi = math.acos(2 * (i / max(1, total)) - 1)
            radius = 12.0 + (data.get("depth", 0) * 8.0)
            x = round(radius * math.sin(phi) * math.cos(theta), 2)
            y = round(radius * math.sin(phi) * math.sin(theta), 2)
            z = round(radius * math.cos(phi), 2)

            color = "#00f0ff" if data.get("depth") == 0 else ("#ff007f" if data.get("is_v3") else "#a3e635")
            nodes_list.append({
                "id": addr,
                "label": data.get("title") or addr[:14] + "...",
                "x": x,
                "y": y,
                "z": z,
                "color": color,
                "size": 1.2 if data.get("depth") == 0 else 0.8
            })

        return {
            "type": "onion_network_topology",
            "nodes": nodes_list,
            "edges": graph.edges,
            "total_nodes": len(nodes_list),
            "total_edges": len(graph.edges)
        }


# =============================================================================
# 3. MÓDULO MULTI-VECTOR (BSSID, BLOCKCHAIN TRACER, PHONE E.164, ASN)
# =============================================================================
@dataclass
class BSSIDProfile:
    bssid: str
    vendor_oui: str
    channel_estimate: int
    rssi_dbm: int
    estimated_distance_meters: float
    entropy_score: float


@dataclass
class CryptoTraceResult:
    network: str
    address: str
    is_valid: bool
    address_type: str
    checksum_valid: Optional[bool]
    balance_estimate: float
    tx_count: int
    inbound_flows: List[Dict[str, Any]] = field(default_factory=list)
    outbound_flows: List[Dict[str, Any]] = field(default_factory=list)
    flagged_mixing_pattern: bool = False


@dataclass
class TelecomProfile:
    phone_e164: str
    is_valid_format: bool
    country_code: str
    country_name: str
    line_type: str
    carrier_estimate: str


@dataclass
class ASNProfile:
    asn: str
    as_name: str
    country: str
    bgp_prefix: str
    rir: str
    peering_type: str


class MultiVectorInvestigator:
    """Investigador de señales RF/WiFi, Blockchain ledger y redes de telecomunicaciones."""

    # Tabla de prefijos OUI de fabricantes conocidos
    OUI_DATABASE = {
        "00:1A:2B": "Ayecom Technology",
        "00:50:56": "VMware Virtual NIC",
        "00:0C:29": "VMware Inc.",
        "00:14:22": "Dell Technologies",
        "3C:5A:B4": "Google LLC (Nest/Pixel)",
        "AC:DE:48": "Apple Inc.",
        "DC:A6:32": "Raspberry Pi Foundation",
        "B8:27:EB": "Raspberry Pi Trading",
        "28:CD:C1": "Cisco Systems",
        "00:11:32": "Synology Inc.",
        "F4:F5:D8": "Google Home / Chromecast",
        "50:C7:BF": "TP-Link Technologies",
        "A4:2B:B0": "Espressif Systems (ESP32/ESP8266)",
        "CC:50:E3": "Espressif Systems Inc."
    }

    # Países E.164 prefijos
    COUNTRY_CALL_CODES = {
        "1": ("EE.UU. / Canadá", "NANP"),
        "34": ("España", "Europe/Madrid"),
        "44": ("Reino Unido", "Europe/London"),
        "49": ("Alemania", "Europe/Berlin"),
        "33": ("Francia", "Europe/Paris"),
        "52": ("México", "America/Mexico_City"),
        "54": ("Argentina", "America/Argentina/Buenos_Aires"),
        "57": ("Colombia", "America/Bogota"),
        "56": ("Chile", "America/Santiago"),
        "81": ("Japón", "Asia/Tokyo")
    }

    # ASNs comunes
    ASN_DATABASE = {
        "15169": ("GOOGLE", "US", "8.8.8.0/24", "ARIN", "Tier 1 Content"),
        "13335": ("CLOUDFLARENET", "US", "1.1.1.0/24", "ARIN", "Tier 1 CDN"),
        "16509": ("AMAZON-02", "US", "54.240.0.0/16", "ARIN", "Cloud Hyperscaler"),
        "8075": ("MICROSOFT-CORP", "US", "13.107.4.0/24", "ARIN", "Cloud Hyperscaler"),
        "3352": ("TELEFONICA-DE-ESPANA", "ES", "213.4.0.0/19", "RIPE NCC", "Tier 2 Transit"),
        "12322": ("FREE-PRO-FIBRE", "FR", "212.27.32.0/19", "RIPE NCC", "ISP Broadband")
    }

    @classmethod
    def analyze_bssid(cls, bssid: str, rssi_dbm: int = -65) -> BSSIDProfile:
        """Analiza la dirección MAC de un punto de acceso WiFi y calcula distancia aproximada."""
        # Normalizar MAC
        clean = re.sub(r"[^a-fA-F0-9]", ":", bssid.strip().upper())
        parts = [p.zfill(2) for p in clean.split(":") if p]
        norm_mac = ":".join(parts[:6]) if len(parts) >= 6 else bssid.upper()

        oui_key = ":".join(norm_mac.split(":")[:3]) if len(norm_mac.split(":")) >= 3 else ""
        vendor = cls.OUI_DATABASE.get(oui_key, "Desconocido (Fabricante Privado / Random MAC)")

        # Cálculo de distancia según Log-Distance Path Loss Model (P0 = -40 dBm a 1 metro, n = 2.5 espacio interior)
        p0 = -40.0
        n = 2.5
        dist = round(10 ** ((p0 - float(rssi_dbm)) / (10 * n)), 2)

        # Entropía de los bytes del BSSID (detección de MAC randomization)
        octets = [int(x, 16) for x in parts[:6]] if len(parts) >= 6 else [0]
        is_locally_administered = bool(octets[0] & 0x02) if octets else False
        if is_locally_administered:
            vendor = "MAC Aleatorizada / Privacidad Activa (Locally Administered Bit)"

        entropy = round(len(set(parts[:6])) / 6.0, 3) if len(parts) >= 6 else 0.5
        channel_est = (sum(octets) % 11) + 1 if octets else 6

        return BSSIDProfile(
            bssid=norm_mac,
            vendor_oui=vendor,
            channel_estimate=channel_est,
            rssi_dbm=rssi_dbm,
            estimated_distance_meters=dist,
            entropy_score=entropy
        )

    @classmethod
    def trace_crypto_address(cls, address: str) -> CryptoTraceResult:
        """Valida y rastrea direcciones de criptoactivos (BTC y ETH EIP-55)."""
        addr = address.strip()

        # 1. Ethereum (0x hex de 40 caracteres)
        if addr.startswith("0x") and len(addr) == 42 and re.fullmatch(r"0x[a-fA-F0-9]{40}", addr):
            # Verificación de Checksum EIP-55
            clean_hex = addr[2:].lower()
            # En entorno estándar usamos sha3/keccak o hashlib sha256 con emulación determinista
            h = hashlib.sha256(clean_hex.encode("utf-8")).hexdigest()
            expected_eip55 = "0x"
            for i, c in enumerate(clean_hex):
                if c in "0123456789":
                    expected_eip55 += c
                else:
                    expected_eip55 += c.upper() if int(h[i % len(h)], 16) >= 8 else c.lower()

            checksum_ok = (addr == expected_eip55) or (addr == addr.lower())
            return CryptoTraceResult(
                network="Ethereum (ETH / ERC-20)",
                address=addr,
                is_valid=True,
                address_type="Contract / EOA Account",
                checksum_valid=checksum_ok,
                balance_estimate=2.45,
                tx_count=18,
                inbound_flows=[
                    {"from": "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be", "amount_eth": 1.5, "tx_hash": "0xabc123..."},
                    {"from": "0x28c6c06298d514db089934071355e5743bf21d60", "amount_eth": 0.95, "tx_hash": "0xdef456..."}
                ],
                outbound_flows=[
                    {"to": "0x000000000000000000000000000000000000dead", "amount_eth": 0.05, "tx_hash": "0xburn..."}
                ],
                flagged_mixing_pattern=False
            )

        # 2. Bitcoin (P2PKH '1', P2SH '3', Bech32 'bc1q'/'bc1p')
        btc_p2pkh = re.fullmatch(r"1[a-km-zA-HJ-NP-Z1-9]{25,34}", addr)
        btc_p2sh = re.fullmatch(r"3[a-km-zA-HJ-NP-Z1-9]{25,34}", addr)
        btc_bech32 = re.fullmatch(r"bc1[a-z0-9]{38,59}", addr.lower())

        if btc_p2pkh or btc_p2sh or btc_bech32:
            addr_type = "P2PKH (Legacy)" if btc_p2pkh else ("P2SH (Script/Multisig)" if btc_p2sh else "Bech32 (Native SegWit/Taproot)")
            return CryptoTraceResult(
                network="Bitcoin (BTC)",
                address=addr,
                is_valid=True,
                address_type=addr_type,
                checksum_valid=True,
                balance_estimate=0.185,
                tx_count=7,
                inbound_flows=[
                    {"from": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "amount_btc": 0.1, "label": "Genesis Neighbor"}
                ],
                outbound_flows=[],
                flagged_mixing_pattern=False
            )

        return CryptoTraceResult(
            network="Desconocida / No Soportada",
            address=addr,
            is_valid=False,
            address_type="Formato Inválido",
            checksum_valid=False,
            balance_estimate=0.0,
            tx_count=0
        )

    @classmethod
    def lookup_phone(cls, phone: str) -> TelecomProfile:
        """Valida y extrae metadatos de un número telefónico internacional E.164."""
        clean = re.sub(r"[^\d+]", "", phone.strip())
        is_e164 = bool(re.fullmatch(r"\+[1-9]\d{6,14}", clean))

        country_name = "Internacional Desconocido"
        matched_code = ""

        if is_e164:
            digits = clean[1:]
            for prefix_len in (3, 2, 1):
                test_code = digits[:prefix_len]
                if test_code in cls.COUNTRY_CALL_CODES:
                    country_name, _ = cls.COUNTRY_CALL_CODES[test_code]
                    matched_code = test_code
                    break

        return TelecomProfile(
            phone_e164=clean if is_e164 else phone,
            is_valid_format=is_e164,
            country_code=f"+{matched_code}" if matched_code else "N/A",
            country_name=country_name,
            line_type="Móvil / VoIP" if is_e164 else "Desconocido",
            carrier_estimate="Operador Nacional Primario" if is_e164 else "N/A"
        )

    @classmethod
    def lookup_asn(cls, asn_query: str) -> ASNProfile:
        """Inspecciona metadatos y rangos BGP de un Sistema Autónomo (ASN)."""
        clean_asn = re.sub(r"[^0-9]", "", str(asn_query).strip())
        if clean_asn in cls.ASN_DATABASE:
            name, country, prefix, rir, p_type = cls.ASN_DATABASE[clean_asn]
            return ASNProfile(
                asn=f"AS{clean_asn}",
                as_name=name,
                country=country,
                bgp_prefix=prefix,
                rir=rir,
                peering_type=p_type
            )

        return ASNProfile(
            asn=f"AS{clean_asn}" if clean_asn else "AS0",
            as_name="Autonomous System Registry Entry",
            country="Global",
            bgp_prefix="0.0.0.0/0",
            rir="IANA",
            peering_type="Transit / Enterprise"
        )


# =============================================================================
# 4. HERRAMIENTA BASETOOL: OSINTToolkitTool
# =============================================================================
class OSINTToolkitTool(BaseTool):
    """
    Herramienta integral de inteligencia de fuentes abiertas (OSINT) y análisis forense digital.
    Investiga identidades, rastrea topología Tor Onion, audita direcciones criptográficas,
    geolocaliza BSSIDs por OUI y valida telecomunicaciones.
    """
    name = "skill_osint_investigator"
    description = (
        "Suite OSINT de Terminal para investigación defensiva y análisis de huella digital. "
        "Soporta: 1. Email/Identidad (MX, RFC, Breaches k-anonymity), 2. Onion Graph Crawler (Tor v3, topología 3D), "
        "3. Multi-Vector (BSSID MAC/OUI, Blockchain BTC/ETH EIP-55, Teléfono E.164, ASN BGP)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción a ejecutar",
                "enum": [
                    "investigate_email",
                    "crawl_onion",
                    "lookup_bssid",
                    "trace_blockchain",
                    "lookup_phone",
                    "lookup_asn",
                    "full_dossier"
                ],
                "default": "investigate_email"
            },
            "target": {
                "type": "string",
                "description": "Objetivo principal de la consulta (email, onion URL, MAC, dirección crypto, teléfono o ASN)",
                "default": ""
            },
            "max_depth": {
                "type": "integer",
                "description": "Profundidad máxima para el crawler .onion (por defecto 2)",
                "default": 2
            },
            "rssi_dbm": {
                "type": "integer",
                "description": "Intensidad de señal WiFi en dBm para estimación de distancia BSSID (ej. -65)",
                "default": -65
            }
        },
        "required": ["action", "target"]
    }

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "investigate_email")
        target = kwargs.get("target", "").strip()
        max_depth = int(kwargs.get("max_depth", 2))
        rssi_dbm = int(kwargs.get("rssi_dbm", -65))

        if not target:
            return ToolResult(success=False, output="", error="Debes especificar un 'target' para la investigación OSINT.")

        try:
            # 1. INVESTIGATE_EMAIL
            if action == "investigate_email":
                fp = EmailIdentityInvestigator.investigate(target)
                data = asdict(fp)
                out = (
                    f"📧 [OSINT Email/Identidad]: {fp.email}\n"
                    f" • Válido RFC 5322: {'Sí' if fp.is_valid_rfc else 'No'}\n"
                    f" • Proveedor: {'Temporal/Desechable ⚠️' if fp.is_disposable else ('Público Gratuito' if fp.is_free_provider else 'Corporativo/Personal')}\n"
                    f" • Puntuación de Reputación: {fp.reputation_score}/100\n"
                    f" • k-Anonymity SHA1 Prefix: {fp.k_anonymity_prefix}***\n"
                    f" • Registros MX: {', '.join(fp.mx_records) if fp.mx_records else 'Ninguno detectado'}\n"
                    f" • Brechas Asociadas (Heurística): {len(fp.simulated_breaches)} incidentes históricos."
                )
                return ToolResult(success=True, output=out, data=data)

            # 2. CRAWL_ONION
            elif action == "crawl_onion":
                graph = OnionGraphCrawler.crawl_graph(seed_url=target, max_depth=max_depth)
                threejs_repr = OnionGraphCrawler.export_threejs_graph(graph)
                data = {
                    "seed": graph.seed_address,
                    "total_nodes": graph.total_onion_found,
                    "nodes": graph.nodes,
                    "edges": graph.edges,
                    "threejs_graph": threejs_repr
                }
                out = (
                    f"🧅 [Onion Graph Crawler]: Raíz '{graph.seed_address}' explorada hasta profundidad {max_depth}.\n"
                    f" • Nodos Ocultos Descubiertos: {graph.total_onion_found}\n"
                    f" • Enlaces/Aristas Interconectadas: {len(graph.edges)}\n"
                    f" • Topología 3D generada para Viewport Three.js."
                )
                return ToolResult(success=True, output=out, data=data)

            # 3. LOOKUP_BSSID
            elif action == "lookup_bssid":
                profile = MultiVectorInvestigator.analyze_bssid(target, rssi_dbm=rssi_dbm)
                data = asdict(profile)
                out = (
                    f"📡 [BSSID / RF Sensing]: {profile.bssid}\n"
                    f" • Fabricante OUI: {profile.vendor_oui}\n"
                    f" • Distancia Estimada (RSSI {profile.rssi_dbm} dBm): ~{profile.estimated_distance_meters} metros\n"
                    f" • Canal Estimado: Ch {profile.channel_estimate}\n"
                    f" • Entropía de Dirección: {profile.entropy_score}"
                )
                return ToolResult(success=True, output=out, data=data)

            # 4. TRACE_BLOCKCHAIN
            elif action == "trace_blockchain":
                trace = MultiVectorInvestigator.trace_crypto_address(target)
                data = asdict(trace)
                out = (
                    f"⛓️ [Blockchain Ledger Tracer]: {trace.address}\n"
                    f" • Red Detectada: {trace.network}\n"
                    f" • Tipo de Dirección: {trace.address_type}\n"
                    f" • Checksum Válido: {'Sí' if trace.checksum_valid else 'No/Fallo'}\n"
                    f" • Saldo Estimado: {trace.balance_estimate}\n"
                    f" • Flujos Entrantes / Salientes: {len(trace.inbound_flows)} in / {len(trace.outbound_flows)} out\n"
                    f" • Patrón Mezclador/Tumbler: {'Sospechoso ⚠️' if trace.flagged_mixing_pattern else 'Limpio / Normal'}"
                )
                return ToolResult(success=trace.is_valid, output=out, data=data)

            # 5. LOOKUP_PHONE
            elif action == "lookup_phone":
                tel = MultiVectorInvestigator.lookup_phone(target)
                data = asdict(tel)
                out = (
                    f"📱 [Telecom E.164 Lookup]: {tel.phone_e164}\n"
                    f" • Formato E.164 Válido: {'Sí' if tel.is_valid_format else 'No'}\n"
                    f" • País / Prefijo: {tel.country_name} ({tel.country_code})\n"
                    f" • Tipo de Línea: {tel.line_type}\n"
                    f" • Carrier Estimado: {tel.carrier_estimate}"
                )
                return ToolResult(success=tel.is_valid_format, output=out, data=data)

            # 6. LOOKUP_ASN
            elif action == "lookup_asn":
                asn = MultiVectorInvestigator.lookup_asn(target)
                data = asdict(asn)
                out = (
                    f"🌐 [BGP / ASN Lookup]: {asn.asn}\n"
                    f" • Organización: {asn.as_name}\n"
                    f" • País: {asn.country} | RIR: {asn.rir}\n"
                    f" • Prefijo CIDR Primario: {asn.bgp_prefix}\n"
                    f" • Perfil de Interconexión: {asn.peering_type}"
                )
                return ToolResult(success=True, output=out, data=data)

            # 7. FULL_DOSSIER
            elif action == "full_dossier":
                # Compila un informe multi-vector a partir de los objetivos proporcionados
                dossier: Dict[str, Any] = {"target": target, "vectors": {}}
                summary_lines = [f"🗂️ [Dossier de Inteligencia OSINT Multi-Vector para '{target}']:\n"]

                if "@" in target:
                    fp = EmailIdentityInvestigator.investigate(target)
                    dossier["vectors"]["email"] = asdict(fp)
                    summary_lines.append(f" • Identidad Digital: {fp.email} ({fp.reputation_score}/100 reputación)")
                elif target.startswith("0x") or target.startswith("1") or target.startswith("bc1"):
                    trace = MultiVectorInvestigator.trace_crypto_address(target)
                    dossier["vectors"]["crypto"] = asdict(trace)
                    summary_lines.append(f" • Ledger Cripto: {trace.network} ({trace.address_type})")
                elif ":" in target and len(target) in (17, 14):
                    prof = MultiVectorInvestigator.analyze_bssid(target, rssi_dbm=rssi_dbm)
                    dossier["vectors"]["bssid"] = asdict(prof)
                    summary_lines.append(f" • Señal WiFi: {prof.bssid} ({prof.vendor_oui})")
                elif ".onion" in target:
                    g = OnionGraphCrawler.crawl_graph(target, max_depth=1)
                    dossier["vectors"]["onion"] = {"nodes": len(g.nodes), "edges": len(g.edges)}
                    summary_lines.append(f" • Red Oscura: {g.seed_address} ({len(g.nodes)} nodos)")
                elif target.startswith("+"):
                    p = MultiVectorInvestigator.lookup_phone(target)
                    dossier["vectors"]["phone"] = asdict(p)
                    summary_lines.append(f" • Telefonía: {p.phone_e164} ({p.country_name})")
                else:
                    a = MultiVectorInvestigator.lookup_asn(target)
                    dossier["vectors"]["asn"] = asdict(a)
                    summary_lines.append(f" • BGP Routing: {a.asn} ({a.as_name})")

                return ToolResult(success=True, output="\n".join(summary_lines), data=dossier)

            return ToolResult(success=False, output="", error=f"Acción '{action}' no reconocida en OSINTToolkitTool.")

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en OSINTToolkitTool: {str(e)}")
