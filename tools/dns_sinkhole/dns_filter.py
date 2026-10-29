"""
Módulo de DNS Sinkhole & Filtro de Publicidad de Red.
Servidor e interceptor DNS ligero inspirado en Pi-hole y ESP32 AdBlocker.
Bloquea dominios de telemetría, rastreadores y publicidad respondiendo con 0.0.0.0.
"""
from typing import Set, Dict, Any, Optional, Tuple
import socket
import struct
import threading
import time
import argparse
from pathlib import Path


class DnsSinkhole:
    """Interceptor y servidor DNS sinkhole con filtrado por lista negra."""

    def __init__(self, upstream_dns: str = "1.1.1.1", upstream_port: int = 53):
        self.upstream_dns = upstream_dns
        self.upstream_port = upstream_port
        self.blocklist: Set[str] = set()
        self.stats = {
            "total_queries": 0,
            "blocked_queries": 0,
            "forwarded_queries": 0,
            "start_time": time.time(),
            "blocked_domains_log": []
        }
        self.running = False
        self.server_socket: Optional[socket.socket] = None

    def load_blocklist_from_file(self, file_path: str) -> int:
        """
        Carga dominios bloqueados desde un archivo hosts o lista plana de dominios.
        Ignora comentarios (#) y mapeos de localhost.
        """
        path = Path(file_path)
        if not path.exists():
            return 0

        count = 0
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                    domain = parts[1].lower().strip()
                else:
                    domain = parts[0].lower().strip()

                # Ignorar nombres locales
                if domain in ("localhost", "broadcasthost", "local"):
                    continue

                if domain:
                    self.blocklist.add(domain)
                    count += 1
        return count

    def add_domains(self, domains: list) -> None:
        """Añade una lista de dominios en memoria a la lista de bloqueo."""
        for d in domains:
            clean = d.lower().strip()
            if clean:
                self.blocklist.add(clean)

    def is_blocked(self, domain: str) -> bool:
        """Comprueba si un dominio o sus subdominios principales están en la lista de bloqueo."""
        d = domain.lower().rstrip(".")
        if d in self.blocklist:
            return True
        # Comprobar subdominios padres (ej: ad.tracker.example.com -> tracker.example.com -> example.com)
        parts = d.split(".")
        for i in range(1, len(parts) - 1):
            parent = ".".join(parts[i:])
            if parent in self.blocklist:
                return True
        return False

    @staticmethod
    def parse_dns_domain_name(data: bytes, offset: int = 12) -> Tuple[str, int]:
        """Extrae el nombre de dominio consultado del payload de un paquete DNS RFC 1035."""
        labels = []
        i = offset
        while i < len(data):
            length = data[i]
            if length == 0:
                i += 1
                break
            # Soporte de punteros de compresión RFC 1035
            if (length & 0xC0) == 0xC0:
                i += 2
                break
            i += 1
            labels.append(data[i:i + length].decode("ascii", errors="ignore"))
            i += length
        return ".".join(labels), i

    @staticmethod
    def build_sinkhole_response(query_data: bytes, domain: str, sinkhole_ip: str = "0.0.0.0") -> bytes:
        """
        Construye una respuesta DNS directa con registro A apuntando a 0.0.0.0 para dominios bloqueados.
        """
        if len(query_data) < 12:
            return b""

        transaction_id = query_data[:2]
        # Flags: Response, Opcode=Standard, Authoritative=0, Truncated=0, Recursion Desired (copiado),
        # Recursion Available=1, Response Code=NoError (0)
        flags = struct.pack(">H", 0x8180)
        qdcount = struct.pack(">H", 1)  # 1 pregunta
        ancount = struct.pack(">H", 1)  # 1 respuesta
        nscount = struct.pack(">H", 0)
        arcount = struct.pack(">H", 0)

        header = transaction_id + flags + qdcount + ancount + nscount + arcount

        # Encontrar el final de la sección Question
        _, end_offset = DnsSinkhole.parse_dns_domain_name(query_data, 12)
        qtype_qclass = query_data[end_offset:end_offset + 4]
        question_section = query_data[12:end_offset + 4]

        # Sección Answer: Name Pointer (0xc00c apuntando al inicio del nombre en byte 12),
        # Type A (1), Class IN (1), TTL (60s), Data Length (4 bytes), IP (4 bytes)
        name_pointer = struct.pack(">H", 0xC00C)
        type_a = struct.pack(">H", 1)
        class_in = struct.pack(">H", 1)
        ttl = struct.pack(">I", 60)
        rdlength = struct.pack(">H", 4)
        rdata = socket.inet_aton(sinkhole_ip)

        answer_section = name_pointer + type_a + class_in + ttl + rdlength + rdata
        return header + question_section + answer_section

    def forward_upstream(self, query_data: bytes, timeout: float = 2.0) -> bytes:
        """Reenvía la consulta al servidor DNS upstream legítimo (ej. 1.1.1.1 o 8.8.8.8)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(query_data, (self.upstream_dns, self.upstream_port))
            response, _ = sock.recvfrom(2048)
            return response
        except Exception:
            return b""
        finally:
            sock.close()

    def handle_dns_query(self, data: bytes) -> bytes:
        """Procesa una consulta DNS: devuelve 0.0.0.0 si está bloqueada o reenvía al upstream."""
        self.stats["total_queries"] += 1
        domain, _ = self.parse_dns_domain_name(data, 12)

        if domain and self.is_blocked(domain):
            self.stats["blocked_queries"] += 1
            if len(self.stats["blocked_domains_log"]) < 100:
                self.stats["blocked_domains_log"].append({"domain": domain, "timestamp": time.time()})
            return self.build_sinkhole_response(data, domain, sinkhole_ip="0.0.0.0")
        else:
            self.stats["forwarded_queries"] += 1
            return self.forward_upstream(data)

    def start_server(self, host: str = "127.0.0.1", port: int = 5353) -> None:
        """Inicia el servidor UDP en un hilo en segundo plano."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.bind((host, port))
        self.running = True

        def server_loop():
            while self.running:
                try:
                    data, addr = self.server_socket.recvfrom(2048)
                    resp = self.handle_dns_query(data)
                    if resp:
                        self.server_socket.sendto(resp, addr)
                except Exception:
                    if not self.running:
                        break

        thread = threading.Thread(target=server_loop, daemon=True)
        thread.start()

    def stop_server(self) -> None:
        """Detiene el socket de escucha."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Devuelve métricas operativas del filtro DNS."""
        total = self.stats["total_queries"]
        blocked = self.stats["blocked_queries"]
        ratio = (blocked / total * 100.0) if total > 0 else 0.0
        return {
            "total_queries": total,
            "blocked_queries": blocked,
            "forwarded_queries": self.stats["forwarded_queries"],
            "block_rate_percentage": round(ratio, 2),
            "blocklist_rules_count": len(self.blocklist),
            "upstream_dns": self.upstream_dns
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DNS Sinkhole & Ad-Filter")
    parser.add_argument("--blocklist", help="Ruta a archivo de dominios bloqueados (hosts o lista)")
    parser.add_argument("--test-domain", help="Verificar si un dominio específico está bloqueado")
    parser.add_argument("--port", type=int, default=5353, help="Puerto UDP para el servidor (default 5353)")
    args = parser.parse_args()

    sinkhole = DnsSinkhole()
    if args.blocklist:
        n = sinkhole.load_blocklist_from_file(args.blocklist)
        print(f"[*] Cargadas {n} reglas desde {args.blocklist}")
    else:
        # Reglas de ejemplo por defecto
        sinkhole.add_domains(["adservice.google.com", "doubleclick.net", "telemetry.bad.org"])

    if args.test_domain:
        blocked = sinkhole.is_blocked(args.test_domain)
        print(f"Dominio '{args.test_domain}': {'BLOQUEADO (0.0.0.0)' if blocked else 'PERMITIDO'}")
    else:
        print(f"[*] Iniciando DNS Sinkhole en 127.0.0.1:{args.port} (Ctrl+C para salir)...")
        sinkhole.start_server(port=args.port)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sinkhole.stop_server()
            print("\n[*] Servidor detenido.")
