# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.1] - 2026-10-10

### Security
These were found and reported privately by Anant Goyal. Upgrade if you use
`litsurvey web`.

- The web server accepted requests from other web sites. A page open in the
  same browser could start jobs and, through the output-file field, write a
  file anywhere in the user's home folder; a page that points its own domain
  name at 127.0.0.1 could read the run history. The server now refuses any
  request whose `Host` is not its own loopback address and port, any request
  carrying another site's `Origin` or `Sec-Fetch-Site: cross-site`, and any
  POST that is not `application/json`. The web API no longer takes an output
  path at all; results are downloaded from the page.
- `is_local()` decided "local" by a substring test, so a cloud URL such as
  `https://localhost.example.com` was reported as a local model. The host name
  is now parsed and compared exactly, here and in the page's banner.
- `~/.litsurvey` is now readable by its owner only (mode 700, tightened at
  start-up on existing installs) and run files and the history index are
  mode 600.
- Codex CLI now gets the prompt on stdin, so the claim is not visible to other
  accounts in the process list.
- Claude Code is started with only its shell tool (`--tools Bash`), and its
  shell may run only the five lookup commands (`litsurvey search`, `paper`,
  `cites`, `refs`, `related`). Before, its read tools were available without
  asking, and `litsurvey history show` accepted a path such as `../../file`.
- History run ids are checked against litsurvey's own format, so neither the
  command line nor the web API can be pointed at another file.
- When a subscription agent runs `litsurvey`, it refuses `--out`, `history`,
  `init`, `web` and the agent commands (an environment variable marks the
  agent's shell). This applies to Codex, Gemini and Antigravity as well.
- Search results reach the model inside marked blocks, with an instruction
  that nothing in them is a command. With a local model or an API key, a
  search query that repeats eight or more consecutive words of the user's
  input is refused. `docs/confidentiality.md` now says plainly which parts of
  the confidentiality rules are instructions and which are enforced, and what
  each subscription CLI could do if a hostile abstract steered it.

### Added
- `SECURITY.md`: how to report a vulnerability privately.
- **Google Antigravity CLI (`agy`) support** as a subscription CLI backend
  alongside Claude Code, Codex, and Gemini CLI. Automatically probes reasoning
  effort from `agy --help` (defaulting to `medium`).

## [1.1.0] - 2026-09-12

### Added
- **PubMed** as a default search source, through the NCBI E-utilities
  (esearch for the matching record ids, efetch for the records, so abstracts
  come back and the LLM agents can judge relevance). More than 40 million
  biomedical citations, authoritatively indexed; the general indexes cover
  much of the same ground but not with PubMed's subject indexing. Journal
  articles and book/chapter records are both parsed.
- **Europe PMC** as an opt-in source (`--sources europepmc`): PubMed's ground
  again, but with citation counts and the bioRxiv/medRxiv preprints. Off by
  default because it largely repeats PubMed.
- Subscription CLI backends now run at a deliberate model and reasoning
  effort instead of the tool's own maximum. `litsurvey init` asks the
  installed binary what it supports and picks one model below the best at an
  effort level in the middle of the range — for Claude Code, Opus at `high`.
  Stored as `cli_model` / `cli_effort` in the config (`"-"` means "leave the
  tool at its own default"), shown by `litsurvey doctor`, and overridable
  with `LITSURVEY_CLI_MODEL` / `LITSURVEY_CLI_EFFORT`. The stored choice
  belongs to the tool it was made for, so switching `cli_tool` re-runs the
  poll instead of passing a Claude model name to codex.

### Fixed
- **The `codex` CLI backend was broken**: `codex exec --full-auto` no longer
  exists (removed by codex-cli; it fails with "unexpected argument"). The
  command is now `codex exec --skip-git-repo-check --sandbox workspace-write
  --add-dir ~/.litsurvey -c sandbox_workspace_write.network_access=true`.
  Without the sandbox flags codex has no network — every `litsurvey` call
  inside it returns nothing while codex still exits 0 and writes a
  confident, empty report — refuses to start outside a git repository, and
  cannot write the run history. Codex is given an empty temporary directory
  as its working root, so its write sandbox covers a scratch area and
  `~/.litsurvey` rather than the directory you started from. Verified end to
  end against codex-cli 0.153.4.
- A subscription CLI's final report is now read from a file it writes
  (`-o`), not from stdout, which also carries progress and tool-call
  chatter.

### Notes
- DBLP was considered and left out: its search API sits behind a
  proof-of-work bot wall on every mirror (dblp.org, dblp.uni-trier.de,
  dblp.dagstuhl.de), which litsurvey will not try to defeat.

## [1.0.1] - 2026-09-11

### Fixed
- Without a Semantic Scholar key, searches took about a minute because the
  refusing shared pool was retried five times; keyless retries are now
  capped at two (about ten seconds), and `doctor` reports a keyless Semantic
  Scholar failure as a warning instead of a problem.
- `related` returned nothing when Semantic Scholar answered with an empty
  list; it now falls back to OpenAlex related works, which also no longer
  include the paper itself.
- Custom subscription-CLI commands on Windows lost the backslashes in paths.
- The web page's Search label listed three sources; it now says six.

### Added
- The web page accepts `?mode=<mode>&text=<query>` in the URL to preselect a
  mode and fill the input.
- README: screenshot, and how to get the Semantic Scholar key and what
  happens without it.

## [1.0.0] - 2026-09-11

First public release.

### Added
- `search`: fused, de-duplicated keyword search over OpenAlex, Semantic Scholar,
  arXiv, TechRxiv, Research Square (via Crossref) and the IACR ePrint archive,
  with `--sort relevance|citations|year`.
- `paper`, `cites`, `refs`, `related`: one paper and its citation neighbourhood;
  a title is accepted in place of an id, with a candidate list and `--pick N`.
  `cites`/`refs` rank by citation count via OpenAlex, with Semantic Scholar as
  fallback; `related` and `paper` fall back to OpenAlex when Semantic Scholar
  is unavailable.
- `oa`: legal open-access copies via Unpaywall.
- `novelty` and `research`: LLM-driven agents with pluggable backends and a
  reproducible search log. Backends: `cli` (delegates the task to a signed-in
  Claude Code, Codex CLI or Gemini CLI under the user's subscription),
  `ollama` (local), `openai` (any OpenAI-compatible server, `--base-url` for
  OpenRouter, LM Studio and others), `anthropic`.
- Export to BibTeX, RIS, CSV, JSON and Markdown from any result list.
- Run history (`litsurvey history`) shared by the CLI and the web page.
- `litsurvey web`: local browser interface with a History tab, a photo
  banner, a three-way choice of where the LLM runs (subscription CLI, local
  model, cloud API key) with a privacy banner, BibTeX/RIS/CSV downloads,
  URL detection with DOI/arXiv conversion, "waiting for <source>" status
  while a run is in progress, and a report-a-bug link.
- `init` and `doctor` commands.
- Per-host rate limiting (Semantic Scholar 1 req/s, arXiv 1 req/3 s) and
  `Retry-After` handling.
