"""Load versioned prompt YAML files from disk.

Layout:
    prompts/<name>.yaml             # current version, single file per prompt
    prompts/<name>/v3.yaml          # OR multiple historical versions in a dir

Why YAML, not Python: prompts must be reviewable in PRs by non-engineers, and
versioning belongs in source control rather than a database. Each file declares
its own version; the manager simply loads it.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from string import Template
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Prompt(BaseModel):
    """A single resolved prompt template plus the metadata needed to reproduce it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    system: str
    user_template: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=512, ge=1, le=8192)
    description: str | None = None

    def render_user(self, variables: dict[str, Any]) -> str:
        """Substitute `${var}` placeholders. Missing keys raise KeyError loudly —
        we'd rather fail the eval run than silently emit a malformed prompt.
        """
        return Template(self.user_template).substitute(variables)

    def fingerprint(self) -> str:
        """Stable short hash. Useful for cache keys and report headers."""
        payload = f"{self.name}|{self.version}|{self.system}|{self.user_template}|{self.temperature}|{self.max_output_tokens}"
        return sha256(payload.encode()).hexdigest()[:12]


class PromptManager:
    """Resolves a (name, version) pair to a Prompt by scanning a directory."""

    def __init__(self, root: Path):
        if not root.exists():
            raise FileNotFoundError(f"Prompts directory does not exist: {root}")
        self._root = root

    def load(self, name: str, version: str | None = None) -> Prompt:
        """Load a prompt. If version is None, returns the highest version found.

        Search order:
            1. <root>/<name>.yaml                      (single-file prompt)
            2. <root>/<name>/<version>.yaml            (versioned directory)
            3. <root>/<name>/latest.yaml or highest-numbered if version is None
        """
        single_file = self._root / f"{name}.yaml"
        if single_file.exists():
            data = _read_yaml(single_file)
            return _to_prompt(name, data, default_version=version)

        prompt_dir = self._root / name
        if not prompt_dir.is_dir():
            raise FileNotFoundError(f"No prompt named '{name}' found under {self._root}")

        if version is None:
            candidates = sorted(prompt_dir.glob("v*.yaml"))
            if not candidates:
                raise FileNotFoundError(
                    f"Prompt '{name}' directory exists but contains no v*.yaml files"
                )
            target = candidates[-1]
        else:
            target = prompt_dir / f"{version}.yaml"
            if not target.exists():
                raise FileNotFoundError(
                    f"Prompt '{name}' has no version '{version}' (looked at {target})"
                )

        data = _read_yaml(target)
        data.setdefault("version", target.stem)
        return _to_prompt(name, data, default_version=version)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"Prompt file {path} must contain a YAML mapping at the top level")
    return loaded


def _to_prompt(name: str, data: dict[str, Any], default_version: str | None) -> Prompt:
    return Prompt(
        name=name,
        version=str(data.get("version", default_version or "v1")),
        system=str(data["system"]).strip(),
        user_template=str(data["user_template"]).strip(),
        temperature=float(data.get("temperature", 0.0)),
        max_output_tokens=int(data.get("max_output_tokens", 512)),
        description=data.get("description"),
    )
