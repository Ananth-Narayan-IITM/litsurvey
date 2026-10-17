"""Local browser interface: stdlib HTTP server on 127.0.0.1, one HTML page, JSON API."""
import json
import os
import threading
import time
import traceback
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, backends, config, export, history, http, ops, papers

REPO_URL = "https://github.com/udaykdk/litsurvey"

# "Update available" in the page header. The local server, not the page, asks
# PyPI, at most once a day; the answer is cached in ~/.litsurvey. PyPI's JSON
# API can trail a new release by a few minutes, which is harmless here.
UPDATE_URL = "https://pypi.org/pypi/litsurvey/json"
UPDATE_EVERY = 24 * 3600
UPDATE_CACHE = os.path.join(config.DATA_DIR, ".update-check")
_UPDATE_LOCK = threading.Lock()


def version_tuple(v):
    """(1, 10) from "1.10.0": compared as numbers, so 1.10 is newer than 1.9, and
    trailing zeros dropped, so "1.2" equals "1.2.0". A pre-release ("1.2.0rc1")
    or anything unparsable gives None and is ignored."""
    parts = str(v or "").strip().split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    while len(nums) > 1 and nums[-1] == 0:
        nums.pop()
    return tuple(nums)


_UPDATE_MEMO = {}     # this process's last answer, in case the cache file cannot be written


def update_status(now=None):
    """{"enabled", "latest", "update_available"}. Network only when the cached
    answer is older than a day; offline or any error just means no marker."""
    now = now or time.time()
    if not config.enabled(config.load()["update_check"]):
        return {"enabled": False, "latest": None, "update_available": False}
    with _UPDATE_LOCK:
        try:
            with open(UPDATE_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
            float(cache.get("checked") or 0)           # a damaged file is treated as absent
            if not isinstance(cache.get("latest") or "", str):
                raise ValueError
        except (OSError, ValueError, TypeError, AttributeError):
            cache = {}
        if float(_UPDATE_MEMO.get("checked") or 0) > float(cache.get("checked") or 0):
            cache = dict(_UPDATE_MEMO)
        if now - float(cache.get("checked") or 0) > UPDATE_EVERY:
            try:
                data = json.loads(http.get(UPDATE_URL, timeout=5, retries=1).decode("utf-8"))
                cache = {"checked": now, "latest": data["info"]["version"]}
            except Exception:  # noqa: BLE001 - offline, PyPI down: try again tomorrow
                cache = {"checked": now, "latest": cache.get("latest")}
            _UPDATE_MEMO.clear()
            _UPDATE_MEMO.update(cache)
            try:
                config.ensure_data_dir()
                config.write_private(UPDATE_CACHE, json.dumps(cache))
            except OSError:
                pass
    latest, mine = version_tuple(cache.get("latest")), version_tuple(__version__)
    newer = bool(latest and mine and latest > mine)
    return {"enabled": True, "latest": cache.get("latest") if newer else None,
            "update_available": newer}

JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_KEEP = 3600       # seconds a finished job stays queryable; its run is in History anyway


def _page():
    path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    with open(path, encoding="utf-8") as f:
        return f.read().replace("{{VERSION}}", __version__)


def _start_job(mode, params):
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "mode": mode, "status": "running", "progress": [],
           "started": time.time(), "result": None, "run_id": None, "error": None,
           "written": [], "current": "", "note": ""}
    with JOBS_LOCK:
        now = time.time()
        for old in [k for k, j in JOBS.items() if j.get("finished") and now - j["finished"] > JOB_KEEP]:
            del JOBS[old]
        JOBS[job_id] = job

    def progress(line):
        job["progress"].append(line)

    def reporter(kind, text):
        if kind == "current":       # a new attempt or a finished request: the retry note is over
            job["current"] = text
            job["note"] = ""
        else:
            job["note"] = text

    def work():
        http.set_reporter(reporter)
        try:
            result = ops.run_mode(mode, params, progress=progress)
            run_id, written = ops.save(mode, params, result)
            job["result"] = {k: v for k, v in result.items() if k != "log"}
            if result.get("log"):
                job["result"]["log"] = result["log"]
            job["run_id"], job["written"] = run_id, written
            job["status"] = "done"
            job["finished"] = time.time()
        except Exception as e:  # noqa: BLE001
            job["error"] = f"{type(e).__name__}: {e}"
            job["progress"].append(traceback.format_exc().splitlines()[-1])
            job["status"] = "error"
            job["finished"] = time.time()

    threading.Thread(target=work, daemon=True).start()
    return job_id


MAX_BODY = 1_000_000   # bytes; a job request is a few hundred


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet
        pass

    def _local_names(self):
        port = self.server.server_address[1]
        hosts = ("127.0.0.1", "localhost", "[::1]")
        names = {f"{h}:{port}" for h in hosts}
        if port == 80:                  # browsers omit the default port
            names |= set(hosts)
        return names

    def _guard(self, post=False):
        """Serve only the page this server itself handed out.

        The server listens on 127.0.0.1, but a web page open in the same browser
        can still reach it in two ways. A cross-site form or fetch with a "simple"
        content type needs no CORS preflight, so it could start jobs. And a page
        whose domain is re-pointed at 127.0.0.1 (DNS rebinding) could read the
        history. The Host header defeats rebinding, because the attacker's domain
        name stays in it; Origin and Sec-Fetch-Site catch cross-site requests;
        and requiring a JSON content type on POST forces a preflight that this
        server never answers. Sends a 403 and returns False when refused."""
        names = self._local_names()
        host = (self.headers.get("Host") or "").strip().lower()
        if host and host not in names:
            self._json({"error": "refused: unexpected Host header"}, 403)
            return False
        origin = (self.headers.get("Origin") or "").strip().lower()
        if origin and origin not in {"http://" + n for n in names}:
            self._json({"error": "refused: request from another site"}, 403)
            return False
        if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
            self._json({"error": "refused: request from another site"}, 403)
            return False
        if post:
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                self._json({"error": "refused: POST must be application/json"}, 415)
                return False
        return True

    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if not self._guard():
            return
        u = urllib.parse.urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        q = urllib.parse.parse_qs(u.query)
        try:
            if not parts:
                return self._send(200, _page(), "text/html")
            if parts[:2] == ["api", "config"]:
                cfg = config.load()
                info = {"version": __version__, "backend": cfg["backend"] or "auto",
                        "repo_url": REPO_URL,
                        "issues_url": REPO_URL + "/issues/new?template=bug_report.md",
                        "model": cfg["model"], "s2_key": bool(cfg["s2_api_key"]),
                        "ollama_models": [], "ollama": False}
                try:
                    info["ollama_models"] = backends.ollama_models()
                    info["ollama"] = True
                except Exception:  # noqa: BLE001
                    pass
                info["openai_base_url"] = cfg["openai_base_url"]
                info["openai_local"] = backends.is_local("openai")
                info["cli_tools"] = backends.cli_tools_available() + (["custom"] if cfg["cli_command"] else [])
                info["cli_tool"] = cfg["cli_tool"]
                info["openai_key"] = bool(cfg["openai_api_key"])
                info["anthropic_key"] = bool(cfg["anthropic_api_key"])
                return self._json(info)
            if parts[:2] == ["api", "update"]:
                return self._json(update_status())
            if parts[:2] == ["api", "history"]:
                return self._json(history.list_runs(limit=200))
            if parts[:2] == ["api", "run"] and len(parts) >= 3:
                run = history.load(parts[2])
                if len(parts) == 4 and parts[3] == "export":
                    fmt = (q.get("fmt") or ["bib"])[0]
                    if fmt not in export.FORMATS:
                        return self._json({"error": f"unknown format {fmt!r}"}, 400)
                    if run.get("papers"):
                        text = export.render(run["papers"], fmt)
                    elif fmt == "md" and run.get("report"):
                        text = ops.report_text(run["mode"], run["inputs"].get("text", ""),
                                               {"report": run["report"], "log": run.get("log")})
                    else:
                        return self._json({"error": "nothing to export in that format"}, 400)
                    fname = f"{run['id']}.{ 'bib' if fmt == 'bibtex' else fmt}"
                    return self._send(200, text, "text/plain",
                                      {"Content-Disposition": f'attachment; filename="{fname}"'})
                return self._json(run)
            if parts[:2] == ["api", "jobs"] and len(parts) == 3:
                job = JOBS.get(parts[2])
                if not job:
                    return self._json({"error": "no such job"}, 404)
                return self._json({k: v for k, v in job.items() if k not in ("started", "finished")})
            return self._json({"error": "not found"}, 404)
        except FileNotFoundError:
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        if not self._guard(post=True):
            return
        u = urllib.parse.urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "bad Content-Length"}, 400)
        if length > MAX_BODY:
            return self._json({"error": "request too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "bad JSON"}, 400)
        if parts[:2] == ["api", "jobs"]:
            mode = body.get("mode")
            if mode not in ops.MODES:
                return self._json({"error": f"unknown mode {mode!r}"}, 400)
            params = {k: body.get(k) for k in ("text", "n", "year_from", "backend", "model", "rounds",
                                               "pick", "base_url", "timeout")}
            params = {k: v for k, v in params.items() if v not in (None, "", [])}
            if "n" in params:
                params["n"] = int(params["n"])
            if "year_from" in params:
                params["year_from"] = int(params["year_from"])
            # No "out" here: the page offers downloads, and a server that writes
            # wherever a request says is a file-overwrite primitive.
            try:
                papers.normalize_input(params.get("text", ""))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"job_id": _start_job(mode, params)})
        return self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        if not self._guard():
            return
        parts = [p for p in self.path.split("/") if p]
        if parts[:2] == ["api", "run"] and len(parts) == 3:
            history.delete(parts[2])
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)


def serve(port=8765, open_browser=True):
    config.tighten_data_dir()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"litsurvey web interface at {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
