"""Consent and privacy configuration for the production agent."""

from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from collector.windows_collector import normalize_authorized_folders


@dataclass
class AgentConfig:
    authorized_folders: list[str] = field(default_factory=list)
    consent_granted_at: str = ""
    policy_version: str = "1.0"
    collector_version: str = "1.0"
    include_processes: bool = True
    include_keyboard_counts: bool = False
    output_dir: str = "~/.poe/sessions"

    def validate(self) -> None:
        if platform.system() != "Windows":
            raise OSError("The production desktop agent is supported only on Windows.")
        normalize_authorized_folders(self.authorized_folders)
        if not self.consent_granted_at:
            raise ValueError("Explicit consent is required before monitoring.")


def default_config_path() -> Path:
    return Path("~/.poe/agent-config.json").expanduser()


def load_config(path: str | Path | None = None) -> AgentConfig:
    config_path = Path(path or default_config_path()).expanduser()
    if not config_path.exists():
        return AgentConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return AgentConfig(**data)


def save_config(config: AgentConfig, path: str | Path | None = None) -> Path:
    config_path = Path(path or default_config_path()).expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def grant_consent(
    folders: Iterable[str | Path],
    *,
    output_dir: str = "~/.poe/sessions",
    include_processes: bool = True,
    include_keyboard_counts: bool = False,
) -> AgentConfig:
    """Create a consented configuration from folders selected by the user."""
    normalized = normalize_authorized_folders(folders)
    from datetime import datetime, timezone

    return AgentConfig(
        authorized_folders=[str(folder) for folder in normalized],
        consent_granted_at=datetime.now(timezone.utc).isoformat(),
        output_dir=output_dir,
        include_processes=include_processes,
        include_keyboard_counts=include_keyboard_counts,
    )
