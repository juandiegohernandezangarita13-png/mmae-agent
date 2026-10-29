"""
Gestor del Sistema Modular de Habilidades (Skill Registry & Factory) para JEV.
Provee persistencia en disco, validación estricta, introspección tipada y
puente nativo hacia el ToolRegistry del agente.
"""
from typing import Dict, Any, List, Optional, Callable
import json
import importlib.util
import sys
import unittest
from pathlib import Path
from dataclasses import dataclass, field

from jev.tools.base import BaseTool, ToolResult


@dataclass(slots=True)
class SkillMetadata:
    """Metadatos formales de una habilidad adquirida."""
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    trigger_keywords: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillMetadata":
        return cls(
            name=data.get("name", "unnamed_skill"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            category=data.get("category", "general"),
            trigger_keywords=data.get("trigger_keywords", []),
            dependencies=data.get("dependencies", []),
            parameters=data.get("parameters", {})
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "trigger_keywords": self.trigger_keywords,
            "dependencies": self.dependencies,
            "parameters": self.parameters
        }


class Skill:
    """Representa una habilidad modular empaquetada en disco."""

    def __init__(self, skill_dir: Path, metadata: SkillMetadata, handler_callable: Callable[..., Any]):
        self.skill_dir = skill_dir
        self.metadata = metadata
        self.handler = handler_callable

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    def execute(self, **kwargs) -> Any:
        return self.handler(**kwargs)


class SkillToolAdapter(BaseTool):
    """Adapta dinámicamente un Skill para ser consumido por el ToolRegistry de JEV."""

    def __init__(self, skill: Skill):
        self.skill = skill
        self.name = skill.name
        self.description = f"[SKILL] {skill.description}"

        # Solo son obligatorios los parámetros SIN valor por defecto. Si se marcan
        # todos como requeridos, el ToolRegistry rechaza llamadas válidas en las que
        # el modelo omite argumentos opcionales (p. ej. 'params' de una malla) y la
        # skill se vuelve inutilizable desde el bucle ReAct.
        properties = dict(skill.metadata.parameters or {})
        required = [
            name for name, spec in properties.items()
            if isinstance(spec, dict) and "default" not in spec
        ]
        self.parameters = {
            "type": "object",
            "properties": properties,
            "required": required
        }

    def execute(self, **kwargs) -> ToolResult:
        try:
            res = self.skill.execute(**kwargs)
            if isinstance(res, ToolResult):
                return res
            if isinstance(res, (dict, list)):
                out_str = json.dumps(res, indent=2, ensure_ascii=False)
                return ToolResult(success=True, output=out_str, data=res if isinstance(res, dict) else {"data": res})
            return ToolResult(success=True, output=str(res), data={"result": res})
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error ejecutando habilidad '{self.name}': {str(e)}")


class SkillRegistry:
    """Registro y cargador reflexivo de habilidades persistidas en disco."""

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or (Path(__file__).parent)
        self._skills: Dict[str, Skill] = {}
        self.discover_skills()

    def discover_skills(self) -> None:
        """Escanea el directorio en busca de carpetas con metadata.json y handler.py."""
        self._skills.clear()
        if not self.skills_dir.exists():
            return

        for path in self.skills_dir.iterdir():
            if path.is_dir() and not path.name.startswith(("_", ".")):
                meta_file = path / "metadata.json"
                handler_file = path / "handler.py"
                if meta_file.exists() and handler_file.exists():
                    try:
                        self._load_skill_from_disk(path, meta_file, handler_file)
                    except Exception as e:
                        print(f"[AVISO] Error cargando habilidad en {path.name}: {e}")

    def _load_skill_from_disk(self, skill_dir: Path, meta_file: Path, handler_file: Path) -> None:
        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = SkillMetadata.from_dict(data)

        # Importar dinámicamente handler.py
        module_name = f"jev_skill_{metadata.name}"
        spec = importlib.util.spec_from_file_location(module_name, handler_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)

            # Buscar función de entrada estándar: 'handle', 'execute', o nombrada como la habilidad
            handler_func = getattr(mod, "handle", None) or getattr(mod, "execute", None)
            if not handler_func:
                for attr_name in dir(mod):
                    if attr_name.startswith("skill_") or attr_name == metadata.name:
                        handler_func = getattr(mod, attr_name)
                        break

            if handler_func and callable(handler_func):
                skill = Skill(skill_dir=skill_dir, metadata=metadata, handler_callable=handler_func)
                self._skills[metadata.name] = skill

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        return [s.metadata.to_dict() for s in self._skills.values()]

    def execute_skill(self, name: str, **kwargs) -> Any:
        skill = self._skills.get(name)
        if not skill:
            raise KeyError(f"Habilidad '{name}' no encontrada en el registro.")
        return skill.execute(**kwargs)

    def run_skill_tests(self, name: str) -> bool:
        """Ejecuta los tests unitarios contenidos en tests/ de la habilidad."""
        skill = self._skills.get(name)
        if not skill:
            raise KeyError(f"Habilidad '{name}' no encontrada.")
        tests_dir = skill.skill_dir / "tests"
        if not tests_dir.exists():
            return True

        suite = unittest.TestSuite()
        loader = unittest.TestLoader()

        skill_dir_str = str(skill.skill_dir)
        path_added = False
        if skill_dir_str not in sys.path:
            sys.path.insert(0, skill_dir_str)
            path_added = True

        try:
            for test_file in tests_dir.glob("test_*.py"):
                mod_name = f"test_skill_{name}_{test_file.stem}"
                if mod_name in sys.modules:
                    del sys.modules[mod_name]
                spec = importlib.util.spec_from_file_location(mod_name, test_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    suite.addTests(loader.loadTestsFromModule(mod))

            runner = unittest.TextTestRunner(verbosity=0)
            res = runner.run(suite)
            return res.wasSuccessful()
        finally:
            if path_added and skill_dir_str in sys.path:
                sys.path.remove(skill_dir_str)

    def to_tool_adapters(self) -> List[BaseTool]:
        """Convierte todas las habilidades registradas en herramientas compatibles con AgentCore."""
        return [SkillToolAdapter(skill) for skill in self._skills.values()]


class SkillFactory:
    """Fábrica de compilación y scaffolding de nuevas habilidades modulares."""

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def create_skill(
        self,
        name: str,
        description: str,
        handler_code: str,
        test_code: str,
        category: str = "general",
        version: str = "1.0.0",
        trigger_keywords: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Skill:
        """
        Compila y persiste una nueva habilidad con metadata, handler y tests unitarios.
        Valida que los tests pasen exitosamente antes de registrar la habilidad.
        """
        skill_dir = self.registry.skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = skill_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        metadata = SkillMetadata(
            name=name,
            description=description,
            version=version,
            category=category,
            trigger_keywords=trigger_keywords or [],
            dependencies=dependencies or [],
            parameters=parameters or {}
        )

        # 1. Escribir metadata.json
        with open(skill_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)

        # 2. Escribir handler.py
        with open(skill_dir / "handler.py", "w", encoding="utf-8") as f:
            f.write(handler_code)

        # 3. Escribir tests/test_handler.py
        with open(tests_dir / "test_handler.py", "w", encoding="utf-8") as f:
            f.write(test_code)

        # 4. Cargar en el registro
        self.registry._load_skill_from_disk(
            skill_dir=skill_dir,
            meta_file=skill_dir / "metadata.json",
            handler_file=skill_dir / "handler.py"
        )

        # 5. Ejecutar tests unitarios
        tests_ok = self.registry.run_skill_tests(name)
        if not tests_ok:
            raise RuntimeError(f"Fallo en pruebas unitarias de la nueva habilidad '{name}'.")

        return self.registry.get_skill(name)
