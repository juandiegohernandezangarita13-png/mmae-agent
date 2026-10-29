"""
Sistema Modular de Habilidades (Skill Factory & Registry) para JEV.
Permite descubrir, validar, compilar y ejecutar habilidades dinámicas y tipadas en disco.
"""
from jev.skills.manager import SkillRegistry, SkillFactory, Skill, SkillMetadata

__all__ = ["SkillRegistry", "SkillFactory", "Skill", "SkillMetadata"]
