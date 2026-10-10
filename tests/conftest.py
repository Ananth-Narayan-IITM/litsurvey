import pytest

from litsurvey import config, history


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    """Never touch the user's real ~/.litsurvey during tests."""
    monkeypatch.setattr(history, "INDEX", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(history, "RUNS", str(tmp_path / "runs"))
    yield


@pytest.fixture(autouse=True)
def default_config(monkeypatch):
    """Run every test with the built-in defaults, not with whatever the person
    running the tests has in ~/.litsurvey/config.json or the environment. CFG is
    one dict shared by every module, so its keys are reset in place."""
    for key, value in config.DEFAULTS.items():
        monkeypatch.setitem(config.CFG, key, value)
    for envs in config.ENV_MAP.values():
        for env in envs:
            monkeypatch.delenv(env, raising=False)
    monkeypatch.delenv("LITSURVEY_AGENT", raising=False)
    yield
