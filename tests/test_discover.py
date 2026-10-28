"""Discovery: paper parsers (documented API shapes), embedding clustering, history dedupe, paper filter."""
import json, sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from factory import discover, embed


@pytest.fixture(autouse=True)
def hash_backend(monkeypatch):
    monkeypatch.setattr(embed, "_backend", "hash")   # deterministic, no model download in tests


NOW = datetime.now(timezone.utc)
ARXIV = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
 <entry><id>http://arxiv.org/abs/2610.01234v1</id><published>{NOW:%Y-%m-%dT%H:%M:%SZ}</published>
  <title>Small Language Models Learn
   to Use Tools</title><summary>We show that ...</summary><arxiv:doi>10.48550/arXiv.2610.01234</arxiv:doi></entry>
</feed>""".encode()
BIORXIV = {"collection": [
    {"doi": "10.1101/2026.10.25.111", "title": "Gut microbes shape sleep in mice", "date": f"{NOW:%Y-%m-%d}",
     "version": "1", "category": "neuroscience", "abstract": "We find ..."},
    {"doi": "10.1101/2026.10.01.999", "title": "Old preprint revised", "date": f"{NOW:%Y-%m-%d}", "version": "3"}]}
PUBMED = {"result": {"uids": ["41000001"], "41000001": {
    "title": "Water ice at the lunar south pole.", "source": "Nature", "fulljournalname": "Nature",
    "sortpubdate": f"{NOW:%Y/%m/%d} 00:00", "articleids": [{"idtype": "doi", "value": "10.1038/s41586-026-0001-1"}]}}}


def item(title, cat="science", source="bbc.co.uk", hours=2):
    return {"title": title, "url": "https://x/" + title[:8], "published": (NOW - timedelta(hours=hours)).isoformat(),
            "source": source, "summary": "", "category": cat}


def test_parsers():
    a = discover.parse_arxiv(ARXIV)
    assert a[0]["title"] == "Small Language Models Learn to Use Tools" and a[0]["paper"]["kind"] == "preprint"
    assert a[0]["paper"]["id"] == "2610.01234v1"
    b = discover.parse_biorxiv(json.dumps(BIORXIV))
    assert len(b) == 1 and b[0]["paper"]["doi"] == "10.1101/2026.10.25.111"   # revised versions are not news
    p = discover.parse_pubmed_summary(PUBMED)
    assert p[0]["paper"]["kind"] == "journal" and p[0]["paper"]["doi"].startswith("10.1038/")
    o = discover.parse_openalex({"id": "W1", "doi": "https://doi.org/10.1/x", "cited_by_count": 3,
                                 "best_oa_location": {"pdf_url": "https://x/p.pdf"}})
    assert o["doi"] == "10.1/x" and o["oa_url"] == "https://x/p.pdf"


def test_reworded_headlines_cluster_and_papers_join_their_press():
    items = [item("OpenAI releases GPT-6 with 10x cheaper pricing", "ai", "verge.com"),
             item("OpenAI launches GPT-6, slashing prices tenfold", "ai", "reuters.com"),
             item("Apple unveils new iPhone 18", "tech", "bbc.co.uk"),
             item("NASA confirms water ice at the Moon's south pole", "science", "bbc.co.uk")]
    items += discover.parse_pubmed_summary(PUBMED)
    cands = discover.cluster(items, discover.NICHES)
    by = {c["story"]: c for c in cands}
    assert len(cands) == 3
    gpt = next(c for c in cands if "GPT-6" in c["story"])
    assert gpt["signals"]["source_count"] == 2
    moon = next(c for c in cands if c.get("paper"))
    assert moon["category"] == "papers" and moon["signals"]["press"] == 1 and "Apple unveils new iPhone 18" in by


def test_drop_seen_and_paper_filter(tmp_path):
    con = sqlite3.connect(tmp_path / "d.db")
    con.row_factory = sqlite3.Row
    discover.ensure(con)
    con.execute("INSERT INTO disc_cards (created_at, title, status, data) VALUES (?,?,?,?)",
                (NOW.isoformat(), "OpenAI launches GPT-6 and cuts prices", "picked", "{}"))
    con.commit()
    cands = [{"story": "OpenAI releases GPT-6 with 10x cheaper pricing", "signals": {}},
             {"story": "Bees can count to five, study finds", "signals": {}}]
    kept, dropped = discover.drop_seen(con, cands)
    assert [c["story"] for c in kept] == ["Bees can count to five, study finds"] and len(dropped) == 1
    pre = [{"story": f"p{i}", "first_seen": f"2026-10-{10 + i}", "signals": {}, "paper": {"kind": "preprint"}}
           for i in range(12)]
    covered = {"story": "c", "first_seen": "x", "signals": {"press": 2}, "paper": {"kind": "preprint"}}
    out = discover.paper_filter(pre + [covered])
    assert covered in out and len(out) == 1 + discover.MAX_UNCOVERED_PREPRINTS


def test_brief_points_research_at_the_paper():
    b = discover.brief_for({"title": "T", "topic": "x", "hook": "h", "flags": ["preprint"],
                            "paper": {"kind": "preprint", "doi": "10.1/x", "oa_url": "https://x/p.pdf"}})
    assert "PRIMARY SOURCE" in b and "NOT peer reviewed" in b and "https://x/p.pdf" in b
