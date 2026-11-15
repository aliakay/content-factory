// Builds countries.json's geometry-derived fields (home bbox, label point) from the vendored world-atlas 50m file.
// Run by build_countries.py (names + codes), which feeds the table on stdin and takes the finished table on stdout.
//   node build_countries.cjs < names.json > countries.json
const Module = require("module"), path = require("path"), fs = require("fs");
const V = path.join(__dirname, "vendor");
const orig = Module._resolveFilename;
Module._resolveFilename = function (r, ...a) { return orig.call(this, r === "d3-array" ? path.join(V, "d3-array.min.js") : r, ...a); };
const d3 = require(path.join(V, "d3-geo.min.js")), topo = require(path.join(V, "topojson-client.min.js"));
const T = JSON.parse(fs.readFileSync(path.join(__dirname, "countries-50m.json"), "utf8"));
const rows = JSON.parse(fs.readFileSync(0, "utf8"));
const byNum = new Map(rows.map((r) => [r.id, r]));
const EXTRA = { Kosovo: "XK", Somaliland: "SO", "N. Cyprus": "CY" };   // atlas shapes without an ISO numeric id
const byIso = new Map(rows.map((r) => [r.iso2, r]));
const polys = new Map();                                              // iso2 -> [Polygon coordinates]
for (const f of topo.feature(T, T.objects.countries).features) {
  const row = f.id ? byNum.get(String(f.id).padStart(3, "0")) : byIso.get(EXTRA[f.properties.name]);
  if (!row) continue;
  const list = polys.get(row.iso2) || polys.set(row.iso2, []).get(row.iso2);
  if (f.geometry.type === "Polygon") list.push(f.geometry.coordinates); else list.push(...f.geometry.coordinates);
}
const poly = (c) => ({ type: "Polygon", coordinates: c });
const R = (x) => Math.round(x * 100) / 100;
for (const row of rows) {
  const list = polys.get(row.iso2);
  if (!list || !list.length) { row.geo = false; continue; }
  row.geo = true;
  const info = list.map((c) => ({ c, a: d3.geoArea(poly(c)), ctr: d3.geoCentroid(poly(c)) })).sort((x, y) => y.a - x.a);
  const main = info[0];
  // home parts: polygons within 30 degrees of the main part (or nearly as big): Alaska and the Aleutians do not stretch the USA
  const home = info.filter((p) => d3.geoDistance(p.ctr, main.ctr) < 0.5236 || p.a >= main.a * 0.5);
  const [[w, s], [e, n]] = d3.geoBounds({ type: "MultiPolygon", coordinates: home.map((p) => p.c) });
  row.bbox = [R(w), R(s), R(e), R(n)];
  let ctr = main.ctr;
  if (!d3.geoContains(poly(main.c), ctr)) {   // a crescent (Chile, Italy): the nearest inside point of a coarse grid
    const [[mw, ms], [me, mn]] = d3.geoBounds(poly(main.c)); let best = null;
    for (let i = 0; i <= 24; i++) for (let j = 0; j <= 24; j++) {
      const p = [mw + ((me < mw ? me + 360 : me) - mw) * i / 24, ms + (mn - ms) * j / 24];
      if (d3.geoContains(poly(main.c), p)) { const d = d3.geoDistance(p, ctr); if (!best || d < best[0]) best = [d, p]; }
    }
    if (best) ctr = best[1];
  }
  if (row.bbox[2] - row.bbox[0] >= 359 || (row.bbox[0] > row.bbox[2] && row.area < 0.5)) row.bbox = [R(ctr[0] - 4), R(ctr[1] - 3), R(ctr[0] + 4), R(ctr[1] + 3)];   // a small state across the antimeridian (Fiji)
  row.lat = R(ctr[1]); row.lon = R(((ctr[0] + 540) % 360) - 180);
  row.area = Math.round(main.a * 6371 * 6371 / 1e4) / 100;   // main part, million km2 (steradians * R^2)
}
process.stdout.write(JSON.stringify(rows));
