import csv
import io

from litsurvey import export
from litsurvey import papers as P


def sample():
    return [P.make(title="Learning {Braces} & Percent 50%", year=2024,
                   authors=["Jane Q Public", "Wei Li"], venue="J. Test", doi="10.1/x",
                   url="https://doi.org/10.1/x", abstract="abs"),
            P.make(title="An arXiv Only Paper", year=2025, authors=["Solo Author"],
                   venue="arXiv", arxiv="2501.00001", url="https://arxiv.org/abs/2501.00001"),
            P.make(title="Learning again", year=2024, authors=["Jane Public"])]


def test_bibtex_entries_types_and_escaping():
    bib = export.to_bibtex(sample())
    assert "@article{public2024learning," in bib
    assert "@misc{author2025arxiv," in bib
    assert "eprint = {2501.00001}" in bib and "archivePrefix = {arXiv}" in bib
    assert "\\textbraceleft{}Braces\\textbraceright{}" in bib and "\\&" in bib and "50\\%" in bib
    assert "author = {Public, Jane Q and Li, Wei}" in bib


def test_bibtex_keys_are_unique():
    bib = export.to_bibtex(sample())
    assert "public2024learning," in bib and "public2024learning2," in bib


def test_ris_and_csv():
    ris = export.to_ris(sample())
    assert ris.startswith("TY  - JOUR") and "AU  - Public, Jane Q" in ris and "ER  - " in ris
    rows = list(csv.reader(io.StringIO(export.to_csv(sample()))))
    assert rows[0][0] == "title" and len(rows) == 4
    assert rows[1][4] == "10.1/x"


def test_render_and_write(tmp_path):
    for fmt in ("bib", "ris", "csv", "json", "md"):
        assert export.render(sample(), fmt)
    out = tmp_path / "refs.bib"
    export.write(sample(), str(out))
    assert out.read_text().startswith("@article")
    try:
        export.render(sample(), "docx")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_bibtex_escapes_latex_specials_and_handles_suffixes():
    from litsurvey import export, papers
    bib = export.to_bibtex([papers.make(title="C# a_b ~x^2 $5 & 10% {g}", year=2020,
                                        authors=["Martin Luther King Jr.", "Ann Lee III"])])
    title = [l for l in bib.splitlines() if "title" in l][0]
    for raw in ("C#", "a_b", " ~x", "^2", " $5"):
        assert raw not in title
    assert r"C\# a\_b \textasciitilde{}x\textasciicircum{}2 \$5 \& 10\% \textbraceleft{}g\textbraceright{}" in title
    assert "author = {King, Jr., Martin Luther and Lee, III, Ann}" in bib
    assert bib.startswith("@misc{king2020")


def test_bibtex_stays_balanced_with_a_lone_brace():
    from litsurvey import export, papers
    bib = export.to_bibtex([papers.make(title="Sets {a, b and c", year=2020, doi="10.5555/x"),
                            papers.make(title="Closing } only", year=2021)])
    for entry in bib.strip().split("\n\n"):
        depth = 0
        for ch in entry:
            depth += {"{": 1, "}": -1}.get(ch, 0)
            assert depth >= 0
        assert depth == 0
