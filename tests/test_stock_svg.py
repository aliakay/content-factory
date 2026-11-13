"""Commons SVG/CC0 props: licence filter, object-not-text rule, sanitising, viewBox repair and the licence ledger."""
import json

import pytest

from factory import licence, stock
from factory.hat import tools


HORSE = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
         '<script>alert(1)</script><style>.a{fill:red}</style>'
         '<foreignObject width="10" height="10"><div>x</div></foreignObject>'
         '<use href="https://evil.example/x.svg"/>'
         '<path d="M0 0 L10 10" style="fill:red;background:url(https://evil/x)"/></svg>')
HORSE2 = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24z"/>'
          '<text x="1" y="2">24</text></svg>')
CALENDAR = ('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20"/>'
            '<text>1</text><text>2</text></svg>')
BROKEN = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'


def _page(title, url, lic, size=9000, index=1, mime="image/svg+xml"):
    return {"title": title, "index": index,
            "imageinfo": [{"url": url, "descriptionurl": "https://commons.example/" + title.replace(" ", "_"),
                           "mime": mime, "size": size,
                           "extmetadata": {"LicenseShortName": {"value": lic}}}]}


PAGES = [
    _page("File:Horse silhouette.svg", "https://upload.example/horse.svg", "CC0", index=1),
    _page("File:Horse calendar.svg", "https://upload.example/calendar.svg", "Public domain", index=2),
    _page("File:Horse drawing CC BY.svg", "https://upload.example/horse-by.svg", "CC BY 4.0", index=3),
    _page("File:Horse drawing CC BY-SA.svg", "https://upload.example/horse-sa.svg", "CC BY-SA 4.0", index=4),
    _page("File:Horse logo.svg", "https://upload.example/logo.svg", "CC0", index=5),
    _page("File:Horse huge.svg", "https://upload.example/huge.svg", "CC0", size=400_000, index=6),
    _page("File:Train station.svg", "https://upload.example/train.svg", "CC0", index=7),
    _page("File:Horse broken.svg", "https://upload.example/broken.svg", "PD", index=8),
    _page("File:Horse two shapes.svg", "https://upload.example/horse2.svg", "CC0", index=9),
]
SVGS = {"https://upload.example/horse.svg": HORSE, "https://upload.example/calendar.svg": CALENDAR,
        "https://upload.example/horse-by.svg": '<svg width="10" height="10"><path d="M0 0"/></svg>',
        "https://upload.example/horse-sa.svg": '<svg width="10" height="10"><path d="M0 0"/></svg>',
        "https://upload.example/logo.svg": '<svg width="10" height="10"><path d="M0 0"/></svg>',
        "https://upload.example/huge.svg": '<svg width="10" height="10"><path d="M0 0"/></svg>',
        "https://upload.example/train.svg": '<svg width="10" height="10"><path d="M0 0"/></svg>',
        "https://upload.example/broken.svg": BROKEN,
        "https://upload.example/horse2.svg": HORSE2}


class Http:
    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if "api.php" in url:
            return json.dumps({"query": {"pages": {str(i): p for i, p in enumerate(PAGES)}}}).encode()
        return SVGS[url].encode()


class Boom:
    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        raise RuntimeError("network should not be needed")


@pytest.fixture
def root(tmp_path, monkeypatch):
    for m in (stock, licence):
        monkeypatch.setattr(m, "ROOT", str(tmp_path))
    monkeypatch.setattr(stock, "DIR", str(tmp_path / "assets" / "stock"))
    monkeypatch.setattr(stock, "SVG_DIR", str(tmp_path / "assets" / "stock"))
    monkeypatch.setattr(stock, "CACHE", str(tmp_path / "data" / "stock_cache.json"))
    return tmp_path


def _svg(rel):
    return (stock.ROOT + "/" + rel) if not rel.startswith("/") else rel


def test_default_is_pd_or_cc0_only(root):
    http = Http()
    hits = stock.search_vectors("horse", n=5, http=http)
    titles = [h["title"] for h in hits]
    assert "Horse silhouette.svg" in titles and "Horse two shapes.svg" in titles
    assert not any("CC BY" in h["license"] for h in hits)
    assert not any("calendar" in h["title"] or "logo" in h["title"] or "huge" in h["title"]
                   or "Train" in h["title"] or "broken" in h["title"] for h in hits)
    json.dump({"query": "horse", "pages": [h["title"] for h in hits]}, open(root / "hits.json", "w"))
    assert len(hits) == 2
    svg = open(_svg(hits[0]["file"]), encoding="utf-8").read()
    assert 'viewBox="0 0 100 50"' in svg                 # repaired from width/height
    for bad in ("<script", "<foreignObject", "<style", 'href="http', "<text"):
        assert bad not in svg
    assert '<path d="M0 0 L10 10"' in svg and "background:" not in svg
    assert hits[0]["width"] == 100 and hits[0]["height"] == 50 and hits[0]["shapes"] >= 1
    assert hits[0]["credit"] is False


def test_cc_by_is_optional_and_needs_credit(root):
    hits = stock.search_vectors("horse", n=5, allow_cc_by=True, http=Http())
    by = [h for h in hits if h["license"] == "CC BY 4.0"]
    assert by and by[0]["credit"] is True
    assert not any(h["license"] == "CC BY-SA 4.0" for h in hits)      # share-alike stays out


def test_the_answer_is_cached_with_its_files(root):
    first = Http()
    hits = stock.search_vectors("horse", n=5, http=first)
    assert first.calls
    boom = Boom()
    again = stock.search_vectors("horse", n=5, http=boom)
    assert boom.calls == [] and [h["file"] for h in again] == [h["file"] for h in hits]
    assert (root / "assets" / "stock").is_dir() and (root / "data" / "stock_cache.json").exists()


def test_a_search_with_no_object_is_cached_as_empty(root):
    assert stock.search_vectors("unicorn", n=2, http=Http()) == []
    boom = Boom()
    assert stock.search_vectors("unicorn", n=2, http=boom) == []
    assert boom.calls == []


def test_sanitizer_and_size_helpers():
    with pytest.raises(ValueError):
        stock.sanitize_svg("<html>no svg here</html>")
    out = stock.sanitize_svg('<svg viewBox="0 0 10 10"><a href="https://x/a"><rect width="1"/></a>'
                             '<use xlink:href="#shape"/><use xlink:href="https://x/y.svg"/></svg>')
    assert 'xlink:href="#shape"' in out and "https://x" not in out and '<rect width="1"' in out
    assert stock.svg_size('<svg viewBox="0 0 12 8"/>') == (12.0, 8.0)
    assert stock.svg_size('<svg width="5px" height="6px"/>') == (5.0, 6.0)
    with pytest.raises(ValueError):
        stock.svg_size("<svg><path/></svg>")


def test_the_credit_reaches_the_licence_ledger(root):
    hit = next(h for h in stock.search_vectors("horse", n=5, allow_cc_by=True, http=Http()) if h["credit"])
    plan = {"scenes": [{"html": f'<img src="/{hit["file"]}">'}]}
    rows = licence.stock_entries(plan)
    assert rows and rows[0]["licence"] == "CC BY 4.0" and rows[0]["credit"] is True
    assert hit["title"] in licence.block(rows)


def test_the_agent_tool_sits_next_to_stock_search(monkeypatch):
    assert "stock_vectors" in tools.TOOLS and "stock_search" in tools.TOOLS
    monkeypatch.setattr(stock, "search_vectors", lambda query, n=2, allow_cc_by=False:
                        [{"file": "assets/stock/x.svg", "title": "Horse", "credit": False}])
    out = tools.TOOLS["stock_vectors"]["fn"](None, query="horse", n=1, cc_by=True)
    assert out["found"] is True and out["items"][0]["title"] == "Horse"
