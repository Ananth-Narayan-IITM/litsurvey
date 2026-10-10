"""The paper record, de-duplication, rank fusion and text formatting."""
import itertools
import re

FIELDS = ("title", "year", "venue", "authors", "doi", "arxiv", "s2_id",
          "citations", "abstract", "url", "sources")


def make(**kw):
    p = {"title": "", "year": None, "venue": "", "authors": [], "doi": "",
         "arxiv": "", "s2_id": "", "citations": 0, "abstract": "", "url": "",
         "sources": []}
    p.update({k: v for k, v in kw.items() if k in FIELDS})
    p["citations"] = int(p["citations"] or 0)
    p["doi"] = (p["doi"] or "").replace("https://doi.org/", "").strip()
    return p


def norm_title(t):
    """Letters and digits only, in any script: "[a-z0-9]" alone would turn every
    Chinese or Russian title into "" and merge them all into one paper."""
    return re.sub(r"[\W_]+", "", (t or "").casefold())


# Preprint servers that register a new DOI for every version of a paper:
# TechRxiv 10.36227/techrxiv.16610629.v7 or .../techrxiv.176704133.32328897/v2,
# Research Square 10.21203/rs.3.rs-123/v2
_VERSIONED_DOI = re.compile(r"^(10\.(?:36227|21203)/.+?)[./]v\d+$")
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$")
# A title this long is specific enough to identify a paper on its own; shorter
# ones ("Editorial", "Preface", "Deep learning") also need the year to match.
_DISTINCT_TITLE = 30


def keys(p):
    """Every identity a record can be matched on: its DOI (with version suffixes
    removed), its arXiv id (also when it is only known as an arXiv DOI), and its
    title. Two records are the same paper when any of these agree."""
    out = []
    doi = (p.get("doi") or "").strip().lower()
    arx = (p.get("arxiv") or "").strip().lower()
    if doi:
        m = _ARXIV_DOI.match(doi)
        if m:
            arx = arx or m.group(1)
        else:
            v = _VERSIONED_DOI.match(doi)
            out.append("doi:" + (v.group(1) if v else doi))
    if arx:
        out.append("arxiv:" + re.sub(r"v\d+$", "", arx))
    t = norm_title(p.get("title"))
    if len(t) >= _DISTINCT_TITLE:
        out.append("title:" + t)
    elif t and p.get("year"):          # a short title with no year identifies nothing
        out.append(f"title:{t}|{p['year']}")
    return out


def _ids(ks):
    return {k for k in ks if not k.startswith("title:")}


# DOI prefixes of preprint servers. A preprint DOI and a journal DOI on records
# with the same title are one paper in two places, not a contradiction.
_PREPRINT_DOI = ("doi:10.36227/", "doi:10.21203/", "doi:10.1101/", "doi:10.2139/ssrn",
                 "doi:10.20944/", "doi:10.31219/", "doi:10.22541/")


def _kind(k):
    if k.startswith("arxiv:"):
        return "arxiv"
    return "preprint" if k.startswith(_PREPRINT_DOI) else "journal"


def _conflict(a, b):
    """True when two sets of identifiers belong to different papers: both have a
    journal DOI (or both a preprint DOI, or both an arXiv id) and none of them
    agree. A matching title must not join such records: two editorials of the
    same year are still two papers."""
    for kind in ("journal", "preprint", "arxiv"):
        x = {k for k in a if _kind(k) == kind}
        y = {k for k in b if _kind(k) == kind}
        if x and y and not x & y:
            return True
    return False


def key(p):
    """The primary identity of a record (see keys())."""
    ks = keys(p)
    return ks[0] if ks else "id:" + str(id(p))


def best_id(p):
    """The identifier to pass to paper/cites/refs/related. A DOI is preferred
    because both Semantic Scholar and OpenAlex accept it (so fallbacks work);
    then an arXiv id, then the Semantic Scholar hash."""
    if p.get("doi"):
        return "DOI:" + p["doi"]
    if p.get("arxiv"):
        return "ARXIV:" + p["arxiv"]
    if p.get("s2_id"):
        return p["s2_id"]
    return ""


def _absorb(q, p):
    """Fold record p into record q (same paper, seen again)."""
    q["sources"] = sorted(set(q["sources"]) | set(p["sources"]))
    q["citations"] = max(q["citations"], p["citations"])
    for f in ("title", "doi", "arxiv", "s2_id", "venue", "abstract", "url", "year"):
        if not q.get(f) and p.get(f):
            q[f] = p[f]
    if len(p.get("authors") or []) > len(q["authors"]):
        q["authors"] = p["authors"]


def merge(result_lists, k=60):
    """Dedupe across sources and fuse rankings with reciprocal rank fusion.
    Each element is a result list, or a (list, weight) pair.

    A record joins an existing paper when its DOI or arXiv id agrees, or when
    its title agrees and no DOI or arXiv id says otherwise. So a preprint known
    by its arXiv id meets the same paper known by its arXiv DOI, a record that
    matches two papers at once joins them, and a paper that gains a DOI or a
    year while being merged is matched again on those."""
    papers, scores, ids, owner = {}, {}, {}, {}   # group -> record, score, id keys; key -> group
    counter = itertools.count()

    def join(g, o):
        _absorb(papers[g], papers.pop(o))
        scores[g] += scores.pop(o)
        ids[g] |= ids.pop(o)
        for kk, v in owner.items():
            if v == o:
                owner[kk] = g

    def register(g):
        """Record g's keys; join any other group a key of g already points to."""
        changed = True
        while changed:
            changed = False
            ids[g] |= _ids(keys(papers[g]))
            for kk in keys(papers[g]):
                o = owner.setdefault(kk, g)
                if o != g and o in papers and not _conflict(ids[g], ids[o]):
                    join(g, o)
                    changed = True
                    break

    for item in result_lists:
        results, weight = (item if isinstance(item, tuple) else (item, 1.0))
        for rank, p in enumerate(results):
            ks = keys(p)
            pid = _ids(ks)
            groups = []
            for kk in ks:
                g = owner.get(kk)
                if g is None or g in groups or g not in papers:
                    continue
                if kk.startswith("title:") and _conflict(ids[g], pid):
                    continue
                groups.append(g)
            if groups:
                gid = groups[0]
                _absorb(papers[gid], p)
                ids[gid] |= pid
                for o in groups[1:]:
                    if o in papers and not _conflict(ids[gid], ids[o]):
                        join(gid, o)
            else:
                gid = next(counter)
                papers[gid], scores[gid], ids[gid] = dict(p), 0.0, set(pid)
            scores[gid] += weight / (k + rank)
            register(gid)
    return [papers[g] for g in sorted(papers, key=lambda x: scores[x], reverse=True)]


def format_paper(p, i=None, snippet=0):
    head = f"{i}. " if i is not None else ""
    authors = ", ".join(p["authors"][:3]) + (" et al." if len(p["authors"]) > 3 else "")
    line = (f"{head}**{p['title']}** ({p['year']}) — {authors or 'unknown authors'}\n"
            f"   {p['venue'] or '?'} · {p['citations']} citations · "
            f"[{'+'.join(p['sources']) or '?'}] · id: `{best_id(p) or 'n/a'}`\n"
            f"   {p['url']}")
    if snippet and p["abstract"]:
        line += f"\n   > {p['abstract'][:snippet].strip()}…"
    return line


def compact(papers, n=8, abstract_chars=350):
    """Small dicts for feeding an LLM."""
    return [{"title": p["title"], "year": p["year"], "venue": p["venue"],
             "citations": p["citations"], "id": best_id(p),
             "doi": p["doi"], "arxiv": p["arxiv"],
             "abstract": (p["abstract"] or "")[:abstract_chars]} for p in papers[:n]]


_ID_RES = (re.compile(r"^[0-9a-f]{40}$", re.I),                  # Semantic Scholar hash
           re.compile(r"^(DOI:)?10\.\d{4,9}/\S+$", re.I),         # DOI
           re.compile(r"^(ARXIV:)?\d{4}\.\d{4,5}(v\d+)?$", re.I),  # new-style arXiv id
           re.compile(r"^(ARXIV:)?[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$", re.I))  # old-style arXiv id


def is_paper_id(text):
    t = (text or "").strip()
    return any(r.match(t) for r in _ID_RES)


def canonical_id(text):
    """Add the DOI:/ARXIV: prefix Semantic Scholar expects when it is missing."""
    t = (text or "").strip()
    if re.match(r"^10\.\d{4,9}/", t):
        return "DOI:" + t
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", t) or re.match(r"^[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$", t, re.I):
        return "ARXIV:" + re.sub(r"v\d+$", "", t)
    return t


URL_RE = re.compile(r"^\s*(https?://|www\.)", re.I)
URL_HELP = ("URLs are not accepted. Use keywords for a search, or a paper id: "
            "DOI:10.xxxx/..., ARXIV:2404.19756, or a Semantic Scholar hash. "
            "For a publisher page (IEEE Xplore, Elsevier, Springer, ...) copy the DOI shown on that page.")


def clean_text(text):
    """Collapse newlines, tabs and repeated spaces (pasted titles often carry line
    breaks) and strip surrounding whitespace and stray quotes."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t.strip("\"'\u201c\u201d ").strip()


def normalize_input(text):
    """Clean whitespace; convert well-known paper URLs to ids; reject other URLs
    with guidance. Returns (text, note). note is '' when nothing changed."""
    t = clean_text(text)
    if not URL_RE.match(t):
        return t, ""
    m = re.search(r"doi\.org/(10\.[^\s?#]+)", t, re.I)
    if m:
        return "DOI:" + m.group(1).rstrip("/"), "converted DOI URL to " + "DOI:" + m.group(1).rstrip("/")
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?/?(?:[?#].*)?$", t, re.I)
    if m:
        return "ARXIV:" + m.group(1), "converted arXiv URL to ARXIV:" + m.group(1)
    m = re.search(r"semanticscholar\.org/paper/(?:[^/\s]+/)*([0-9a-f]{40})", t, re.I)
    if m:
        return m.group(1), "converted Semantic Scholar URL to its paper id"
    raise ValueError(URL_HELP)


def scholar_url(query):
    import urllib.parse
    return "https://scholar.google.com/scholar?q=" + urllib.parse.quote_plus(query)
