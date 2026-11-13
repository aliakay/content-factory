GEO KIT (maps, flags and borders from real data: Natural Earth + flag-icons, offline; motion/templates/fxgeo.js). The page
loads it only when a scene's js says FX.geo. Never draw geography by hand and never ask a model for a map or a flag.
  g = FX.geo.map(tl, root, T, {region, bbox, center, zoom, projection, pad, highlight, colors, labels, draw, year, at, box})
    region: country ('Türkiye', 'TR', 'TUR'), region name ('europe'|'avrupa'|'middle_east'|'balkans'|'asia'|'africa'|
      'north_america'|'south_america'|'oceania'|'world' ...), a list (union), or places ['İstanbul', [41, 28]];
      bbox [west, south, east, north]; center + zoom (zoom 1 = the whole world across the frame). Default projection:
      mercator (naturalEarth for the world; 'globe' = an orthographic disc, 'equirect'). pad = share of margin (0.18).
    highlight: ['TR', 'Yunanistan'] with labels true|false|[countries]; draw 'stroke' (outlines draw on) | 'fade'.
  Builders on g, `at` in ABSOLUTE film seconds like the rest of FX:
    g.highlight(at, countries, {color, label, dur})   g.label(at, countries)   g.fly(at, {from, to, dur, pad})
    g.route(at, [place, ...], {dur, arc: true (great circle) | false | 'lift', marker: 'plane'|'dot', labels, color})
    g.pin(at, place, {label, color, side})   g.choropleth(at, {values: {iso|name: n}, legend: {title}, labelTop, unit, colors})
  Flags: FX.geo.flag(tl, root, at, 'TR', {x, y, w, wave, label, pole}), FX.geo.flagRow(tl, root, at, [codes], {names, cols}).
  Places: country name or ISO code in Turkish or English, one of 74 cities (İstanbul, Ankara, İzmir, Londra, Paris,
    New York, Tokyo, ...), [lat, lon] (LATITUDE FIRST; fx3d's globe is [lon, lat]) or {lat, lon, label}. An unknown name
    throws: use coordinates, never a near-match. Labels come in the film's language (the scene's <html lang>).
  History: year: 1453 draws the political map of that year (Cliopatria, CC BY 4.0, cached by factory/geo.py on first use;
    the credit line reaches the publish description by itself). g.highlight then takes polity names (Osmanlı, Bizans,
    Roma, Selçuklu, Moğol, Ottoman Empire ...). Without the data only coastlines show: never a wrong-era border.
  For the 3D kit: FX.geo.countryRings('TR'|'all', {simplify, detail}) -> [[lat, lon], ...] rings (closed) of real borders.
  Data: FX.geo.find(q), FX.geo.city(q), FX.geo.place(p), FX.geo.contains(iso, lat, lon), FX.geo.regions.

RULES: one FX.geo.map per scene (it owns the picture: land, labels, pins); text from the map is DOM text, do not write
  the same names again. The map bleeds off the stage; the region is framed in the platform-safe area and labels are
  clamped into it. Colours come from the film palette (--ink, --bg, --accent, --accent2, --hot): pass colors only for a
  reason. 4-5 highlights, pins or stops at most; one flyover per scene. Everything is a pure function of t: no
  Math.random, no Date, no fetch. A flat map is cheap; a flying camera redraws every frame (0.1-0.3 s a frame).
