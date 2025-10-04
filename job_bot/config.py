"""Configuration loader for the job automation bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml


@dataclass(slots=True)
class BrowserConfig:
    """Settings that control how Playwright launches the browser."""

    headless: bool = True
    slow_mo: Optional[int] = None
    timeout_ms: int = 10_000
    locale: Optional[str] = None


@dataclass(slots=True)
class StepConfig:
    """A single automation instruction inside a job flow."""

    action: str
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "StepConfig":
        if "action" not in data:
            raise ValueError("Every step must define an 'action' field")
        action = str(data["action"])
        options = {k: v for k, v in data.items() if k != "action"}
        return cls(action=action, options=options)


@dataclass(slots=True)
class JobConfig:
    """Configuration for a single job posting automation run."""

    name: str
    url: str
    steps: List[StepConfig]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "JobConfig":
        if "url" not in data:
            raise ValueError("Each job requires a 'url'")
        name = str(data.get("name") or data["url"])
        url = str(data["url"])
        raw_steps = data.get("steps") or []
        if not isinstance(raw_steps, Iterable):
            raise ValueError("Job 'steps' must be an iterable of step definitions")
        steps = [StepConfig.from_mapping(step) for step in raw_steps]
        metadata = {
            k: v
            for k, v in data.items()
            if k not in {"name", "url", "steps"}
        }
        return cls(name=name, url=url, steps=steps, metadata=metadata)


@dataclass(slots=True)
class AutomationConfig:
    """Top-level configuration file representation."""

    source_path: Path
    profile: Dict[str, Any]
    browser: BrowserConfig
    jobs: List[JobConfig]

    @property
    def base_dir(self) -> Path:
        return self.source_path.parent


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
        if not isinstance(data, Mapping):
            raise ValueError("Configuration root must be a mapping")
        return dict(data)


def _parse_browser_config(data: Mapping[str, Any]) -> BrowserConfig:
    return BrowserConfig(
        headless=bool(data.get("headless", True)),
        slow_mo=data.get("slow_mo"),
        timeout_ms=int(data.get("timeout_ms", 10_000)),
        locale=data.get("locale"),
    )


def load_config(path: Path | str) -> AutomationConfig:
    """Load the YAML configuration into dataclasses."""

    cfg_path = Path(path).expanduser().resolve()
    raw = _load_yaml(cfg_path)

    profile = raw.get("profile") or {}
    if not isinstance(profile, Mapping):
        raise ValueError("'profile' must be a mapping of reusable data")
    profile = dict(profile)

    browser = _parse_browser_config(raw.get("browser") or {})

    raw_jobs = raw.get("jobs") or []
    if not isinstance(raw_jobs, Iterable):
        raise ValueError("'jobs' must be a list of job definitions")
    jobs = [JobConfig.from_mapping(job) for job in raw_jobs]

    if not jobs:
        raise ValueError("No jobs defined in configuration")

    return AutomationConfig(
        source_path=cfg_path,
        profile=profile,
        browser=browser,
        jobs=jobs,
    )


__all__ = [
    "AutomationConfig",
    "BrowserConfig",
    "JobConfig",
    "StepConfig",
    "load_config",
]
