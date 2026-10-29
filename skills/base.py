from typing import Dict, Any, Callable

class SkillRegistry:
    """
    Registro central de herramientas (Skills) para MMAE.
    """
    def __init__(self):
        self.skills: Dict[str, Callable] = {}
        self.schemas: Dict[str, str] = {}

    def register(self, name: str, description: str):
        def decorator(func: Callable):
            self.skills[name] = func
            self.schemas[name] = description
            return func
        return decorator

    def execute(self, name: str, **kwargs) -> Any:
        if name not in self.skills:
            raise ValueError(f"Skill '{name}' no encontrada en el registro.")
        return self.skills[name](**kwargs)

    def get_descriptions(self) -> str:
        return "\n".join([f"- {name}: {desc}" for name, desc in self.schemas.items()])
