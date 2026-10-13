---
name: litsurvey
description: Search scientific literature (OpenAlex, Semantic Scholar, arXiv, PubMed, TechRxiv, Research Square, IACR ePrint; Europe PMC and Crossref on request), walk citations, find open-access copies, export BibTeX, or run an LLM-driven novelty assessment or state-of-the-art survey. Needs the free litsurvey tool installed (pipx install litsurvey). Use whenever the user asks to find papers, check prior art or the state of the art, assess novelty of a claim, list what cites a paper, get a reading list, or says "litsurvey". Prefer this over generic web search for scholarly questions.
---

# litsurvey: scholarly search and novelty assessment

## Before you use this skill

This skill drives the `litsurvey` command-line tool, which must be installed
first. It is free and open source (MIT), needs Python 3.10 or newer, and has
no other dependencies:

```bash
pipx install litsurvey        # or: pip install litsurvey
litsurvey --version           # check it is on PATH
```

Source and documentation: https://github.com/udaykdk/litsurvey
Package: https://pypi.org/project/litsurvey/

If `litsurvey` is not found and `python3 -m litsurvey` does not work either,
tell the user to run `pipx install litsurvey` and stop; do not try to replace
it with web searches. Configuration lives in `~/.litsurvey/config.json`
(`litsurvey init` writes it); never ask the user for API keys and never print
that file.

## Commands

```bash
litsurvey search "keyword query" -n 15 [--year-from 2022] [--sort citations|year] [--abstracts] [--json] [--out refs.bib]
                                            # [--sources openalex,s2,arxiv] to go faster, [--sources ...,europepmc,crossref] to go wider
litsurvey paper   <id|title>    # id: S2 hash, DOI:10..., or ARXIV:2404.19756; a title gives a numbered candidate list (exit 2): rerun with --pick N
litsurvey cites   <id> [-n 20]  # forward snowball: who cites it
litsurvey refs    <id> [-n 20]  # backward snowball: what it cites
litsurvey related <id> [-n 20]  # similar papers via recommender (different vocabulary)
litsurvey oa      <doi>         # legal open-access PDF via Unpaywall
litsurvey novelty  "claim as generic topic" [--rounds 8]  [--out report.md]   # LLM agent, minutes
litsurvey research "question"               [--rounds 12] [--out survey.md]   # LLM agent, minutes
litsurvey history [show <id> | export <id> --out x.bib | delete <id>]
litsurvey doctor                # run this first if anything fails
```

## How to use it well

- For a literature question, run 2 to 4 `search` calls with different
  phrasings (synonyms, method-centric and application-centric), then
  `cites`/`related` on the closest hits. Use `--json` when you will process
  results further.
- Cite only titles, DOIs and URLs that appear in the tool output. Do not
  reformat references from memory.
- `novelty` and `research` hand the whole job to the LLM backend the user
  configured in litsurvey (a local Ollama model, a subscription CLI, or an
  API key; `litsurvey doctor` says which) and take minutes; run them in the
  background. Use them when the user asks for them, or for confidential
  material when the backend is local; otherwise drive
  `search`/`cites`/`related` yourself and synthesise.
- To read a paper: `oa <doi>` for a PDF link, or fetch
  `https://arxiv.org/html/<arxiv id>` for arXiv full text.
- Semantic Scholar is limited to 1 request/second; do not run litsurvey
  commands in parallel.

## Confidentiality rule

Users may be reviewing confidential manuscripts. Queries must be short
generic keyword phrases. Never put verbatim sentences, titles, author names
or identifying phrasing from a manuscript into a query, and never send
manuscript text to any web service.
