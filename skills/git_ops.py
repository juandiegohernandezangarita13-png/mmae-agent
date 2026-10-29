import subprocess
from typing import Dict, Any

class GitOperationsSkill:
    """
    Herramienta de control de versiones Git para seguimiento de cambios del agente.
    """
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def _run_git(self, args: list) -> Dict[str, Any]:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=15
            )
            return {
                "success": res.returncode == 0,
                "output": res.stdout.strip() if res.returncode == 0 else res.stderr.strip()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def status(self) -> Dict[str, Any]:
        return self._run_git(["status", "--short"])

    def diff(self) -> Dict[str, Any]:
        return self._run_git(["diff"])

    def commit_changes(self, message: str) -> Dict[str, Any]:
        add_res = self._run_git(["add", "."])
        if not add_res["success"]:
            return add_res
        return self._run_git(["commit", "-m", message])
