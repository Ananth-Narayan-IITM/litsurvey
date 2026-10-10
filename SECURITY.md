# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Email the author,
Uday Khankhoje, at uday@ee.iitm.ac.in with a description and, if you have one,
a way to reproduce it. You should get a reply within a week. Once a fix is
released, the CHANGELOG credits the reporter unless they ask otherwise.

## What litsurvey treats as a security boundary

- `litsurvey web` serves one user on `127.0.0.1`. It must not act on requests
  from any other web site, and must not read or write files outside
  `~/.litsurvey` on behalf of the page.
- Files under `~/.litsurvey` (configuration, keys, past claims and reports)
  must be readable by their owner only.
- The LLM agents read text written by strangers (titles and abstracts). That
  text must not be able to make litsurvey itself run commands or read files.
  What a third-party agent (Codex, Gemini, Antigravity) can be talked into is
  limited by that tool's own sandbox; see `docs/confidentiality.md`.
