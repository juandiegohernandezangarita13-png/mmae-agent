"""
Resolutor de Conflictos y Validación Semántica de Habilidades (Skills).
Garantiza que el agente no cargue simultáneamente habilidades que se contradigan
(ej. múltiples frameworks incompatibles, ORMs rivales o directivas operativas opuestas).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple


class SkillConflictResolver:
    """
    Detecta y resuelve incompatibilidades entre habilidades antes de inyectarlas en el contexto.
    """

    # Dominios mutuamente excluyentes (un solo ganador por tarea a menos que se solicite migración)
    EXCLUSIVE_DOMAINS: Dict[str, List[str]] = {
        "frontend_framework": ["react", "vue", "angular", "svelte", "solid", "nextjs", "nuxt", "remix"],
        "styling_system": ["tailwind", "bootstrap", "sass", "styled-components", "emotion", "vanilla-css"],
        "backend_python": ["fastapi", "django", "flask", "litestar", "tornado"],
        "backend_node": ["express", "nestjs", "fastify", "hono", "koa"],
        "database_orm": ["prisma", "drizzle", "typeorm", "sqlalchemy", "peewee", "tortoise", "diesel"],
        "package_manager": ["uv", "poetry", "pipenv", "pip", "pnpm", "yarn", "npm", "bun", "cargo"],
        "cloud_backend": ["supabase", "firebase", "appwrite", "convex", "neon"],
        "testing_e2e": ["playwright", "cypress", "puppeteer", "selenium"]
    }

    @classmethod
    def assign_domain_and_tags(cls, skill_id: str, name: str, description: str) -> Tuple[str, List[str], Optional[str]]:
        """
        Determina la categoría general, etiquetas y si pertenece a un dominio con potencial conflicto.
        """
        combined = f"{skill_id} {name} {description}".lower()
        tags = set()
        conflict_domain = None

        for domain, members in cls.EXCLUSIVE_DOMAINS.items():
            for member in members:
                pattern = rf"\b{re.escape(member)}\b"
                if re.search(pattern, combined):
                    tags.add(member)
                    conflict_domain = domain

        # Categoría general
        if any(k in combined for k in ("react", "vue", "angular", "frontend", "html", "css", "tailwind", "ui", "ux", "web")):
            category = "Frontend & UI"
        elif any(k in combined for k in ("backend", "api", "database", "sql", "postgres", "fastapi", "django", "server", "orm")):
            category = "Backend & Database"
        elif any(k in combined for k in ("docker", "kubernetes", "cloud", "aws", "gcp", "azure", "ci/cd", "github", "deploy")):
            category = "DevOps & Cloud"
        elif any(k in combined for k in ("security", "audit", "auth", "crypto", "vulnerability", "sentry")):
            category = "Security & Auth"
        elif any(k in combined for k in ("ai", "llm", "embedding", "fine-tuning", "rag", "eval", "agent", "prompt")):
            category = "AI & ML"
        elif any(k in combined for k in ("test", "testing", "playwright", "cypress", "unit", "mock")):
            category = "Testing & QA"
        elif any(k in combined for k in ("cli", "terminal", "script", "windows", "os", "powershell", "bash", "filesystem")):
            category = "OS & Automation"
        else:
            category = "General Engineering"

        return category, sorted(list(tags)), conflict_domain

    @classmethod
    def resolve_conflicts(
        cls,
        candidate_skills: List[Dict[str, Any]],
        context_hint: str = "",
        workspace_tech_stack: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filtra candidatos eliminando habilidades contradictorias basándose en:
        1. Mención explícita en el objetivo/contexto.
        2. Stack detectado en el espacio de trabajo.
        3. Puntuación de relevancia y especificidad.
        """
        if not candidate_skills:
            return []

        context_lower = (context_hint or "").lower()
        workspace_stack = {s.lower() for s in (workspace_tech_stack or set())}

        selected_skills: List[Dict[str, Any]] = []
        claimed_domains: Dict[str, Dict[str, Any]] = {}

        for skill in candidate_skills:
            domain = skill.get("conflict_domain")
            if not domain:
                # Sin conflicto: seguro de incluir
                selected_skills.append(skill)
                continue

            # Si ya tenemos una habilidad en este dominio exclusivo, determinar cuál gana
            if domain in claimed_domains:
                existing = claimed_domains[domain]
                winner = cls._pick_winner(existing, skill, context_lower, workspace_stack)
                if winner == skill:
                    claimed_domains[domain] = skill
            else:
                claimed_domains[domain] = skill

        # Combinar habilidades seleccionadas sin duplicados
        final_list = selected_skills + list(claimed_domains.values())
        return final_list

    @classmethod
    def _pick_winner(
        cls,
        skill_a: Dict[str, Any],
        skill_b: Dict[str, Any],
        context_lower: str,
        workspace_stack: Set[str]
    ) -> Dict[str, Any]:
        """Selecciona la habilidad dominante resolviendo la colisión."""
        score_a = cls._calculate_precedence(skill_a, context_lower, workspace_stack)
        score_b = cls._calculate_precedence(skill_b, context_lower, workspace_stack)

        if score_b > score_a:
            return skill_b
        return skill_a

    @classmethod
    def _calculate_precedence(
        cls,
        skill: Dict[str, Any],
        context_lower: str,
        workspace_stack: Set[str]
    ) -> float:
        score = float(skill.get("rank_score", 1.0))
        skill_tags = skill.get("tags", [])

        for tag in skill_tags:
            tag_lower = tag.lower()
            # Bonificación máxima si el usuario nombró la tecnología en su meta
            if tag_lower in context_lower:
                score += 10.0
            # Bonificación si el repo ya contiene esa tecnología
            if tag_lower in workspace_stack:
                score += 5.0

        return score
