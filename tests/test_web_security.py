"""The local web server must answer only the page it served itself."""
import http.client
import json
import os
import stat
import threading

import pytest

from litsurvey import agent, backends, config, history, ops, web


@pytest.fixture
def server(monkeypatch):
    started = []
    monkeypatch.setattr(web, "_start_job", lambda mode, params: started.append((mode, params)) or "job1")
    srv = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], started
    srv.shutdown()
    srv.server_close()


def call(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    hdrs.update(headers or {})
    conn.request(method, path, body=body, headers=hdrs)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data


JOB = json.dumps({"mode": "oa", "text": "10.1038/nature14539", "out": "/tmp/victim/.bashrc"})


def test_the_page_itself_is_served_and_can_start_jobs(server):
    port, started = server
    assert call(port, "GET", "/")[0] == 200
    status, _ = call(port, "POST", "/api/jobs", JOB, {"Content-Type": "application/json",
                                                       "Origin": f"http://127.0.0.1:{port}"})
    assert status == 200 and started[0][0] == "oa"
    assert "out" not in started[0][1]        # the web API never takes a file path


def test_localhost_and_ipv6_names_are_accepted(server):
    port, _ = server
    for host in (f"localhost:{port}", f"[::1]:{port}"):
        assert call(port, "GET", "/api/history", headers={"Host": host})[0] == 200


def test_cross_site_simple_post_is_refused(server):
    port, started = server
    status, _ = call(port, "POST", "/api/jobs", JOB, {"Content-Type": "text/plain",
                                                       "Origin": "https://evil.example"})
    assert status == 403 and not started


def test_text_plain_post_is_refused_even_without_origin(server):
    port, started = server
    status, _ = call(port, "POST", "/api/jobs", JOB, {"Content-Type": "text/plain"})
    assert status == 415 and not started


def test_dns_rebinding_cannot_read_history(server):
    port, _ = server
    for path in ("/api/history", "/api/run/x", "/api/config", "/"):
        assert call(port, "GET", path, headers={"Host": f"evil.example:{port}"})[0] == 403


def test_cross_site_fetch_metadata_is_refused(server):
    port, _ = server
    assert call(port, "GET", "/api/history", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert call(port, "DELETE", "/api/run/x", headers={"Origin": "https://evil.example"})[0] == 403


def test_oversized_body_is_refused(server):
    port, started = server
    status, _ = call(port, "POST", "/api/jobs", "x" * 10,
                     {"Content-Type": "application/json", "Content-Length": str(web.MAX_BODY + 1)})
    assert status == 413 and not started


@pytest.mark.parametrize("url,local", [
    ("http://localhost:1234", True), ("http://127.0.0.1:8080/v1", True), ("http://[::1]:1234", True),
    ("localhost:1234", True), ("http://127.5.5.5", True),
    ("https://localhost.evil.com", False), ("https://api.evil.com/?x=127.0.0.1", False),
    ("https://openrouter.ai/api", False), ("", False)])
def test_loopback_is_decided_by_the_parsed_host(url, local):
    assert backends.is_loopback_url(url) is local


def test_history_files_are_private(monkeypatch, tmp_path):
    runs = tmp_path / "runs"
    monkeypatch.setattr(history, "RUNS", str(runs))
    monkeypatch.setattr(history, "INDEX", str(tmp_path / "history.jsonl"))
    rid = history.record("novelty", {"text": "an unpublished claim"}, report="r")
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(runs / (rid + ".json")).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(tmp_path / "history.jsonl").st_mode) == 0o600
        assert stat.S_IMODE(os.stat(runs).st_mode) == 0o700


def test_data_dir_is_tightened(monkeypatch, tmp_path):
    d = tmp_path / "data"
    d.mkdir(mode=0o755)
    monkeypatch.setattr(config, "DATA_DIR", str(d))
    config.ensure_data_dir()
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(d).st_mode) == 0o700


def test_a_query_repeating_the_input_is_refused(monkeypatch):
    claim = ("we show that adaptive resampling of collocation points guided by the residual "
             "reduces the error of physics informed networks on stiff problems")
    monkeypatch.setattr(agent, "run_search", lambda *a, **k: pytest.fail("must not search"))
    log = []
    out = agent.dispatch("search_papers", {"query": "adaptive resampling of collocation points guided by the residual"},
                         log, guard_text=claim)
    assert "Refused" in out["error"] and log[0]["error"].startswith("refused")


def test_a_generic_query_still_runs(monkeypatch):
    claim = "adaptive resampling of collocation points for physics informed networks"
    monkeypatch.setattr(agent, "run_search", lambda *a, **k: ([], {"openalex": 0}))
    assert agent.dispatch("search_papers", {"query": "residual adaptive collocation PINN"}, [],
                          guard_text=claim) == []


def test_tool_results_reach_the_model_marked_as_data(monkeypatch):
    seen = []
    replies = iter([{"content": "", "tool_calls": [{"id": "1", "name": "search_papers",
                                                    "args": {"query": "kan"}}]},
                    {"content": "report", "tool_calls": []}])

    def fake_chat(backend, model, messages, tools=None, options=None):
        seen.append(list(messages))
        return next(replies)
    monkeypatch.setattr(backends, "resolve", lambda *a: ("ollama", "m"))
    monkeypatch.setattr(backends, "chat", fake_chat)
    monkeypatch.setattr(agent, "run_search", lambda *a, **k: ([], {}))
    agent.run("novelty", "a claim", progress=lambda s: None)
    tool_msg = [m for m in seen[-1] if m["role"] == "tool"][0]
    assert tool_msg["content"].startswith("<search_results>") and tool_msg["content"].endswith("</search_results>")
    assert "UNTRUSTED DATA RULE" in seen[0][0]["content"]


def test_claude_has_only_the_shell_and_codex_reads_stdin(monkeypatch):
    monkeypatch.setattr(backends, "_HELP_CACHE", {"claude": "", "codex": ""})
    monkeypatch.setattr(backends.shutil, "which", lambda t: "/usr/bin/" + t)
    claude = backends.cli_command("claude")[0]
    assert claude[claude.index("--tools") + 1] == "Bash"
    codex, use_stdin = backends.cli_command("codex")
    assert use_stdin is True and codex[-1] == "-" and "{prompt}" not in codex


@pytest.mark.parametrize("bad", ["../../outside", "..", "20261010-112402-oa/../../x", "", "a b"])
def test_run_ids_cannot_name_other_files(monkeypatch, tmp_path, bad):
    monkeypatch.setattr(history, "RUNS", str(tmp_path / "runs"))
    (tmp_path / "outside.json").write_text('{"secret": 1}')
    with pytest.raises(FileNotFoundError):
        history.load(bad)
    with pytest.raises(FileNotFoundError):
        history.delete(bad)
    assert (tmp_path / "outside.json").exists()


def test_real_run_ids_still_load(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "RUNS", str(tmp_path / "runs"))
    monkeypatch.setattr(history, "INDEX", str(tmp_path / "history.jsonl"))
    rid = history.record("search", {"text": "x"}, papers=[])
    assert history.load(rid)["id"] == rid
    assert history.RUN_ID.match("20260907-102335-search")      # ids written by 1.0/1.1


@pytest.mark.parametrize("argv,refused", [
    (["history", "show", "../../x"], True), (["init"], True), (["web"], True),
    (["novelty", "a claim"], True), (["search", "kan", "--out", "/tmp/x.bib"], True),
    (["search", "kan", "--json"], False), (["cites", "DOI:10.1/x"], False)])
def test_an_agent_gets_only_the_lookups(monkeypatch, argv, refused):
    from litsurvey import cli
    monkeypatch.setenv(cli.AGENT_ENV, "1")
    args = cli.build_parser().parse_args(argv)
    assert (cli._agent_refusal(args) is not None) is refused


def test_without_the_agent_flag_nothing_is_refused(monkeypatch):
    from litsurvey import cli
    monkeypatch.delenv(cli.AGENT_ENV, raising=False)
    assert cli._agent_refusal(cli.build_parser().parse_args(["history", "list"])) is None


def test_run_cli_marks_the_agent_environment(monkeypatch):
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, "report", ""

    def fake_run(argv, **kw):
        seen["env"] = kw["env"]
        return Proc()
    monkeypatch.setattr(backends, "cli_command", lambda tool: (["x", "{prompt}"], False))
    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    backends.run_cli("x", "task")
    assert seen["env"]["LITSURVEY_AGENT"] == "1"


def test_claude_may_run_only_the_search_commands(monkeypatch):
    monkeypatch.setattr(backends, "_HELP_CACHE", {"claude": ""})
    monkeypatch.setattr(backends.shutil, "which", lambda t: "/usr/bin/" + t)
    argv = backends.cli_command("claude")[0]
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert allowed == [f"Bash(litsurvey {c}:*)" for c in ("search", "paper", "cites", "refs", "related")]


def test_existing_index_is_tightened_on_append(monkeypatch, tmp_path):
    idx = tmp_path / "history.jsonl"
    idx.write_text("")
    os.chmod(idx, 0o644)
    monkeypatch.setattr(history, "RUNS", str(tmp_path / "runs"))
    monkeypatch.setattr(history, "INDEX", str(idx))
    history.record("search", {"text": "x"}, papers=[])
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(idx).st_mode) == 0o600


def test_an_existing_data_dir_is_tightened_at_start(monkeypatch, tmp_path):
    d = tmp_path / "data"
    d.mkdir(mode=0o755)
    monkeypatch.setattr(config, "DATA_DIR", str(d))
    config.tighten_data_dir()
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(d).st_mode) == 0o700


def test_port_80_accepts_the_portless_host():
    class Fake(web.Handler):
        def __init__(self):
            pass
    h = Fake()
    h.server = type("S", (), {"server_address": ("127.0.0.1", 80)})()
    assert "127.0.0.1" in h._local_names() and "localhost:80" in h._local_names()
    h.server = type("S", (), {"server_address": ("127.0.0.1", 8765)})()
    assert "127.0.0.1" not in h._local_names()
