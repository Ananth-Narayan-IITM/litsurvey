"""Run history: ~/.litsurvey/history.jsonl (index) and ~/.litsurvey/runs/<id>.json."""
import json
import os
import re
import secrets
import time

from .config import DATA_DIR, ensure_data_dir, write_private

INDEX = os.path.join(DATA_DIR, "history.jsonl")
RUNS = os.path.join(DATA_DIR, "runs")


RUN_ID = re.compile(r"^\d{8}-\d{6}(-[0-9a-f]{4,12})?-[a-z]+$")


def _run_path(run_id):
    """The file for a run id. Ids are checked against the format new_id() makes,
    so an id such as "../../.ssh/id_rsa" can never name a file outside RUNS."""
    if not RUN_ID.match(run_id or ""):
        raise FileNotFoundError(f"no such run: {run_id!r}")
    return os.path.join(RUNS, run_id + ".json")


def new_id(mode):
    """Time, a short random part, and the mode. The random part matters: the web
    page runs jobs in threads, and two runs in the same second would otherwise
    get the same id and the second would overwrite the first."""
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}-{mode}"


def record(mode, inputs, papers=None, report=None, log=None, out_file=None,
           stats=None, run_id=None):
    """Save one run. Returns the run id."""
    if os.path.dirname(RUNS) == DATA_DIR:     # tests point RUNS elsewhere
        ensure_data_dir()
    os.makedirs(RUNS, mode=0o700, exist_ok=True)
    if not run_id:
        run_id = new_id(mode)
        while os.path.exists(os.path.join(RUNS, run_id + ".json")):   # never overwrite a run
            run_id = new_id(mode)
    entry = {"id": run_id, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": mode,
             "inputs": inputs, "n_results": len(papers) if papers is not None else None,
             "out_file": out_file or "", "has_report": bool(report)}
    agent = os.environ.get("LITSURVEY_AGENT")
    if agent:                  # made by a subscription agent, not typed by the user
        entry["agent"] = agent
    write_private(os.path.join(RUNS, run_id + ".json"),
                  json.dumps({**entry, "papers": papers, "report": report, "log": log,
                              "stats": stats}, indent=1, ensure_ascii=False))
    fd = os.open(INDEX, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)          # an index from an older version may be 644
    except (OSError, AttributeError):  # AttributeError: Windows has no fchmod
        pass
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return run_id


def list_runs(limit=50):
    if not os.path.exists(INDEX):
        return []
    with open(INDEX, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return list(reversed(rows))[:limit]


def load(run_id):
    path = _run_path(run_id)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def delete(run_id):
    path = _run_path(run_id)
    if os.path.exists(path):
        os.remove(path)
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            rows = [line for line in f if line.strip() and json.loads(line)["id"] != run_id]
        with open(INDEX, "w", encoding="utf-8") as f:
            f.writelines(rows)


def runs_since(epoch):
    """Index entries recorded at or after the given time.time() value, oldest first."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))
    return [r for r in reversed(list_runs(limit=100000)) if r["time"] >= stamp]
