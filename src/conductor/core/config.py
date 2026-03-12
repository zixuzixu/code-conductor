"""Configuration management for Code Conductor."""

import os
from pathlib import Path

import yaml

from conductor.core.constants import CONDUCTOR_HOME, CONFIG_FILE, MEMORY_FILE, SESSIONS_DIR
from conductor.core.models import ConductorConfig

DEFAULT_CONFIG_YAML = """\
# Code Conductor Configuration
# API keys: set GEMINI_API_KEY and KIMI_API_KEY environment variables.
# The api_key fields below are fallbacks if env vars are not set.

primary_llm:
  provider: gemini
  model: gemini-3.1-pro-preview
  api_key: ""
  max_tokens: 8192
  temperature: 0.7

fallback_llm:
  provider: kimi
  model: kimi-k2.5
  api_key: ""
  base_url: https://api.moonshot.cn/v1
  max_tokens: 8192
  temperature: 0.7

project_dirs: []
max_workers_per_session: 3
backup_retention_hours: 168
server_port: 9130  # or set CONDUCTOR_PORT env var (takes precedence)
"""

DEFAULT_MEMORY_MD = """\
# Memory

User preferences and facts are stored here.
"""


def init_conductor_home() -> Path:
    """Initialize ~/.code-conductor/ directory structure on first run.

    Creates the home directory, default config.yaml, MEMORY.md, and sessions/ dir
    if they don't exist. Idempotent — safe to call multiple times.

    Returns the home directory path.
    """
    CONDUCTOR_HOME.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)

    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG_YAML)

    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text(DEFAULT_MEMORY_MD)

    return CONDUCTOR_HOME


def load_config() -> ConductorConfig:
    """Load configuration from config.yaml.

    Environment variable overrides:
      CONDUCTOR_PORT — overrides server_port from config file.
    """
    if not CONFIG_FILE.exists():
        config = ConductorConfig()
    else:
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f) or {}
        config = ConductorConfig(**data)

    # Env var takes precedence over config file
    env_port = os.environ.get("CONDUCTOR_PORT")
    if env_port is not None:
        config.server_port = int(env_port)

    return config


def save_config(config: ConductorConfig) -> None:
    """Save configuration to config.yaml."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
