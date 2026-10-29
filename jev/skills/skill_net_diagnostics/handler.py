"""
Habilidad de Diagnóstico de Red Nativa (TCP Ping, DNS Resolution y RTT).
Implementación pura en la biblioteca estándar (socket, time) sin dependencias externas.
"""
from typing import Dict, Any, List, Optional
import socket
import time


def dns_resolve(hostname: str) -> Dict[str, Any]:
    """Resuelve nombres de dominio a direcciones IP con medición de latencia DNS."""
    t0 = time.perf_counter()
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        ips = list(set([item[4][0] for item in addr_info]))
        return {
            "success": True,
            "target": hostname,
            "resolved_ips": ips,
            "lookup_time_ms": duration_ms,
            "count": len(ips)
        }
    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "success": False,
            "target": hostname,
            "error": f"Fallo de resolución DNS: {str(e)}",
            "lookup_time_ms": duration_ms
        }


def tcp_ping(host: str, port: int = 80, timeout: float = 2.0, count: int = 3) -> Dict[str, Any]:
    """
    Ejecuta un ping TCP midiendo el tiempo de establecimiento del handshake SYN-SYNACK
    para calcular RTT exacto, jitter y tasa de pérdida de paquetes.
    """
    latencies: List[float] = []
    success_count = 0

    for i in range(max(1, count)):
        t_start = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            rtt_ms = (time.perf_counter() - t_start) * 1000
            latencies.append(round(rtt_ms, 2))
            success_count += 1
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            # Si la conexión es rechazada por el puerto, el host sigue respondiendo a nivel de red
            if isinstance(e, ConnectionRefusedError):
                rtt_ms = (time.perf_counter() - t_start) * 1000
                latencies.append(round(rtt_ms, 2))
                success_count += 1
            else:
                pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    if not latencies:
        return {
            "success": False,
            "target": f"{host}:{port}",
            "sent": count,
            "received": 0,
            "packet_loss_pct": 100.0,
            "status": "Host inalcanzable o timeout agotado"
        }

    min_rtt = min(latencies)
    max_rtt = max(latencies)
    avg_rtt = round(sum(latencies) / len(latencies), 2)
    jitter = round(max_rtt - min_rtt, 2)
    loss_pct = round(((count - success_count) / count) * 100.0, 1)

    return {
        "success": True,
        "target": f"{host}:{port}",
        "sent": count,
        "received": success_count,
        "packet_loss_pct": loss_pct,
        "rtt_min_ms": min_rtt,
        "rtt_avg_ms": avg_rtt,
        "rtt_max_ms": max_rtt,
        "jitter_ms": jitter,
        "samples": latencies
    }


def diagnose_host(target: str, ports: Optional[List[int]] = None, timeout: float = 2.0) -> Dict[str, Any]:
    """Diagnóstico integral: resolución DNS + escaneo de latencia en puertos comunes."""
    ports_to_check = ports or [80, 443, 8080, 22]
    dns_res = dns_resolve(target)
    primary_ip = dns_res["resolved_ips"][0] if dns_res.get("resolved_ips") else target

    port_diagnostics = {}
    for p in ports_to_check:
        port_diagnostics[str(p)] = tcp_ping(primary_ip, port=p, timeout=timeout, count=2)

    return {
        "success": True,
        "target": target,
        "dns": dns_res,
        "ports": port_diagnostics
    }


def handle(action: str = "tcp_ping", target: str = "127.0.0.1", port: int = 80, count: int = 3, timeout: float = 2.0) -> Dict[str, Any]:
    """Punto de entrada de la habilidad."""
    act = (action or "tcp_ping").lower()
    if act == "dns_resolve":
        return dns_resolve(target)
    elif act == "diagnose_host":
        return diagnose_host(target, timeout=timeout)
    else:
        return tcp_ping(host=target, port=int(port), timeout=float(timeout), count=int(count))
