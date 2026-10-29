"""
Módulo REA (Reverse Engineering Assistant) - Descompilador y Analizador Estático.
Disecciona binarios, ejecutables (.exe, .dll, ELF), scripts compilados (.pyc) y código
para extraer metadatos, strings, funciones de sistema y generar reportes estructurados de comportamiento.
"""
from typing import Dict, Any, List, Optional, Tuple
import os
import re
import sys
import hashlib
import math
import struct
import argparse
from pathlib import Path


class ReverseEngineeringAssistant:
    """Analizador estático y asistente de ingeniería inversa."""

    # Firmas mágicas de archivos binarios comunes
    FILE_SIGNATURES = {
        b"MZ": "Windows Executable / DLL (PE)",
        b"\x7fELF": "Linux Executable (ELF)",
        b"\xca\xfe\xba\xbe": "Java Class / Mach-O Fat Binary",
        b"\xfe\xed\xfa\xce": "macOS Mach-O 32-bit",
        b"\xfe\xed\xfa\xcf": "macOS Mach-O 64-bit",
        b"PK\x03\x04": "ZIP / APK / JAR Archive",
        b"Rar!\x1a\x07": "RAR Archive",
        b"\x1f\x8b": "GZIP Archive",
        b"sqlite format 3\x00": "SQLite Database",
    }

    # Palabras clave y APIs sensibles de sistema y red para evaluar riesgo
    SUSPICIOUS_INDICATORS = {
        "network": [
            r"https?://[^\s\"']+",
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            r"\b(?:socket|connect|bind|listen|send|recv|WSAStartup|URLDownloadToFile|HttpOpenRequest)\b",
            r"\b(?:urllib|requests|curl|wget)\b"
        ],
        "system_execution": [
            r"\b(?:CreateProcess|ShellExecute|WinExec|system|popen|subprocess|powershell|cmd\.exe)\b",
            r"\b(?:bash|sh|exec|spawn)\b"
        ],
        "persistence_registry": [
            r"\b(?:RegCreateKey|RegSetValue|RegOpenKey|CurrentVersion\\Run|schtasks)\b",
            r"\b(?:cron|systemd|launchd)\b"
        ],
        "obfuscation_crypto": [
            r"\b(?:base64|b64decode|CryptEncrypt|AES|RC4|XOR|VirtualAlloc|VirtualProtect)\b",
            r"\b(?:eval|exec|compile|__import__)\b"
        ]
    }

    def __init__(self, target_path: str):
        self.target_path = Path(target_path)
        if not self.target_path.exists():
            raise FileNotFoundError(f"Archivo objetivo no encontrado: {target_path}")
        self.file_bytes = self.target_path.read_bytes()

    def calculate_entropy(self) -> float:
        """Calcula la entropía de Shannon (0 a 8). Valores > 7.2 suelen indicar compresión o empaquetamiento."""
        if not self.file_bytes:
            return 0.0
        entropy = 0.0
        byte_counts = [0] * 256
        for b in self.file_bytes:
            byte_counts[b] += 1
        total = len(self.file_bytes)
        for count in byte_counts:
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        return round(entropy, 3)

    def identify_format(self) -> str:
        """Determina el tipo y formato del archivo inspeccionando los primeros bytes mágicos."""
        header = self.file_bytes[:16]
        for sig, fmt in self.FILE_SIGNATURES.items():
            if header.startswith(sig):
                return fmt

        # Verificar si es bytecode de Python (.pyc)
        if self.target_path.suffix.lower() == ".pyc":
            return "Python Bytecode (.pyc)"

        # Verificar si es texto / script plano
        try:
            self.file_bytes[:1024].decode("utf-8")
            if self.target_path.suffix.lower() in [".py", ".pyw"]:
                return "Python Script (.py)"
            elif self.target_path.suffix.lower() in [".ps1", ".bat", ".cmd"]:
                return "Windows Script (.ps1 / .bat)"
            elif self.target_path.suffix.lower() in [".sh", ".bash"]:
                return "Shell Script (.sh)"
            return "Texto Plano / Código Fuente"
        except UnicodeDecodeError:
            return "Binario Desconocido"

    def extract_strings(self, min_len: int = 4, max_strings: int = 150) -> List[str]:
        """Extrae secuencias de caracteres ASCII y UTF-16 imprimibles."""
        ascii_strings = re.findall(b"[\x20-\x7e]{" + str(min_len).encode() + b",}", self.file_bytes)
        # Decodificar y desduplicar preservando orden
        seen = set()
        results = []
        for s in ascii_strings:
            try:
                decoded = s.decode("ascii").strip()
                if decoded and decoded not in seen:
                    seen.add(decoded)
                    results.append(decoded)
                    if len(results) >= max_strings:
                        break
            except Exception:
                pass
        return results

    def analyze_indicators(self, strings_list: List[str]) -> Dict[str, List[str]]:
        """Busca patrones de red, comandos de sistema, persistencia y criptografía en las cadenas."""
        matches: Dict[str, List[str]] = {cat: [] for cat in self.SUSPICIOUS_INDICATORS}
        full_text = "\n".join(strings_list)

        for category, patterns in self.SUSPICIOUS_INDICATORS.items():
            found_category = set()
            for pat in patterns:
                found = re.findall(pat, full_text, re.IGNORECASE)
                for item in found:
                    found_category.add(item)
            matches[category] = list(found_category)[:20]

        return matches

    def disassemble_if_python(self) -> Optional[str]:
        """Si el archivo es un script Python o bytecode, genera el desensamblado nativo con 'dis'."""
        if self.target_path.suffix.lower() in [".py", ".pyw"]:
            try:
                import dis
                code_text = self.target_path.read_text(encoding="utf-8", errors="ignore")
                compiled = compile(code_text, str(self.target_path), "exec")
                import io
                output = io.StringIO()
                dis.dis(compiled, file=output)
                return output.getvalue()[:2000]
            except Exception as e:
                return f"Error en desensamblado Python: {e}"
        return None

    def assess_risk_level(self, indicators: Dict[str, List[str]], entropy: float) -> Tuple[str, str]:
        """Evalúa el nivel de riesgo en base a los indicadores y la entropía."""
        score = 0
        reasons = []

        if indicators.get("system_execution"):
            score += 3
            reasons.append(f"Invocación de comandos de consola/procesos ({len(indicators['system_execution'])} referencias)")
        if indicators.get("network"):
            score += 2
            reasons.append(f"Actividad o llamadas de red ({len(indicators['network'])} referencias)")
        if indicators.get("persistence_registry"):
            score += 3
            reasons.append("Acceso a claves de registro de Windows o persistencia")
        if indicators.get("obfuscation_crypto"):
            score += 2
            reasons.append("Uso de funciones de codificación/evaluación dinámica")
        if entropy > 7.2:
            score += 2
            reasons.append(f"Alta entropía ({entropy}/8.0), posible binario empaquetado u ofuscado")

        if score >= 5:
            return "ALTO", "; ".join(reasons)
        elif score >= 2:
            return "MEDIO", "; ".join(reasons)
        else:
            return "BAJO", "No se detectaron patrones anómalos o llamadas de alto riesgo."

    def generate_report(self) -> str:
        """Genera un reporte completo en formato Markdown."""
        file_size = len(self.file_bytes)
        md5 = hashlib.md5(self.file_bytes).hexdigest()
        sha256 = hashlib.sha256(self.file_bytes).hexdigest()
        entropy = self.calculate_entropy()
        fmt = self.identify_format()
        strings_extracted = self.extract_strings(min_len=4, max_strings=200)
        indicators = self.analyze_indicators(strings_extracted)
        risk_level, risk_details = self.assess_risk_level(indicators, entropy)
        python_disasm = self.disassemble_if_python()

        report_lines = [
            f"# Reporte de Ingeniería Inversa (REA): `{self.target_path.name}`",
            "",
            "## 1. Metadatos del Archivo",
            f"* **Formato detectado:** {fmt}",
            f"* **Tamaño:** {file_size:,} bytes",
            f"* **Entropía de Shannon:** {entropy} / 8.000 {'(Alta - Posible empaquetamiento)' if entropy > 7.2 else '(Normal)'}",
            f"* **MD5:** `{md5}`",
            f"* **SHA256:** `{sha256}`",
            "",
            "## 2. Nivel de Riesgo y Comportamiento",
            f"* **Evaluación:** **[{risk_level}]**",
            f"* **Justificación:** {risk_details}",
            "",
            "## 3. Indicadores Sospechosos Encontrados",
        ]

        for cat, items in indicators.items():
            cat_name = cat.replace("_", " ").title()
            if items:
                report_lines.append(f"* **{cat_name}:** `{', '.join(items[:8])}`")
            else:
                report_lines.append(f"* **{cat_name}:** Ninguno detectado.")

        report_lines.extend([
            "",
            f"## 4. Cadenas de Texto Relevantes ({len(strings_extracted)} extraídas)",
            "```text"
        ])
        for s in strings_extracted[:25]:
            report_lines.append(s)
        if len(strings_extracted) > 25:
            report_lines.append(f"... (+ {len(strings_extracted) - 25} cadenas adicionales)")
        report_lines.append("```")

        if python_disasm:
            report_lines.extend([
                "",
                "## 5. Desensamblado de Bytecode (Muestra inicial)",
                "```text",
                python_disasm[:1200],
                "```"
            ])

        return "\n".join(report_lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="REA - Reverse Engineering Assistant")
    parser.add_argument("target", help="Ruta al archivo binario o script a inspeccionar")
    parser.add_argument("--output", help="Ruta donde guardar el reporte Markdown (opcional)")
    args = parser.parse_args()

    assistant = ReverseEngineeringAssistant(args.target)
    report = assistant.generate_report()

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"[OK] Reporte guardado en: {args.output}")
    else:
        print(report)
