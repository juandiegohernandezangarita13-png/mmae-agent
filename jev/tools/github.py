"""
Herramientas de integración con GitHub y asimilación de repositorios para JEV.
Permite buscar repositorios de código abierto, inspeccionar su código, clonarlos
y asimilar nuevas capacidades para automejora continua.
"""
from typing import Dict, Any, List, Optional
import subprocess
import shutil
import base64
import sys
from pathlib import Path
import httpx

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class GitHubSearchReposTool(BaseTool):
    """Busca repositorios de código abierto en GitHub."""
    name = "search_github_repos"
    description = (
        "Busca repositorios de código abierto en GitHub por palabras clave, temas o algoritmos. "
        "Devuelve los repositorios más populares con estrellas, descripción, URL y lenguajes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Término de búsqueda (ej: 'fast python web scraper', 'local llm agent tools', 'screen ocr')."
            },
            "sort": {
                "type": "string",
                "enum": ["stars", "forks", "updated"],
                "description": "Criterio de ordenación (por defecto 'stars')."
            },
            "max_results": {
                "type": "integer",
                "description": "Número máximo de repositorios a devolver (por defecto 5)."
            }
        },
        "required": ["query"]
    }

    def execute(self, query: str, sort: str = "stars", max_results: int = 5, **kwargs) -> ToolResult:
        try:
            url = f"https://api.github.com/search/repositories?q={query}&sort={sort}&per_page={max_results}"
            headers = {
                "User-Agent": "JEV-Autonomous-Agent/1.0",
                "Accept": "application/vnd.github.v3+json"
            }
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code != 200:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Error en la API de GitHub ({res.status_code}): {res.text[:200]}"
                    )
                data = res.json()

            items = data.get("items", [])
            if not items:
                return ToolResult(
                    success=True,
                    output=f"No se encontraron repositorios en GitHub para la consulta: '{query}'."
                )

            lines = [f"Resultados de GitHub para '{query}' (Total encontrados: {data.get('total_count', len(items))}):\n"]
            repo_list = []
            for i, repo in enumerate(items[:max_results], 1):
                full_name = repo.get("full_name")
                desc = repo.get("description") or "Sin descripción"
                stars = repo.get("stargazers_count", 0)
                lang = repo.get("language") or "Desconocido"
                clone_url = repo.get("clone_url")
                html_url = repo.get("html_url")

                lines.append(
                    f"{i}. [Stars: {stars}] {full_name} ({lang})\n"
                    f"   Descripción: {desc}\n"
                    f"   URL: {html_url}\n"
                    f"   Clone: {clone_url}\n"
                )
                repo_list.append({
                    "full_name": full_name,
                    "stars": stars,
                    "language": lang,
                    "clone_url": clone_url,
                    "html_url": html_url
                })

            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"repos": repo_list}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error buscando repositorios en GitHub: {str(e)}"
            )


class GitHubRepoInspectTool(BaseTool):
    """Inspecciona el README y la estructura de un repositorio de GitHub."""
    name = "inspect_github_repo"
    description = (
        "Obtiene el README.md y metadatos de un repositorio de GitHub dado su nombre completo 'owner/repo' "
        "(ej: 'facebookresearch/llama', 'psf/requests')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "repo_full_name": {
                "type": "string",
                "description": "Nombre completo del repositorio en formato 'propietario/repositorio'."
            }
        },
        "required": ["repo_full_name"]
    }

    def execute(self, repo_full_name: str, **kwargs) -> ToolResult:
        try:
            repo_full_name = repo_full_name.strip().replace("https://github.com/", "")
            headers = {
                "User-Agent": "JEV-Autonomous-Agent/1.0",
                "Accept": "application/vnd.github.v3+json"
            }
            url_readme = f"https://api.github.com/repos/{repo_full_name}/readme"

            with httpx.Client(timeout=15.0) as client:
                res = client.get(url_readme, headers=headers)
                if res.status_code != 200:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"No se pudo obtener el README de '{repo_full_name}' (Status {res.status_code})."
                    )
                readme_data = res.json()

            content_b64 = readme_data.get("content", "")
            readme_text = base64.b64decode(content_b64).decode("utf-8", errors="replace")

            # Truncar si es muy largo
            preview = readme_text[:4000]
            truncated = f"\n\n[... Truncado. Mostrando 4000 de {len(readme_text)} caracteres ...]" if len(readme_text) > 4000 else ""

            return ToolResult(
                success=True,
                output=f"--- README de {repo_full_name} ---\n\n{preview}{truncated}",
                data={"repo": repo_full_name, "length": len(readme_text)}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error inspeccionando repositorio {repo_full_name}: {str(e)}"
            )


class GitHubCloneRepoTool(BaseTool):
    """Clona un repositorio de GitHub en el espacio de trabajo local."""
    name = "clone_github_repo"
    description = (
        "Clona un repositorio de GitHub en workspace/repos/ para inspeccionar "
        "sus scripts y algoritmos. Puede recibir la URL completa (ej: 'https://github.com/alirezamika/autoscraper.git') "
        "o simplemente el nombre 'owner/repo' (ej: 'alirezamika/autoscraper')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "clone_url": {
                "type": "string",
                "description": "URL de clonación (https://...) o nombre del repositorio ('owner/repo')."
            },
            "dest_folder": {
                "type": "string",
                "description": "Nombre de la carpeta de destino dentro de workspace/repos/ (opcional)."
            }
        },
        "required": ["clone_url"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, clone_url: str, dest_folder: Optional[str] = None, **kwargs) -> ToolResult:
        try:
            target_url = clone_url.strip()
            # Si sólo proporcionaron owner/repo, convertir a URL https de git
            if not target_url.startswith("http://") and not target_url.startswith("https://") and "/" in target_url:
                target_url = f"https://github.com/{target_url.strip('/')}.git"

            repos_dir = self.workspace_dir / "repos"
            repos_dir.mkdir(parents=True, exist_ok=True)

            if not dest_folder:
                dest_name = target_url.rstrip("/").split("/")[-1]
                if dest_name.endswith(".git"):
                    dest_name = dest_name[:-4]
            else:
                dest_name = dest_folder

            target_path = repos_dir / dest_name
            if target_path.exists():
                return ToolResult(
                    success=True,
                    output=f"El repositorio ya existe en: {target_path}",
                    data={"path": str(target_path)}
                )

            # Ejecutar git clone --depth 1
            cmd = ["git", "clone", "--depth", "1", target_url, str(target_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Fallo en git clone para '{target_url}': {proc.stderr}"
                )

            return ToolResult(
                success=True,
                output=f"Repositorio clonado exitosamente en: {target_path}",
                data={"path": str(target_path)}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error clonando repositorio {clone_url}: {str(e)}"
            )


class GitHubSkillAssimilatorTool(BaseTool):
    """Asimila un repositorio de GitHub analizando su estructura y preparando su integración."""
    name = "assimilate_github_library"
    description = (
        "Clona un repositorio de GitHub en workspace/repos/, analiza su estructura, "
        "localiza su documentación, archivos de entrada y opcionalmente instala sus dependencias en el entorno virtual."
    )
    parameters = {
        "type": "object",
        "properties": {
            "repo_identifier": {
                "type": "string",
                "description": "Nombre del repositorio (ej: 'psf/requests') o URL completa de GitHub."
            },
            "install_dependencies": {
                "type": "boolean",
                "description": "Si es True, instala sus requerimientos si existe 'requirements.txt' o 'setup.py' (por defecto True)."
            }
        },
        "required": ["repo_identifier"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, repo_identifier: str, install_dependencies: bool = True, **kwargs) -> ToolResult:
        try:
            # 1. Clonar el repositorio
            clone_tool = GitHubCloneRepoTool(self.workspace_dir)
            clone_res = clone_tool.execute(clone_url=repo_identifier)
            if not clone_res.success:
                return clone_res

            repo_path = Path(clone_res.data["path"])

            # 2. Analizar estructura de archivos
            python_files = list(repo_path.glob("**/*.py"))[:15]
            has_requirements = (repo_path / "requirements.txt").exists()
            has_setup = (repo_path / "setup.py").exists() or (repo_path / "pyproject.toml").exists()

            install_summary = "No se requirió instalación de paquetes externos."
            if install_dependencies and has_requirements:
                req_file = repo_path / "requirements.txt"
                proc = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)], capture_output=True, text=True, timeout=120)
                if proc.returncode == 0:
                    install_summary = "Dependencias de requirements.txt instaladas exitosamente en .venv."
                else:
                    install_summary = f"Advertencia al instalar requirements.txt: {proc.stderr[:200]}"

            file_list = [f.name for f in python_files[:10]]
            output_msg = (
                f"✓ Repositorio '{repo_identifier}' asimilado con éxito en: {repo_path}\n"
                f"• Módulos Python identificados ({len(python_files)}): {', '.join(file_list)}\n"
                f"• Estado de dependencias: {install_summary}\n"
                f"• Próximo paso recomendado: Utiliza 'read_file' para inspeccionar los algoritmos o 'create_custom_tool' para envolverlo en una herramienta permanente."
            )

            return ToolResult(
                success=True,
                output=output_msg,
                data={"repo_path": str(repo_path), "python_files_count": len(python_files)}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error asimilando repositorio de GitHub: {str(e)}"
            )
