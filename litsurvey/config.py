"""Configuration: ~/.litsurvey/config.json, with environment variable overrides.

Keys (all optional):
  s2_api_key        Semantic Scholar API key (1 request/second dedicated)
  openalex_mailto   your email; gives OpenAlex's polite pool, also used by Unpaywall
  backend           default LLM backend: ollama | openai | anthropic
  model             default model name for the backend
  ollama_host       default http://localhost:11434
  openai_base_url   default https://api.openai.com (LM Studio: http://localhost:1234)
  openai_api_key
  anthropic_api_key
  cli_tool          subscription CLI for the "cli" backend: claude | codex | agy | gemini | custom
  cli_command       custom command line for cli_tool=custom; {prompt} placeholder or prompt on stdin
  cli_model         model the subscription CLI should use; "-" means the tool's own default
  cli_effort        reasoning effort for the subscription CLI; "-" means the tool's own default
  update_check      "false" stops the web page asking pypi.org (once a day) for the latest version
  agent_timeout     minutes a novelty/research run may take (default 30; 0 = no limit)
"""
import json
import os

DATA_DIR = os.path.join(os.path.expanduser("~"), ".litsurvey")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LEGACY_PATH = os.path.expanduser("~/.litsearch.json")

ENV_MAP = {
    "s2_api_key": ("LITSURVEY_S2_API_KEY", "S2_API_KEY"),
    "openalex_mailto": ("LITSURVEY_MAILTO", "OPENALEX_MAILTO"),
    "backend": ("LITSURVEY_BACKEND",),
    "model": ("LITSURVEY_MODEL",),
    "ollama_host": ("OLLAMA_HOST",),
    "openai_base_url": ("OPENAI_BASE_URL",),
    "openai_api_key": ("OPENAI_API_KEY",),
    "anthropic_api_key": ("ANTHROPIC_API_KEY",),
    "cli_tool": ("LITSURVEY_CLI_TOOL",),
    "cli_command": ("LITSURVEY_CLI_COMMAND",),
    "cli_model": ("LITSURVEY_CLI_MODEL",),
    "cli_effort": ("LITSURVEY_CLI_EFFORT",),
    "update_check": ("LITSURVEY_UPDATE_CHECK",),
    "agent_timeout": ("LITSURVEY_AGENT_TIMEOUT",),
}

DEFAULTS = {
    "s2_api_key": "",
    "openalex_mailto": "",
    "backend": "",
    "model": "",
    "ollama_host": "http://localhost:11434",
    "openai_base_url": "https://api.openai.com",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "cli_tool": "",
    "cli_command": "",
    "cli_model": "",
    "cli_effort": "",
    "update_check": "",
    "agent_timeout": "",
}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        import sys
        print(f"[warn] could not read {path}: {e}", file=sys.stderr)
        return {}


def load():
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in _read_json(LEGACY_PATH).items() if k in DEFAULTS})
    cfg.update({k: v for k, v in _read_json(CONFIG_PATH).items() if k in DEFAULTS})
    for key, envs in ENV_MAP.items():
        for env in envs:
            val = os.environ.get(env)
            if val:
                cfg[key] = val
                break
    # a placeholder left in the file must not be sent as a key
    if "PASTE" in (cfg.get("s2_api_key") or "").upper():
        cfg["s2_api_key"] = ""
    # normalise host URLs
    for k in ("ollama_host", "openai_base_url"):
        v = cfg.get(k) or DEFAULTS[k]
        if not v.startswith("http"):
            v = "http://" + v
        cfg[k] = v.rstrip("/")
    return cfg


def ensure_data_dir():
    """Create ~/.litsurvey readable by its owner only, and tighten an existing one.
    It holds the config and every past run: the text of novelty claims and
    research questions, which other accounts on a shared machine should not read."""
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    return DATA_DIR


def tighten_data_dir():
    """Make an existing ~/.litsurvey owner-only. Called at start-up, so an install
    from before 1.1.1 is fixed even if the user only reads the history."""
    if os.path.isdir(DATA_DIR):
        try:
            os.chmod(DATA_DIR, 0o700)
        except OSError:
            pass


def write_private(path, text):
    """Write a file that only its owner can read (mode 600 on POSIX)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(path, 0o600)       # an existing file keeps its old mode otherwise
    except OSError:
        pass


def save(values):
    """Write the given keys to the config file, keeping other existing keys."""
    ensure_data_dir()
    current = _read_json(CONFIG_PATH)
    current.update({k: v for k, v in values.items() if k in DEFAULTS})
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
        f.write("\n")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return CONFIG_PATH


def enabled(value):
    """A config flag that is on unless set to false / 0 / no / off."""
    return str(value).strip().lower() not in ("false", "0", "no", "off")


CFG = load()
