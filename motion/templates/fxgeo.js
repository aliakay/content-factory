/* fxgeo.js — maps, flags and country borders from real data, for the explainer scenes (loaded by explainer_shell.html
   after fxlib.js, only for a film whose scenes say FX.geo). Free and offline: nothing is drawn by hand and nothing is
   fetched from a network; the data is vendored under assets/geo/ (see THIRD_PARTY.md):
     countries-110m.json / countries-50m.json   Natural Earth (public domain) through world-atlas (ISC), TopoJSON
     countries.json                             our table: ISO alpha-2/3, numeric id, Turkish + English names, label point, home bbox
     cities.json                                74 cities (Turkish + English names) for pins and routes
     flags/<iso2>.svg                           flag-icons 4x3 (MIT)
     vendor/                                    d3-geo, d3-array, topojson-client (ISC): projections and the TopoJSON decoder
   Written for this factory after the ideas in AI-Video-Factory's geo.ts (fit box, home parts, 110m for the world, 50m
   for regions, great-circle routes, flags from flag-icons, choropleth); the drawing is ours: SVG whose every state is a
   PURE FUNCTION OF t (the renderer asks for frames in any order), no random numbers, no clock, no network at render time.

   API (all times are ABSOLUTE film seconds like the rest of FX; places are country names/ISO codes in Turkish or
   English, city names, [lat, lon] or {lat, lon, label}. NOTE lat FIRST here; fx3d's globe takes [lon, lat]):
     g = FX.geo.map(tl, root, T, {region, bbox, center, zoom, projection, highlight, colors, labels, draw, at, box})
         region: 'Türkiye' | 'europe' | ['Almanya', 'Fransa'] | [['İstanbul'], ...] ; bbox: [w, s, e, n] ; center: place + zoom (1 = world)
         projection: 'mercator' (default) | 'equirect' | 'naturalEarth' (default for the world) | 'globe' (orthographic disc)
         highlight: ['TR', 'Yunanistan'] or [{countries: [...], color, at, label}] ; labels: true (highlighted) | false | [countries]
         draw: 'stroke' (outlines drawn on, default) | 'fade'
     g.highlight(at, countries, {color, label, dur})      g.label(at, countries)
     g.fly(at, {from, to, dur})                           camera move between regions/countries (zooms out mid-way on long hops)
     g.route(at, [place, place, ...], {arc: true|false|'lift', dur, color, marker: 'plane'|'dot', labels, ghost})
     g.pin(at, place, {label, color, side})               g.choropleth(at, {values: {iso: n}, legend: {title, unit}, colors: [lo, hi], labelTop})
     FX.geo.flag(tl, root, at, iso, {x, y, w, wave, label, pole})   FX.geo.flagRow(tl, root, at, [iso, ...], {y, w, names})
   Data helpers: FX.geo.find(q) (country by ISO2/ISO3/numeric/Turkish or English name), FX.geo.city(q), FX.geo.place(p),
     FX.geo.countryRings(iso | 'all', {simplify, detail}) -> [[lat, lon], ...] rings for the 3D kit; FX.geo.contains(iso, lat, lon). */
(function () {
  "use strict";
  const FX = window.FX;
  if (!FX) throw new Error("fxgeo.js: load fxlib.js first");
  const d3 = window.d3, topojson = window.topojson;
  if (!d3 || !d3.geoPath || !topojson) throw new Error("fxgeo.js: d3-geo / topojson-client not loaded");
  const G = (FX.geo = {});
  const NS = "http://www.w3.org/2000/svg";
  const BASE = "/assets/geo/";
  const RAD = Math.PI / 180;
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);   // power3.inOut
  const easeOut = (p) => 1 - Math.pow(1 - clamp(p, 0, 1), 3);
  const lang = () => ((G.language || (typeof document !== "undefined" && document.documentElement.lang) || "en").slice(0, 2).toLowerCase() === "tr" ? "tr" : "en");   // the film's language (<html lang>); G.language overrides
  const wrap180 = (x) => ((((x + 180) % 360) + 360) % 360) - 180;

  /* ------------------------------------------------------------------ data */
  const D = (G._d = { countries: [], cities: [], by: new Map(), cityBy: new Map(), world: {}, ready: false });
  // folding: "Türkiye" = "TURKIYE" = "turkiye"; Turkish dotted/dotless i and the diacritics all fold to plain ASCII
  const fold = (s) => String(s == null ? "" : s).replace(/İ/g, "i").replace(/I/g, "i").replace(/ı/g, "i").toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
  G.fold = fold;
  const EXTRA = { Kosovo: "XK", Somaliland: "SO", "N. Cyprus": "CY" };   // atlas shapes with no ISO numeric id
  const jget = (url) => { const x = new XMLHttpRequest(); x.open("GET", url, false); x.send(); if (x.status !== 200) throw new Error("fxgeo: " + url + " -> " + x.status); return x.responseText; };

  function index(countries, cities) {
    D.countries = countries; D.cities = cities; D.by = new Map(); D.cityBy = new Map();
    const put = (m, k, v) => { k = fold(k); if (k && !m.has(k)) m.set(k, v); };
    for (const c of countries) {
      put(D.by, c.iso2, c); put(D.by, c.iso3, c); D.by.set("num " + c.num, c);   // codes first: 'in' is India, not a preposition
    }
    for (const c of countries) { put(D.by, c.tr, c); put(D.by, c.en, c); (c.alt || []).forEach((a) => put(D.by, a, c)); }
    for (const c of cities) { put(D.cityBy, c.tr, c); put(D.cityBy, c.en, c); }
    D.iso = new Map(countries.map((c) => [c.iso2, c]));
  }
  function decode(detail, topo) {
    const num = new Map(D.countries.map((c) => [c.num, c.iso2]));
    const feats = topojson.feature(topo, topo.objects.countries).features.map((f, i) => {
      const iso = f.id != null ? num.get(String(f.id).padStart(3, "0")) : EXTRA[f.properties.name];
      return { iso: iso || null, f, i, bounds: null };
    });
    D.world[detail] = feats;
  }
  /* async: fetch the data once before the scenes are built (explainer_shell.html awaits it) */
  G.load = async () => {
    if (D.ready) return G;
    const [c, ci, w1, w5] = await Promise.all(["countries.json", "cities.json", "countries-110m.json", "countries-50m.json"].map((f) => fetch(BASE + f).then((r) => { if (!r.ok) throw new Error(f + " " + r.status); return r.json(); })));
    // label widths are measured on the page: load the faces first, or the first frame measures the fallback font
    if (typeof document !== "undefined" && document.fonts) await Promise.all(['800 40px "Inter Tight"', '900 40px "Inter Tight"', '900 100px Anton'].map((f) => document.fonts.load(f, "AÇĞİÖŞÜçğıöşüÂÎÛ0123456789").catch(() => {})));
    return G.init(c, ci, { "110m": w1, "50m": w5 });
  };
  /* sync init from already parsed data (tests and Node use it) */
  G.init = (countries, cities, topos) => { index(countries, cities); for (const k in topos) decode(k, topos[k]); D.ready = true; return G; };
  const need = () => { if (!D.ready) throw new Error("FX.geo: data not loaded (the page loads it when a scene says FX.geo)"); };

  /* ------------------------------------------------------------------ lookup */
  G.find = (q) => {
    need();
    if (q == null) return null;
    if (typeof q === "object" && q.iso2) return q;
    const s = String(q).trim();
    if (/^\d{3}$/.test(s)) return D.by.get("num " + s) || null;
    return D.by.get(fold(s)) || null;
  };
  G.city = (q) => { need(); return q == null ? null : D.cityBy.get(fold(typeof q === "object" ? q.en || q.tr : q)) || null; };
  /* a place -> {lat, lon, label, kind, rec} (label in the film's language) */
  G.place = (p) => {
    need();
    const L = lang();
    if (p && typeof p === "object" && !Array.isArray(p) && p.lat != null) return { lat: +p.lat, lon: +p.lon, label: p.label || "", kind: "point" };
    if (Array.isArray(p) && p.length >= 2 && typeof p[0] === "number") return { lat: +p[0], lon: +p[1], label: p[2] || "", kind: "point" };
    if (p && p.kind) return p;
    const city = G.city(p);
    if (city && !(typeof p === "string" && p.length === 2 && G.find(p))) return { lat: city.lat, lon: city.lon, label: city[L], kind: "city", rec: city };
    const c = G.find(p);
    if (c) return { lat: c.lat, lon: c.lon, label: c[L], kind: "country", rec: c };
    throw new Error("FX.geo: unknown place " + JSON.stringify(p));
  };
  G.name = (iso, l) => { const c = G.find(iso); return c ? c[l || lang()] : String(iso); };

  /* named regions: [west, south, east, north] */
  const REGIONS = {
    world: [-180, -58, 180, 84], europe: [-12, 34, 42, 71], asia: [26, -10, 150, 56], africa: [-20, -36, 52, 38],
    north_america: [-170, 7, -50, 72], south_america: [-83, -56, -34, 13], oceania: [110, -48, 180, -2], middle_east: [25, 12, 63, 42],
    balkans: [13, 35, 31, 47], caucasus: [38, 38, 51, 45], mediterranean: [-10, 29, 37, 46], black_sea: [26, 39, 43, 47],
    central_asia: [46, 35, 88, 56], scandinavia: [4, 54, 32, 71], east_asia: [95, 18, 146, 54], southeast_asia: [92, -11, 142, 28],
    south_asia: [60, 5, 98, 38], latin_america: [-118, -56, -34, 33], eastern_europe: [10, 40, 50, 70], western_europe: [-12, 35, 18, 61],
  };
  const REGION_TR = {
    dunya: "world", avrupa: "europe", asya: "asia", afrika: "africa", kuzey_amerika: "north_america", guney_amerika: "south_america",
    okyanusya: "oceania", orta_dogu: "middle_east", balkanlar: "balkans", kafkasya: "caucasus", akdeniz: "mediterranean",
    karadeniz: "black_sea", orta_asya: "central_asia", iskandinavya: "scandinavia", dogu_asya: "east_asia",
    guneydogu_asya: "southeast_asia", guney_asya: "south_asia", latin_amerika: "latin_america", dogu_avrupa: "eastern_europe", bati_avrupa: "western_europe",
  };
  const regionKey = (s) => { const k = fold(s).replace(/ /g, "_"); return REGIONS[k] ? k : REGION_TR[k] || null; };
  G.regions = Object.keys(REGIONS);

  /* a view spec -> bbox [w, s, e, n] (e may pass 180: the box can cross the antimeridian) */
  function bboxOf(spec) {
    if (spec == null) return REGIONS.world.slice();
    if (typeof spec === "string") {
      const rk = regionKey(spec);
      if (rk) return REGIONS[rk].slice();
      const city = G.city(spec);
      if (city && !G.find(spec)) return [city.lon - 3, city.lat - 2, city.lon + 3, city.lat + 2];
      const c = G.find(spec);
      if (!c) throw new Error("FX.geo: unknown region or country " + JSON.stringify(spec));
      const b = c.bbox.slice();
      if (b[2] < b[0]) b[2] += 360;
      return b;
    }
    if (Array.isArray(spec) && spec.length === 4 && spec.every((x) => typeof x === "number")) return spec.slice();
    const list = Array.isArray(spec) && !(spec.length === 2 && typeof spec[0] === "number") ? spec : [spec];
    const boxes = list.map((x) => (typeof x === "string" ? bboxOf(x) : (() => { const p = G.place(x); return [p.lon - 3, p.lat - 2, p.lon + 3, p.lat + 2]; })()));
    const mid0 = (boxes[0][0] + boxes[0][2]) / 2;
    let w = Infinity, e = -Infinity, s = Infinity, n = -Infinity;
    for (const b of boxes) {
      const m = (b[0] + b[2]) / 2, sh = Math.round((mid0 - m) / 360) * 360;   // unwrap to the first one's side of the globe
      w = Math.min(w, b[0] + sh); e = Math.max(e, b[2] + sh); s = Math.min(s, b[1]); n = Math.max(n, b[3]);
    }
    return [w, s, e, n];
  }
  G.bbox = bboxOf;

  /* ------------------------------------------------------------------ projections and the camera */
  const PROJ = { mercator: d3.geoMercator, equirect: d3.geoEquirectangular, equirectangular: d3.geoEquirectangular, naturalEarth: d3.geoNaturalEarth1, naturalearth: d3.geoNaturalEarth1, globe: d3.geoOrthographic, orthographic: d3.geoOrthographic };
  const KINDS = { orthographic: "globe", equirectangular: "equirect", naturalearth: "naturalEarth" };
  const kindOf = (k) => { k = KINDS[k] || k || "mercator"; if (!PROJ[k]) throw new Error("FX.geo: unknown projection " + k); return k; };
  const MIN_SPAN = [6, 4];   // a tiny state still gets a map, not a pixel
  function padBox(b, pad) {   // pad: share of the span added around (default 0.18: the neighbours show)
    let [w, s, e, n] = b;
    const cx = (w + e) / 2, cy = (s + n) / 2;
    let sw = Math.max(e - w, MIN_SPAN[0]) * (1 + pad), sh = Math.max(n - s, MIN_SPAN[1]) * (1 + pad);
    return [cx - sw / 2, clamp(cy - sh / 2, -84, 84), cx + sw / 2, clamp(cy + sh / 2, -84, 84)];
  }
  /* a camera {lon, lat, k} that frames bbox in the box: lon/lat = the point at the middle of the box, k = scale */
  function fitCam(kind, bbox, box, pad) {
    const [w, s, e, n] = padBox(bbox, pad == null ? 0.18 : pad);
    const lon0 = wrap180((w + e) / 2), lat0 = (s + n) / 2;
    if (kind === "globe") {
      const ctr = [lon0, lat0];
      const pts = [[w, s], [e, s], [w, n], [e, n], [w, lat0], [e, lat0], [lon0, s], [lon0, n]];
      const rho = Math.max(0.5, ...pts.map((p) => d3.geoDistance(ctr, p)));
      return { lon: lon0, lat: lat0, k: Math.min(box.w, box.h) / 2 / Math.sin(Math.min(Math.PI / 2, rho * 1.5)) };
    }
    const pts = [];
    for (let i = 0; i <= 6; i++) for (const lat of [s, n]) pts.push([lerp(w, e, i / 6), lat]);
    for (let j = 0; j <= 4; j++) for (const lon of [w, e]) pts.push([lon, lerp(s, n, j / 4)]);
    const P = PROJ[kind]().rotate([-lon0, 0]).fitExtent([[box.x, box.y], [box.x + box.w, box.y + box.h]], { type: "MultiPoint", coordinates: pts });
    const c = P.invert([box.x + box.w / 2, box.y + box.h / 2]);
    return { lon: lon0, lat: c[1], k: P.scale() };
  }
  function makeProj(kind, cam, box, W, H) {
    const P = PROJ[kind]();
    if (kind === "globe") return P.rotate([-cam.lon, -cam.lat]).scale(cam.k).translate([box.x + box.w / 2, box.y + box.h / 2]).clipAngle(90);
    return P.rotate([-cam.lon, 0]).center([0, cam.lat]).scale(cam.k).translate([box.x + box.w / 2, box.y + box.h / 2]).clipExtent([[-40, -40], [W + 40, H + 40]]);
  }
  /* the camera between two cams: shortest way round in longitude, scale in logs, a pull-out on a long hop */
  function lerpCam(a, b, p, kind, box) {
    const e = ease(p), dl = wrap180(b.lon - a.lon);
    const dist = d3.geoDistance([a.lon, a.lat], [b.lon, b.lat]);
    const kmin = Math.min(a.k, b.k);
    const rel = kind === "globe" ? dist / 0.6 : (dist * kmin) / Math.min(box.w, box.h);
    const bump = rel > 0.7 ? (kind === "globe" ? Math.min(0.5, Math.log(1 + rel * 0.3)) : Math.min(1.1, Math.log(1 + rel * 0.55))) : 0;
    const lk = lerp(Math.log(a.k), Math.log(b.k), e) - bump * Math.sin(Math.PI * e);
    return { lon: wrap180(a.lon + dl * e), lat: lerp(a.lat, b.lat, e), k: Math.max(Math.exp(lk), kmin * 0.3) };
  }

  /* ------------------------------------------------------------------ a map */
  const svgEl = (tag, attrs, parent) => { const n = document.createElementNS(NS, tag); for (const k in attrs || {}) n.setAttribute(k, attrs[k]); if (parent) parent.appendChild(n); return n; };
  const divEl = (parent, css, html) => { const d = document.createElement("div"); Object.assign(d.style, css || {}); if (html != null) d.textContent = html; parent.appendChild(d); return d; };
  const STYLE = {   // palette-driven: the film's CSS variables, so a map in a cold film is cold and in a paper film is paper
    land: "color-mix(in srgb, var(--ink, #f4efe6) 15%, var(--bg, #0f1220))",
    border: "color-mix(in srgb, var(--ink, #f4efe6) 38%, var(--bg, #0f1220))",
    sea: "color-mix(in srgb, var(--accent2, #7c5cff) 14%, var(--bg, #0f1220))",
    hi: "var(--accent, #ffb347)", hi2: "var(--hot, #ff5a5f)", ink: "var(--ink, #f4efe6)", muted: "var(--muted, #9aa3b5)", bg: "var(--bg, #0f1220)",
  };
  G.style = STYLE;
  const PLANE = "M0,-17 L4,-5 L17,3 L17,7 L4,4 L3,12 L8,16 L8,18 L0,16.5 L-8,18 L-8,16 L-3,12 L-4,4 L-17,7 L-17,3 L-4,-5 Z";

  /* ---- historical borders: /work/geo/history/<year>.json is written by factory/geo.py (Cliopatria, CC BY 4.0) ---- */
  const POLITY_TR = {   // Turkish names -> the Cliopatria polity title
    osmanli: "Ottoman Empire", "osmanli imparatorlugu": "Ottoman Empire", bizans: "Byzantine Empire", "dogu roma": "Byzantine Empire",
    roma: "Roman Empire", "roma imparatorlugu": "Roman Empire", "bati roma": "Western Roman Empire", selcuklu: "Great Seljuk Empire", "buyuk selcuklu": "Great Seljuk Empire",
    mogol: "Mongol Empire", "mogol imparatorlugu": "Mongol Empire", "altin orda": "Golden Horde", timur: "Timurid Empire", safevi: "Safavid Dynasty",
    memluk: "Mamluk Sultanate", emevi: "Umayyad Caliphate", abbasi: "Abbasid Caliphate", "kutsal roma": "Holy Roman Empire", makedonya: "Macedonian Empire",
    ahameni: "Achaemenid Empire", hitit: "Hittites", babur: "Mughal Empire", "rus imparatorlugu": "Russian Empire", karaman: "Beylik of Karaman",
    venedik: "Republic of Venice", ceneviz: "Republic of Genoa", kartaca: "Carthage", sasani: "Sasanian Empire", "kharezm": "Khwarazmian Empire",
  };
  const histCache = new Map();
  function loadHistory(year) {
    if (histCache.has(year)) return histCache.get(year);
    let h = null;
    try {
      const j = JSON.parse(jget("/work/geo/history/" + year + ".json"));
      const pol = j.polities.map((p) => {
        const polys = p.polygons.map((poly) => (d3.geoArea({ type: "Polygon", coordinates: poly }) > 2 * Math.PI ? poly.map((r) => r.slice().reverse()) : poly));   // d3 wants spherical winding
        const geom = { type: "MultiPolygon", coordinates: polys };
        const big = polys.map((c) => [d3.geoArea({ type: "Polygon", coordinates: c }), c]).sort((a, b) => b[0] - a[0])[0];
        return { name: p.name, key: fold(p.name), wiki: fold(p.wikipedia || ""), geom, area: d3.geoArea(geom), cen: d3.geoCentroid({ type: "Polygon", coordinates: big[1] }), d: "", el: null };
      });
      h = { year, polities: pol, credit: j.credit };
    } catch (e) { console.error("geo: no historical borders for " + year + " (run factory.geo.prepare): the map shows coastlines only"); }
    histCache.set(year, h);
    return h;
  }
  const findPolity = (h, q) => {
    if (!h) return null;
    const f = fold(q), want = fold(POLITY_TR[f] || q);
    return h.polities.find((p) => p.key === want || p.wiki === want) || (want.length >= 4 ? h.polities.find((p) => p.key.includes(want)) || null : null);
  };
  const yearText = (y) => (y < 0 ? (lang() === "tr" ? "MÖ " + -y : -y + " BC") : lang() === "tr" ? "MS " + y : "" + y);

  G.map = (tl, root, T, o = {}) => {
    need();
    T = T && typeof T === "object" ? T : { start: +T || 0, end: 1e9 };   // (tl, root, at, o) works too
    const W = FX._W || 1080, H = FX._H || 1920, tall = H > W, L = lang();
    const at0 = o.at != null ? o.at : T.start || 0;
    const box = o.box ? { x: o.box[0], y: o.box[1], w: o.box[2], h: o.box[3] }
      : tall ? { x: 50, y: 230, w: W - 100, h: 1240 } : { x: 100, y: 70, w: W - 200, h: 760 };   // the platform-safe area; captions sit below
    const safe = tall ? { x0: 56, x1: W - 56, y0: 175, y1: 1500 } : { x0: 90, y0: 60, x1: W - 90, y1: 860 };
    const hist = o.year != null ? loadHistory(+o.year) : null;
    const colors = Object.assign({}, STYLE, o.colors || {});
    if (o.year != null && o.borders !== true) colors.border = colors.land;   // a map of another year never shows today's borders
    // the view: explicit region / bbox / centre+zoom; with a globe or the world the default is the whole world
    let kind = kindOf(o.projection || (o.region == null && o.bbox == null && o.center == null ? "naturalEarth" : (typeof o.region === "string" && regionKey(o.region) === "world" ? "naturalEarth" : "mercator")));
    let cam0;
    if (o.center != null) {
      const p = G.place(o.center), z = Math.max(0.3, o.zoom || 4);   // zoom 1 = the whole world (globe: the whole disc) across the box
      cam0 = { lon: p.lon, lat: clamp(p.lat, -80, 80), k: kind === "globe" ? Math.min(box.w, box.h) / 2 * z : box.w * z / (2 * Math.PI) };
    } else cam0 = fitCam(kind, o.bbox || bboxOf(o.region == null ? "world" : o.region), box, o.pad);
    const antarctica = o.antarctica != null ? o.antarctica : kind === "globe";

    const svg = FX.svg(root, W, H);
    svg.style.pointerEvents = "none";
    const gSea = svgEl("g", {}, svg), gGrat = svgEl("g", {}, svg), gLand = svgEl("g", {}, svg), gHist = svgEl("g", {}, svg), gHi = svgEl("g", {}, svg), gRt = svgEl("g", {}, svg), gPin = svgEl("g", {}, svg);
    const over = divEl(root, { position: "absolute", left: 0, top: 0, width: W + "px", height: H + "px", pointerEvents: "none" });
    const seaEl = svgEl("path", { style: `fill:${kind === "globe" ? colors.sea : "none"};stroke:${kind === "globe" ? "color-mix(in srgb, var(--accent, #ffb347) 45%, transparent)" : "none"};stroke-width:3` }, gSea);
    const gratEl = svgEl("path", { style: `fill:none;stroke:${colors.border};stroke-width:1;opacity:${o.grid === false ? 0 : kind === "globe" || kind === "naturalEarth" ? 0.5 : 0}` }, gGrat);
    const grat = d3.geoGraticule10();
    const sphere = { type: "Sphere" };

    const fs = (tall ? 1 : 0.8);
    const LABEL = { font: `800 ${Math.round(42 * fs)}px "Inter Tight", Poppins, sans-serif`, color: "var(--ink, #f4efe6)", halo: 9 };
    const mkLabel = (text, o2 = {}) => {
      const d = divEl(over, { position: "absolute", left: 0, top: 0, whiteSpace: "nowrap", font: o2.font || LABEL.font, color: o2.color || LABEL.color, lineHeight: 1.05,
        letterSpacing: ".01em", textAlign: "center", opacity: 0, paintOrder: "stroke fill", webkitTextStroke: `${LABEL.halo}px var(--bg, #0f1220)` }, text);
      if (o2.pill) Object.assign(d.style, { padding: `${Math.round(10 * fs)}px ${Math.round(22 * fs)}px`, borderRadius: "999px", background: o2.pill, color: o2.pillInk || "var(--bg, #0f1220)", webkitTextStroke: "0", font: o2.font || `900 ${Math.round(38 * fs)}px "Inter Tight", Poppins, sans-serif` });
      return d;
    };

    /* ---- state declared by the builder calls: everything below is evaluated from t ---- */
    const S = { moves: [], paints: [], routes: [], pins: [], labels: [], legend: null, polHi: [] };
    const introDur = o.introDur || 1.3, draw = o.draw || "stroke";
    const elements = new Map();                    // feature key -> {land, hi}
    const orderOf = new Map();                     // iso -> 0..1 (distance from the opening centre): the draw-on radiates
    const centre0 = [cam0.lon, cam0.lat];
    const ds = D.countries.map((c) => [c.iso2, d3.geoDistance(centre0, [c.lon, c.lat])]).sort((a, b) => a[1] - b[1]);
    ds.forEach(([iso], i) => orderOf.set(iso, i / Math.max(1, ds.length - 1)));

    const camAt = (t) => {
      let cam = cam0;
      for (const m of S.moves) {   // sorted by start; each leaves from where the previous one ended
        if (t <= m.at) return cam;
        if (t < m.at + m.dur) return lerpCam(cam, m.to, (t - m.at) / m.dur, kind, box);
        cam = m.to;
      }
      return cam;
    };
    const paintAt = (iso, t) => {   // the last paint that has started on this country, with its alpha
      let res = null;
      for (const p of S.paints) {
        const f = p.fill[iso];
        if (f == null) continue;
        const a = (t - p.at - (p.stagger[iso] || 0)) / p.dur;
        if (a > 0) res = { fill: f, a: ease(clamp(a, 0, 1)), p };
      }
      return res;
    };

    let lastKey = "", proj = null, path = null, ids = [], stale = [];
    const keep = (f) => (antarctica || f.iso !== "AQ");
    function projectAll(cam, detail) {
      proj = makeProj(kind, cam, box, W, H);
      path = d3.geoPath(proj).digits(1);
      const feats = D.world[detail].filter(keep);
      ids = []; stale = [];
      for (const ft of feats) {
        const k = detail + ":" + ft.i;
        let e = elements.get(k);
        if (!e) { e = { ft, land: null, hi: null, d: "" }; elements.set(k, e); }
        e.d = path(ft.f) || "";
        ids.push(e);
      }
      for (const [k, e] of elements) if (!k.startsWith(detail + ":")) { e.d = ""; if (e.land) { stale.push(e); } }
      if (hist) for (const pl of hist.polities) pl.d = path(pl.geom) || "";
      seaEl.setAttribute("d", kind === "globe" ? path(sphere) : "");
      gratEl.setAttribute("d", path(grat) || "");
    }
    const setStyle = (el, v) => { if (el._s !== v) { el._s = v; el.setAttribute("style", v); } };
    const setAttr = (el, k, v) => { const key = "_" + k; if (el[key] !== v) { el[key] = v; el.setAttribute(k, v); } };

    const bordW = tall ? 1.6 : 1.3;
    function paintLand(t, cam, detail) {
      const p0 = clamp((t - at0) / introDur, 0, 1);
      for (const e of stale) { setAttr(e.land, "d", ""); setAttr(e.hi, "d", ""); }   // the other resolution's shapes
      for (const e of ids) {
        if (!e.land) { e.land = svgEl("path", { pathLength: 1 }, gLand); e.hi = svgEl("path", { pathLength: 1 }, gHi); }
        const d = e.d;
        setAttr(e.land, "d", d); setAttr(e.hi, "d", d);
        const iso = e.ft.iso, ord = iso ? orderOf.get(iso) || 0 : 0.5;
        const lp = clamp(p0 * 1.7 - ord * 0.7, 0, 1);   // country-local intro progress, radiating from the centre
        if (draw === "stroke") {
          const off = lp >= 1 ? "none" : "1 1";
          setStyle(e.land, `fill:${colors.land};fill-opacity:${(clamp((lp - 0.55) / 0.45, 0, 1)).toFixed(3)};stroke:${colors.border};stroke-width:${bordW};stroke-linejoin:round;stroke-dasharray:${off};stroke-dashoffset:${(1 - Math.min(1, lp * 1.8)).toFixed(4)};opacity:${lp > 0 ? 1 : 0}`);
        } else setStyle(e.land, `fill:${colors.land};stroke:${colors.border};stroke-width:${bordW};stroke-linejoin:round;opacity:${lp.toFixed(3)}`);
        const pa = iso ? paintAt(iso, t) : null;
        if (pa && d) setStyle(e.hi, `fill:color-mix(in srgb, ${pa.fill} ${(pa.a * 100).toFixed(1)}%, transparent);stroke:color-mix(in srgb, ${pa.p.stroke} ${(pa.a * 100).toFixed(1)}%, transparent);stroke-width:${(bordW * 2.1).toFixed(2)};stroke-linejoin:round`);
        else setStyle(e.hi, "display:none");
      }
    }

    const PCOL = ["var(--accent, #ffb347)", "var(--accent2, #7c5cff)", "var(--hot, #ff5a5f)", "color-mix(in srgb, var(--accent2, #7c5cff) 50%, var(--accent, #ffb347))", "color-mix(in srgb, var(--ink, #f4efe6) 55%, var(--bg, #0f1220))", "color-mix(in srgb, var(--hot, #ff5a5f) 55%, var(--accent, #ffb347))"];
    function paintHist(t) {
      if (!hist) return;
      const n = hist.polities.length, hl = S.polHi.filter((h) => t >= h.at);
      hist.polities.forEach((pl, i) => {
        if (!pl.el) { pl.el = svgEl("path", {}, gHist); let h = 0; for (const c of pl.key) h = (h * 31 + c.charCodeAt(0)) >>> 0; pl.col = PCOL[h % PCOL.length]; }
        setAttr(pl.el, "d", pl.d);
        const on = hl.find((h) => h.pl === pl), a = clamp((t - at0 - 0.35 - (i / n) * 0.7) / 0.5, 0, 1);
        const hlOn = hl.length ? ease(clamp((t - hl[0].at) / 0.5, 0, 1)) : 0;
        const op = on ? 0.6 + 0.35 * ease(clamp((t - on.at) / 0.5, 0, 1)) : 0.6 - 0.32 * hlOn;
        setStyle(pl.el, `fill:${on ? on.color : pl.col};fill-opacity:${(a * op).toFixed(3)};stroke:var(--ink, #f4efe6);stroke-width:${on ? 3 : 1.2};stroke-opacity:${(a * (on ? 0.9 : 0.45)).toFixed(3)};stroke-linejoin:round`);
      });
      if (S.year) S.year.style.opacity = clamp((t - at0 - 0.2) / 0.5, 0, 1).toFixed(3);
    }

    /* screen position of a place under the current projection; null when behind the globe */
    const behind = (cam, p) => kind === "globe" && d3.geoDistance([cam.lon, cam.lat], [p.lon, p.lat]) > Math.PI / 2 - 0.03;
    const scr = (p) => proj([p.lon, p.lat]);
    const onStage = (xy) => xy && xy[0] > 10 && xy[0] < W - 10 && xy[1] > 10 && xy[1] < H - 10;
    const placeLabel = (el, x, y, a, opt = {}) => {
      if (!el._w) el._w = el.offsetWidth || 0;
      if (!el._h) el._h = el.offsetHeight || 0;
      const w = el._w, h = el._h;
      let lx = x - w / 2, ly = y - h / 2 + (opt.dy || 0);
      lx = clamp(lx, safe.x0, Math.max(safe.x0, safe.x1 - w)); ly = clamp(ly, safe.y0, Math.max(safe.y0, safe.y1 - h));
      el.style.opacity = a > 0.001 ? a.toFixed(3) : "0";
      const tr = `translate(${lx.toFixed(1)}px,${ly.toFixed(1)}px)`;
      if (el._tr !== tr) { el._tr = tr; el.style.transform = tr; }
      return [lx, ly, w, h];
    };

    function paintOver(t, cam) {
      // country labels: shown with their paint, nudged apart when two collide (deterministic greedy pass)
      const placed = [];
      for (const lb of S.labels) {
        const a = clamp((t - lb.at) / 0.4, 0, 1);
        const p = lb.p;
        if (a <= 0 || behind(cam, p)) { lb.el.style.opacity = "0"; continue; }
        const xy = scr(p);
        if (!onStage(xy)) { lb.el.style.opacity = "0"; continue; }
        const el = lb.el; if (!el._w) { el._w = el.offsetWidth || 0; el._h = el.offsetHeight || 0; }
        let dy = 0, r;
        for (let n = 0; n < 6; n++) {
          r = [xy[0] - el._w / 2, xy[1] - el._h / 2 + dy, el._w, el._h];
          const hit = placed.find((q) => r[0] < q[0] + q[2] && q[0] < r[0] + r[2] && r[1] < q[1] + q[3] && q[1] < r[1] + r[3]);
          if (!hit) break;
          dy = hit[1] + hit[3] - (xy[1] - el._h / 2) + 4;
        }
        placed.push(placeLabel(el, xy[0], xy[1], easeOut(a), { dy }));
      }
      // pins: a dot with a ping, and a pill label above (below when the dot is near the top)
      for (const pn of S.pins) {
        const a = clamp((t - pn.at) / 0.5, 0, 1), xy = !behind(cam, pn.p) ? scr(pn.p) : null;
        if (!xy || a <= 0) { pn.g.setAttribute("opacity", 0); if (pn.el) pn.el.style.opacity = "0"; continue; }
        if (!onStage(xy)) { pn.g.setAttribute("opacity", 0); if (pn.el) pn.el.style.opacity = "0"; continue; }
        const sc = FX.spring(t - pn.at, FX.SPRINGS.bouncy), ph = ((t - pn.at) * 0.9) % 1;
        pn.g.setAttribute("opacity", 1);
        pn.g.setAttribute("transform", `translate(${xy[0].toFixed(1)} ${xy[1].toFixed(1)})`);
        pn.dot.setAttribute("r", (pn.r * clamp(sc, 0, 1.4)).toFixed(2));
        pn.ring.setAttribute("r", (pn.r * (1 + ph * 3)).toFixed(2));
        pn.ring.setAttribute("opacity", (a * (1 - ph) * 0.8).toFixed(3));
        if (pn.el) {
          const below = xy[1] < safe.y0 + 130 || pn.side === "below";
          const el = pn.el; if (!el._w) { el._w = el.offsetWidth || 0; el._h = el.offsetHeight || 0; }
          const k = clamp((t - pn.at - 0.18) / 0.35, 0, 1);
          placeLabel(el, xy[0], xy[1] + (below ? 1 : -1) * (pn.r + el._h / 2 + 14 + (1 - easeOut(k)) * 14), easeOut(k));
        }
      }
    }

    /* routes: screen polyline of the geodesic (or straight, or lifted) between stops, drawn up to progress p */
    function routePoly(rt, cam) {
      if (rt.mode !== "geo") {   // straight in the picture plane between the projected stops, bulged upward for 'lift'
        const out = [], stops = rt.stops.map((s) => proj([s.lon, s.lat]));
        for (let l = 0; l + 1 < stops.length; l++) {
          const a = stops[l], b = stops[l + 1];
          if (!a || !b) { for (let i = 0; i <= rt.per; i++) out.push(null); continue; }
          const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
          let px = -dy / len, py = dx / len;
          if (py > 0) { px = -px; py = -py; }   // the bulge goes up the picture
          const bulge = rt.mode === "lift" ? Math.min(0.3 * len, 300) : 0, cx = (a[0] + b[0]) / 2 + px * bulge, cy = (a[1] + b[1]) / 2 + py * bulge;
          for (let i = 0; i <= rt.per; i++) { const u = i / rt.per, v = 1 - u; out.push([v * v * a[0] + 2 * u * v * cx + u * u * b[0], v * v * a[1] + 2 * u * v * cy + u * u * b[1]]); }
        }
        return out;
      }
      const pts = rt.samples.map((q) => (behind(cam, { lon: q[0], lat: q[1] }) ? null : proj(q)));
      const jump = Math.max(W, H) * 0.55;   // a hop over the antimeridian must not stripe the map
      pts.cuts = [];
      for (let i = 1; i < pts.length; i++) if (pts[i] && pts[i - 1] && Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) > jump) pts.cuts.push(i);
      return pts;
    }
    const dOf = (poly, upto) => {
      const cuts = new Set(poly.cuts || []);
      let d = "", pen = false;
      const lim = Math.min(poly.length, Math.floor(upto) + 1);
      for (let i = 0; i < lim; i++) {
        const q = poly[i]; if (!q) { pen = false; continue; }
        d += (pen && !cuts.has(i) ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1); pen = true;
      }
      // the fractional last step
      const f = upto - Math.floor(upto), i = Math.floor(upto);
      if (f > 0 && poly[i] && poly[i + 1] && !cuts.has(i + 1)) d += "L" + lerp(poly[i][0], poly[i + 1][0], f).toFixed(1) + " " + lerp(poly[i][1], poly[i + 1][1], f).toFixed(1);
      return d;
    };
    function paintRoutes(t, cam) {
      for (const rt of S.routes) {
        const p = clamp((t - rt.at) / rt.dur, 0, 1), e = p;
        const poly = routePoly(rt, cam);
        const last = poly.length - 1;
        rt.ghost.setAttribute("d", dOf(poly, last));
        rt.line.setAttribute("d", p > 0 ? dOf(poly, e * last) : "");
        rt.g.setAttribute("opacity", t < rt.at ? 0 : 1);
        // the marker rides the line; its heading comes from the two samples around it
        const i = clamp(e * last, 0, last - 1e-6), i0 = Math.floor(i), f = i - i0;
        const a = poly[i0], b = poly[Math.min(last, i0 + 1)];
        if (a && b && p > 0) {
          const x = lerp(a[0], b[0], f), y = lerp(a[1], b[1], f);
          let ang = Math.atan2(b[1] - a[1], b[0] - a[0]) / RAD + 90;
          if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-3 && poly[Math.max(0, i0 - 1)]) { const c = poly[Math.max(0, i0 - 1)]; ang = Math.atan2(a[1] - c[1], a[0] - c[0]) / RAD + 90; }
          rt.mk.setAttribute("transform", `translate(${x.toFixed(1)} ${y.toFixed(1)})` + (rt.marker === "plane" ? ` rotate(${ang.toFixed(1)})` : ""));
          rt.mk.setAttribute("opacity", p >= 1 && rt.marker === "plane" && !rt.keepMarker ? clamp(1 - (t - rt.at - rt.dur) / 0.4, 0, 1) : 1);
        } else rt.mk.setAttribute("opacity", 0);
        // stops: a dot when the marker arrives, then the name
        rt.stopEls.forEach((s, j) => {
          const arrive = rt.at + rt.dur * rt.cum[j] , a2 = clamp((t - arrive) / 0.4, 0, 1);
          const xy = !behind(cam, s.p) ? proj([s.p.lon, s.p.lat]) : null;
          if (!onStage(xy) || a2 <= 0) { s.dot.setAttribute("opacity", 0); if (s.el) s.el.style.opacity = "0"; return; }
          s.dot.setAttribute("opacity", 1);
          s.dot.setAttribute("transform", `translate(${xy[0].toFixed(1)} ${xy[1].toFixed(1)}) scale(${clamp(FX.spring(t - arrive, FX.SPRINGS.bouncy), 0, 1.4).toFixed(3)})`);
          if (s.el) { if (!s.el._w) { s.el._w = s.el.offsetWidth || 0; s.el._h = s.el.offsetHeight || 0; } const up = s.side === "below" ? 1 : -1; placeLabel(s.el, xy[0], xy[1] + up * (s.el._h / 2 + 22), easeOut(a2)); }
        });
      }
    }

    function paintLegend(t) {
      const lg = S.legend; if (!lg) return;
      lg.el.style.opacity = clamp((t - lg.at) / 0.5, 0, 1).toFixed(3);
    }

    const paint = (t) => {
      if (!root.isConnected || getComputedStyle(root).display === "none") return;
      const cam = camAt(t);
      const spanDeg = kind === "globe" ? Math.asin(clamp(Math.min(box.w, box.h) / 2 / cam.k, 0, 1)) / RAD : (W / cam.k) / RAD;
      const detail = spanDeg < (kind === "globe" ? 55 : 80) ? "50m" : "110m";
      const key = [cam.lon.toFixed(3), cam.lat.toFixed(3), cam.k.toFixed(2), detail].join();
      if (key !== lastKey) { projectAll(cam, detail); lastKey = key; }
      paintLand(t, cam, detail);
      paintHist(t);
      paintRoutes(t, cam);
      paintOver(t, cam);
      paintLegend(t);
    };
    FX.onFrame(paint);
    // the map arrives with the scene (an entry the motion lint sees); the geometry draws on from `at`
    tl.fromTo(svg, { opacity: 0 }, { opacity: 1, duration: 0.25, ease: "power1.out" }, Math.max(0, at0 - 0.0));

    /* ---- the handle ---- */
    const g = { svg, over, box, kind, cam: camAt, projection: () => proj, screen: (p) => { const q = G.place(p); return proj ? proj([q.lon, q.lat]) : null; } };
    const asList = (c) => (Array.isArray(c) && !(c.length === 2 && typeof c[0] === "number") ? c : [c]);
    const keysOf = (list) => asList(list).map((c) => { const r = G.find(c); if (!r) throw new Error("FX.geo: unknown country " + JSON.stringify(c)); return r.iso2; });
    const labelOf = (iso, at, text) => {
      const r = D.iso.get(iso);
      const el = mkLabel(text || r[L]);
      S.labels.push({ el, at, p: { lat: r.lat, lon: r.lon, kind: "country" } });
    };

    g.highlight = (at, countries, h = {}) => {
      if (hist) {   // on a map of another year a name is a polity first (Osmanlı, Bizans, Ottoman Empire), a modern country second
        const rest = [];
        asList(countries).forEach((c, i) => {
          const pl = typeof c === "string" ? findPolity(hist, c) : null;
          if (!pl) { rest.push(c); return; }
          S.polHi.push({ at: at + i * 0.12, pl, color: h.color || (S.polHi.length % 2 ? colors.hi2 : colors.hi) });
          const lab = h.label != null ? h.label : Array.isArray(o.labels) ? false : o.labels;
          if (lab !== false) { const el = mkLabel(typeof lab === "string" ? lab : (typeof c === "string" ? c : pl.name)); S.labels.push({ el, at: at + i * 0.12 + 0.3, p: { lat: pl.cen[1], lon: pl.cen[0], kind: "polity" } }); }
        });
        if (!rest.length) return g;
        countries = rest;
      }
      const keys = keysOf(countries);
      const color = h.color || colors.hi, fill = {}, stagger = {};
      keys.forEach((k, i) => { fill[k] = color; stagger[k] = i * (h.stagger != null ? h.stagger : 0.12); });
      S.paints.push({ at, dur: h.dur || 0.6, fill, stagger, stroke: h.stroke || colors.ink });
      S.paints.sort((a, b) => a.at - b.at);
      const lab = h.label != null ? h.label : Array.isArray(o.labels) ? false : o.labels;   // named countries get their name unless labels:false
      if (lab !== false) keys.forEach((k, i) => labelOf(k, at + i * 0.12 + 0.25, typeof lab === "string" ? lab : null));
      return g;
    };
    g.label = (at, countries, text) => { keysOf(countries).forEach((k) => labelOf(k, at, text)); return g; };
    g.fly = (at, f = {}) => {
      if (f.from != null && !S.moves.length) cam0 = fitCam(kind, bboxOf(f.from), box, f.pad);
      const to = f.to != null ? fitCam(kind, f.bbox || bboxOf(f.to), box, f.pad) : cam0;
      S.moves.push({ at, dur: f.dur || 1.8, to });
      S.moves.sort((a, b) => a.at - b.at);
      return g;
    };
    g.pin = (at, place, pi = {}) => {
      const p = G.place(place), color = pi.color || colors.hi2;
      const grp = svgEl("g", { opacity: 0 }, gPin);
      const ring = svgEl("circle", { r: 14, style: `fill:none;stroke:${color};stroke-width:4` }, grp);
      const dot = svgEl("circle", { r: 14, style: `fill:${color};stroke:var(--ink, #f4efe6);stroke-width:4` }, grp);
      const text = pi.label !== undefined ? pi.label : p.label;
      const el = text ? mkLabel(text, { pill: pi.pill !== false ? (pi.pillColor || "var(--ink, #f4efe6)") : null }) : null;
      S.pins.push({ at, p, g: grp, dot, ring, el, r: pi.r || 14, side: pi.side });
      return g;
    };
    g.route = (at, stops, r = {}) => {
      const ps = stops.map((s) => G.place(s));
      if (ps.length < 2) throw new Error("FX.geo.route: at least two places");
      const mode = r.arc === false ? "line" : r.arc === "lift" ? "lift" : "geo";
      const color = r.color || colors.hi;
      // samples along the great circle, per leg proportional to its length
      const legs = [];
      for (let i = 0; i + 1 < ps.length; i++) legs.push(d3.geoDistance([ps[i].lon, ps[i].lat], [ps[i + 1].lon, ps[i + 1].lat]));
      const total = legs.reduce((a, b) => a + b, 0) || 1, cum = legs.map((_, i) => i / legs.length).concat(1);   // one equal slice of the time per leg
      const samples = [];
      const per = Math.max(40, Math.min(110, Math.round(150 / legs.length)));
      for (let i = 0; i + 1 < ps.length; i++) {
        const itp = d3.geoInterpolate([ps[i].lon, ps[i].lat], [ps[i + 1].lon, ps[i + 1].lat]);
        for (let j = 0; j < per; j++) samples.push(itp(j / per));
      }
      const last = ps[ps.length - 1]; samples.push([last.lon, last.lat]);
      const grp = svgEl("g", { opacity: 0 }, gRt);
      const ghost = svgEl("path", { style: `fill:none;stroke:${color};stroke-width:${tall ? 4 : 3};stroke-dasharray:2 12;stroke-linecap:round;opacity:${r.ghost === false ? 0 : 0.45}` }, grp);
      const line = svgEl("path", { style: `fill:none;stroke:${color};stroke-width:${tall ? 7 : 5.5};stroke-linecap:round;stroke-linejoin:round` }, grp);
      const marker = r.marker || "plane";
      const mk = svgEl("g", { opacity: 0 }, grp);
      if (marker === "plane") svgEl("path", { d: PLANE, transform: `scale(${tall ? 1.35 : 1.1})`, style: `fill:var(--ink, #f4efe6);stroke:${colors.bg};stroke-width:2` }, mk);
      else svgEl("circle", { r: tall ? 13 : 10, style: `fill:${color};stroke:var(--ink, #f4efe6);stroke-width:4` }, mk);
      const stopEls = ps.map((p, j) => {
        const dot = svgEl("circle", { r: tall ? 13 : 10, style: `fill:${j === ps.length - 1 ? colors.hi2 : color};stroke:var(--ink, #f4efe6);stroke-width:4`, opacity: 0 }, grp);
        const text = r.labels === false ? null : (typeof (r.labels || [])[j] === "string" ? r.labels[j] : p.label);
        const el = text ? mkLabel(text, { pill: "var(--ink, #f4efe6)" }) : null;
        return { dot, el, p, side: j % 2 ? "below" : "above" };
      });
      const dur = r.dur || Math.max(1.4, Math.min(5, legs.length * 1.2 + total * 1.2));
      S.routes.push({ at, dur, mode, samples, n: samples.length, per, stops: ps, cum, g: grp, ghost, line, mk, marker, stopEls, keepMarker: r.keepMarker });
      return g;
    };
    g.choropleth = (at, c = {}) => {
      const entries = Object.entries(c.values || {}).map(([k, v]) => [keysOf(k)[0], +v]).filter(([, v]) => Number.isFinite(v));
      if (!entries.length) throw new Error("FX.geo.choropleth: no values");
      const vals = entries.map(([, v]) => v), lo = c.min != null ? c.min : Math.min(...vals), hi = c.max != null ? c.max : Math.max(...vals);
      const [c0, c1] = c.colors || [`color-mix(in srgb, ${colors.hi} 30%, ${colors.land})`, colors.hi];
      const fill = {}, stagger = {};
      const sorted = entries.slice().sort((a, b) => (D.iso.get(a[0]).lon) - (D.iso.get(b[0]).lon));
      sorted.forEach(([k, v], i) => { const u = hi > lo ? clamp((v - lo) / (hi - lo), 0, 1) : 1; fill[k] = `color-mix(in srgb, ${c1} ${(u * 100).toFixed(1)}%, ${c0})`; stagger[k] = (i / sorted.length) * (c.spread != null ? c.spread : 0.9); });
      S.paints.push({ at, dur: c.dur || 0.55, fill, stagger, stroke: colors.ink });
      S.paints.sort((a, b) => a.at - b.at);
      const fmt = c.fmt || ((v) => v.toLocaleString(L === "tr" ? "tr-TR" : "en-US", { maximumFractionDigits: c.decimals != null ? c.decimals : (Math.abs(v) < 10 && v % 1 ? 1 : 0) }) + (c.unit || ""));
      const top = c.labelTop || 0;
      entries.slice().sort((a, b) => b[1] - a[1]).slice(0, top).forEach(([k, v]) => labelOf(k, at + 0.9 + 0.1 * Math.max(0, sorted.findIndex((s) => s[0] === k)), D.iso.get(k)[L] + "\n" + fmt(v)));
      if (top) S.labels.slice(-top).forEach((lb) => { lb.el.style.whiteSpace = "pre"; });
      const lg = c.legend;
      if (lg) {
        const lw = tall ? 620 : 520, lx = W / 2 - lw / 2, ly = (tall ? box.y + box.h - 40 : safe.y1 - 66);
        const el = divEl(over, { position: "absolute", left: lx + "px", top: ly + "px", width: lw + "px", opacity: 0, font: `700 ${Math.round(30 * fs)}px "Inter Tight", Poppins, sans-serif`, color: "var(--ink, #f4efe6)" });
        if (lg.title) divEl(el, { textAlign: "center", marginBottom: "10px", webkitTextStroke: "6px var(--bg, #0f1220)", paintOrder: "stroke fill", font: `800 ${Math.round(34 * fs)}px "Inter Tight", Poppins, sans-serif` }, lg.title);
        divEl(el, { height: Math.round(26 * fs) + "px", borderRadius: "14px", background: `linear-gradient(90deg, ${c0}, ${c1})`, boxShadow: "0 0 0 3px var(--bg, #0f1220)" });
        const row = divEl(el, { display: "flex", justifyContent: "space-between", marginTop: "8px", webkitTextStroke: "6px var(--bg, #0f1220)", paintOrder: "stroke fill" });
        divEl(row, {}, fmt(lo)); divEl(row, {}, fmt(hi));
        S.legend = { el, at: at + 0.2 };
      }
      return g;
    };

    if (hist || o.year != null) {   // the year, big, top of the safe area
      if (o.yearLabel !== false) {
        const el = divEl(over, { position: "absolute", left: 0, width: W + "px", top: safe.y0 + 4 + "px", textAlign: "center", font: `900 ${tall ? 120 : 84}px Anton, "Inter Tight", sans-serif`, letterSpacing: ".02em", color: "var(--ink, #f4efe6)", webkitTextStroke: "10px var(--bg, #0f1220)", paintOrder: "stroke fill", opacity: 0 }, typeof o.yearLabel === "string" ? o.yearLabel : yearText(+o.year));
        S.year = el;
      }
    }
    /* the map's own arguments */
    if (o.highlight) {
      const hl = Array.isArray(o.highlight) ? o.highlight : [o.highlight];
      if (hl.length && typeof hl[0] === "object" && !Array.isArray(hl[0]) && hl[0].countries) hl.forEach((h) => g.highlight(h.at != null ? h.at : at0 + 1, h.countries, h));
      else g.highlight(o.highlightAt != null ? o.highlightAt : at0 + 1.1, hl, { label: o.labels === false ? false : (o.labels != null ? o.labels : true) });
    }
    if (hist && o.labels === "all") hist.polities.slice().sort((p, q) => q.area - p.area).slice(0, 6).forEach((pl, i) => { const el = mkLabel(pl.name); S.labels.push({ el, at: at0 + 1.2 + i * 0.1, p: { lat: pl.cen[1], lon: pl.cen[0], kind: "polity" } }); });
    if (Array.isArray(o.labels)) o.labels.forEach((c) => g.label(at0 + 1.4, c));
    return g;
  };

  /* ------------------------------------------------------------------ flags */
  const flagCache = new Map();
  let flagUid = 0;
  /* the SVG source of a flag (sync read of the vendored file, cached); null when the set has no such flag */
  G.flagSVG = (iso) => {
    const r = G.find(iso), code = (r ? r.iso2 : String(iso)).toLowerCase();
    if (!flagCache.has(code)) {
      let txt = null;
      try { txt = jget(BASE + "flags/" + code + ".svg"); } catch (e) { console.error("fxgeo: no flag for " + iso); }
      flagCache.set(code, txt);
    }
    return flagCache.get(code);
  };
  /* inline-ready: the inner markup with its ids made unique so many flags can share a page */
  function inner(txt, uid) {
    const body = txt.replace(/<\?xml[^>]*\?>/g, "").replace(/<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");
    return body.replace(/\bid="([^"]+)"/g, (m, id) => `id="gf${uid}-${id}"`).replace(/url\(#([^)]+)\)/g, (m, id) => `url(#gf${uid}-${id})`)
      .replace(/(xlink:)?href="#([^"]+)"/g, (m, x, id) => `${x || ""}href="#gf${uid}-${id}"`);
  }
  const SLICES = 16;
  /* one flag: FX.geo.flag(tl, root, at, 'TR', {x, y, w, wave, label, pole}) -> the container div (centre x, y in px) */
  G.flag = (tl, root, at, iso, o = {}) => {
    need();
    const rec = G.find(iso);
    const txt = G.flagSVG(iso);
    const W0 = FX._W || 1080, H0 = FX._H || 1920, tall = H0 > W0;
    const w = o.w || (tall ? 520 : 420), h = Math.round(w * 0.75);
    const x = o.x != null ? o.x : W0 / 2, y = o.y != null ? o.y : H0 * 0.42;
    const uid = ++flagUid;
    const wrapEl = divEl(root, { position: "absolute", left: x - w / 2 + "px", top: y - h / 2 + "px", width: w + "px", height: h + "px", opacity: 0, transformOrigin: "50% 60%" });
    wrapEl.dataset.flag = rec ? rec.iso2 : String(iso);
    const shadow = o.shadow !== false;
    const face = divEl(wrapEl, { position: "absolute", inset: 0, borderRadius: o.wave ? "0" : Math.round(w * 0.02) + "px", overflow: o.wave ? "visible" : "hidden", boxShadow: shadow && !o.wave ? "0 18px 44px rgba(0,0,0,.45)" : "none", filter: shadow && o.wave ? "drop-shadow(0 16px 24px rgba(0,0,0,.45))" : "none", outline: o.border === false || o.wave ? "none" : "3px solid color-mix(in srgb, var(--ink, #f4efe6) 28%, transparent)" });
    const slices = [];
    if (txt) {
      const body = inner(txt, uid);
      const s = svgEl("svg", { viewBox: "0 0 640 480", width: w, height: h, style: "display:block;overflow:visible" }, face);
      if (!o.wave) s.insertAdjacentHTML("beforeend", body);
      else {
        const defs = svgEl("defs", {}, s); defs.insertAdjacentHTML("beforeend", `<g id="gf${uid}-all">${body}</g>`);
        const sw = 640 / SLICES;
        for (let i = 0; i < SLICES; i++) {
          const gg = svgEl("g", {}, s);
          const sl = svgEl("svg", { x: i * sw, y: 0, width: sw + 2, height: 480, viewBox: `${i * sw} 0 ${sw + 2} 480`, overflow: "hidden" }, gg);
          sl.insertAdjacentHTML("beforeend", `<use href="#gf${uid}-all"/>`);
          const shade = svgEl("rect", { x: i * sw, y: 0, width: sw + 2, height: 480, fill: "#000", opacity: 0 }, sl);
          slices.push({ gg, shade, x: i * sw });
        }
      }
    } else {   // no such flag in the set: a plain card with the code, never a wrong flag
      divEl(face, { position: "absolute", inset: 0, background: "color-mix(in srgb, var(--ink, #f4efe6) 18%, var(--bg, #0f1220))", color: "var(--ink, #f4efe6)", font: `900 ${Math.round(w * 0.3)}px "Inter Tight", sans-serif`, display: "flex", alignItems: "center", justifyContent: "center" }, String(iso).toUpperCase());
    }
    if (o.pole) {
      divEl(wrapEl, { position: "absolute", left: -Math.round(w * 0.035) + "px", top: -Math.round(h * 0.12) + "px", width: Math.round(w * 0.03) + "px", height: Math.round(h * 1.9) + "px", borderRadius: "6px", background: "linear-gradient(90deg, #8a8f99, #e6e9ee 45%, #6b707a)" });
      divEl(wrapEl, { position: "absolute", left: -Math.round(w * 0.05) + "px", top: -Math.round(h * 0.12) - Math.round(w * 0.03) + "px", width: Math.round(w * 0.06) + "px", height: Math.round(w * 0.06) + "px", borderRadius: "50%", background: "radial-gradient(circle at 35% 30%, #fff3b0, #d4a017)" });
    }
    let nameEl = null;
    if (o.label !== false && (o.label || o.names)) {
      const text = typeof o.label === "string" ? o.label : rec ? rec[lang()] : String(iso);
      nameEl = divEl(wrapEl, { position: "absolute", left: "50%", top: h + Math.round(22 * (tall ? 1 : 0.8)) + "px", transform: "translateX(-50%)", whiteSpace: "nowrap", font: `800 ${Math.round((o.fontSize || (tall ? 48 : 36)))}px "Inter Tight", Poppins, sans-serif`, color: "var(--ink, #f4efe6)", textAlign: "center" }, text);
    }
    tl.fromTo(wrapEl, { opacity: 0, scale: 0.72, y: 26 }, { opacity: 1, scale: 1, y: 0, duration: o.dur || 0.55, ease: "back.out(1.7)" }, at);
    if (slices.length) {
      const amp = o.amp != null ? o.amp : 7, speed = o.speed || 2.6, lam = 640 / (o.waves || 1.15);
      const upd = (t) => {
        if (!wrapEl.isConnected || getComputedStyle(wrapEl).display === "none") return;
        slices.forEach((s, i) => {
          const u = s.x / 640, ph = (s.x / lam) * 2 * Math.PI - t * speed, a = amp * (0.12 + 0.88 * u);
          const dy = a * Math.sin(ph), slope = Math.cos(ph) * (0.12 + 0.88 * u);
          s.gg.setAttribute("transform", `translate(0 ${dy.toFixed(2)})`);
          s.shade.setAttribute("opacity", Math.max(0, -slope * 0.22).toFixed(3));
        });
      };
      FX.onFrame(upd);
    }
    return wrapEl;
  };
  /* a row (or two) of flags with their names: comparisons, 'these countries' */
  G.flagRow = (tl, root, at, list, o = {}) => {
    need();
    const W0 = FX._W || 1080, H0 = FX._H || 1920, tall = H0 > W0, n = list.length;
    const cols = o.cols || (tall ? (n <= 3 ? 1 : 2) : Math.min(n, 4)), rows = Math.ceil(n / cols);
    const w = o.w || Math.min(tall ? 440 : 400, Math.floor((W0 - 160 - (cols - 1) * 60) / cols));
    const rowH = Math.round(w * 0.75) + (o.names === false ? 0 : (tall ? 100 : 80));
    const y0 = o.y != null ? o.y : H0 * (tall ? 0.45 : 0.42) - ((rows - 1) * (rowH + 40)) / 2 - rowH * 0.15;
    return list.map((c, i) => {
      const col = i % cols, row = Math.floor(i / cols), inRow = row === rows - 1 ? n - (rows - 1) * cols : cols;
      const x = W0 / 2 + (col - (inRow - 1) / 2) * (w + 60);
      return G.flag(tl, root, at + i * (o.stagger != null ? o.stagger : 0.14), c, Object.assign({}, o, { w, x, y: y0 + row * (rowH + 40) + (w * 0.75) / 2, names: o.names !== false, label: o.names === false ? false : o.label }));
    });
  };

  /* ------------------------------------------------------------------ borders as data (for the 3D kit) */
  const rdp = (ring, tol) => {   // Douglas-Peucker on [lat, lon] rings (planar, degrees): fewer points for a sphere texture
    if (!tol || ring.length < 8) return ring;
    const keep = new Uint8Array(ring.length); keep[0] = keep[ring.length - 1] = 1;
    const stack = [[0, ring.length - 1]];
    while (stack.length) {
      const [a, b] = stack.pop();
      let md = 0, mi = -1;
      const A = ring[a], B = ring[b], dx = B[1] - A[1], dy = B[0] - A[0], len = Math.hypot(dx, dy) || 1e-9;
      for (let i = a + 1; i < b; i++) { const d = Math.abs((ring[i][1] - A[1]) * dy - (ring[i][0] - A[0]) * dx) / len; if (d > md) { md = d; mi = i; } }
      if (md > tol && mi > 0) { keep[mi] = 1; stack.push([a, mi], [mi, b]); }
    }
    return ring.filter((_, i) => keep[i]);
  };
  const ringsOf = (ft, tol) => {
    const g = ft.f.geometry, polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates, out = [];
    for (const poly of polys) for (const r of poly) out.push(rdp(r.map((p) => [Math.round(p[1] * 1000) / 1000, Math.round(p[0] * 1000) / 1000]), tol));
    return out.filter((r) => r.length >= 4);
  };
  /* FX.geo.countryRings('TR', {simplify: 0.05, detail: '50m'}) -> [[[lat, lon], ...], ...] (outer rings and holes, closed);
     FX.geo.countryRings('all', {detail: '110m'}) -> [{iso, rings}] for every country. */
  G.countryRings = (iso, o = {}) => {
    need();
    const detail = o.detail || (iso === "all" ? "110m" : "50m"), tol = o.simplify || 0;
    const feats = D.world[detail];
    if (iso === "all") return feats.filter((f) => f.iso).map((f) => ({ iso: f.iso, rings: ringsOf(f, tol) }));
    const rec = G.find(iso);
    if (!rec) throw new Error("FX.geo.countryRings: unknown country " + JSON.stringify(iso));
    return feats.filter((f) => f.iso === rec.iso2).flatMap((f) => ringsOf(f, tol));
  };
  /* is [lat, lon] inside the country's shape? (tests and 'where is this?' checks) */
  G.contains = (iso, lat, lon, detail = "50m") => {
    need();
    const rec = G.find(iso);
    return D.world[detail].some((f) => f.iso === rec.iso2 && d3.geoContains(f.f, [lon, lat]));
  };
  G.centroid = (iso) => { const r = G.find(iso); return r ? [r.lat, r.lon] : null; };
  G.project = (kind, cam, box, W, H) => makeProj(kindOf(kind), cam, box, W, H);   // for tests
  G.fit = (kind, region, box, pad) => fitCam(kindOf(kind), bboxOf(region), box, pad);
})();
