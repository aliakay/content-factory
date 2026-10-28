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


TRENDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
 <item><title>Fenerbah\xc3\xa7e</title><ht:approx_traffic>200,000+</ht:approx_traffic></item>
 <item><title>ikindi namaz\xc4\xb1</title><ht:approx_traffic>10000+</ht:approx_traffic></item>
</channel></rss>"""


def test_regions_scope_and_turkish_tokens():
    tr = discover.scope(region="tr")
    assert set(tr["categories"]) == {"tr_gundem", "tr_spor", "tr_tech"}
    assert discover.scope(region="tr", only=["tr_spor"])["max_total_ideas"] == 3
    assert "tr_spor" not in discover.scope(region="global")["categories"]
    with pytest.raises(ValueError):
        discover.scope(region="global", only=["tr_spor"])
    assert discover.region_of("tr_tech") == "tr" and discover.region_of("ai") == "global"
    # diacritics folded, Turkish stop words dropped: the same story matches across spellings
    assert discover.tokens("İstanbul'da yeni metro hattı açıldı") >= {"istanbul", "metro", "hatti", "acildi"}
    assert "ve" not in discover.tokens("Galatasaray ve Fenerbahçe")


def test_trends_signal_and_turkish_exclude():
    trends = discover.parse_trends(TRENDS)
    assert trends == {"Fenerbahçe": 200000, "ikindi namazı": 10000}
    cands = [{"story": "Fenerbahçe'nin yeni transferi imzayı attı", "signals": {}},
             {"story": "Merkez Bankası faiz kararı", "signals": {}}]
    discover.attach_wiki(cands, trends, key="trend")
    assert cands[0]["signals"]["trend_term"] == "Fenerbahçe" and "trend" not in cands[1]["signals"]
    items = [item("Süper Lig'de rekor gol ortalaması", cat="tr_spor", source="aa.com.tr"),
             item("Şüpheli GÖZALTINA alındı", cat="tr_gundem", source="trthaber.com"),
             item("Gözaltı haberi değil: yeni uydu fırlatıldı", cat="ai", source="x.com")]
    kept = [i["title"] for i in discover._fresh(items, discover.NICHES)]
    assert kept == ["Süper Lig'de rekor gol ortalaması", "Gözaltı haberi değil: yeni uydu fırlatıldı"]


def test_cards_show_newest_run_per_scope_and_filter_by_region():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    discover.ensure(con)
    def run(scope, cards):
        rid = con.execute("INSERT INTO disc_runs (at, items, candidates, cards, cost_usd, note, scope) "
                          "VALUES ('t',1,1,1,0,'',?)", (scope,)).lastrowid
        for cat, title in cards:
            con.execute("INSERT INTO disc_cards (run_id, created_at, category, status, title, data) VALUES (?,?,?,?,?,?)",
                        (rid, "t", cat, "new", title, json.dumps({"title": title, "category": cat})))
    run(None, [("ai", "old global")])                 # pre-region run: counts as global
    run("global", [("ai", "new global")])
    run("tr:tr_spor", [("tr_spor", "spor 1")])
    run("tr:tr_tech", [("tr_tech", "tek 1")])
    run("tr:tr_spor", [("tr_spor", "spor 2")])
    titles = {c["title"] for c in discover.cards(con)["cards"]}
    assert titles == {"new global", "spor 2", "tek 1"}
    tr = discover.cards(con, region="tr")
    assert {c["title"] for c in tr["cards"]} == {"spor 2", "tek 1"} and all(c["region"] == "tr" for c in tr["cards"])
    assert tr["regions"] == {"global": "Global", "tr": "Türkiye"}


def test_video_language_overrides_channel_language():
    from factory import channels
    ch = {"name": "Konu anlatımı", "lang": "en", "audience": "global"}
    assert "on-screen language: English" in channels.prompt_note(ch)
    assert "on-screen language: Turkish (this video's language" in channels.prompt_note(ch, "tr")
