# Third-party code

## line-art-animation (JDhruv14) — MIT
Used in: `motion/templates/lineart.js` (the `FX.ink` line-art kit), ported from TypeScript to plain JavaScript and re-engineered
so every state is a pure function of time. Taken from upstream: the open double-stroke limb, the 95-unit figure space, the
phase-based walk/run solver, the ink wobble filter, the day-to-night palette ramps.
Source: https://github.com/JDhruv14/line-art-animation

MIT License — Copyright (c) 2026 JDhruv14

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

## AI-Video-Factory (Ersin KOÇ) — MIT
Used in: `factory/speech_tr.py` (Turkish number / ordinal / currency / fraction / abbreviation reading rules, suffix harmony
for expanded acronyms, token-group → caption word mapping) and `data/pronounce_tr.json` (the built-in respelling lexicon: tech
terms and Turkish acronym expansions such as `C++ → si pılas pılas`, `TBMM → Türkiye Büyük Millet Meclisi`), and the checks of
`factory/voiceaudit.py` (word gaps over 400 ms, quiet-block policy). Ported from TypeScript to Python (`packages/pipeline/src/
numbers.ts`, `pronounce.ts`, `voice-audit.ts`) with our own additions (dates, units, clock times, letter-spelled acronyms,
exact-case matching of ALL-CAPS terms); the lexicon entries are our own selection around the same idea.
Source: https://github.com/ersinkoc/AI-Video-Factory

MIT License — Copyright (c) 2026 Ersin KOÇ

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

## Maps, flags and borders (FX.geo: `motion/templates/fxgeo.js`, `factory/geo.py`, `assets/geo/`)
All vendored under `assets/geo/` and used offline at render time (no CDN, no network). Our own code on top: `fxgeo.js`
(SVG maps whose every frame is a pure function of t), `factory/geo.py`, `assets/geo/countries.json` (ISO codes, Turkish and
English names, label points; built by `assets/geo/build_countries.py` from the ISO 3166 list and CLDR names) and `cities.json`.

- **Natural Earth** (public domain) through **world-atlas 2.0.2** (ISC, Mike Bostock): `assets/geo/countries-110m.json`,
  `countries-50m.json` (TopoJSON, Natural Earth 4.1.0 Admin 0). Sources: https://www.naturalearthdata.com/ ·
  https://github.com/topojson/world-atlas
- **flag-icons 7.6.0** (MIT, Copyright (c) 2013 Panayiotis Lipiridis): `assets/geo/flags/*.svg` (the 4x3 set, unmodified).
  Source: https://github.com/lipis/flag-icons
- **d3-geo 3.1.2** (ISC, Copyright 2010-2026 Mike Bostock; contains GeographicLib code, MIT, Copyright 2008-2012 Charles Karney),
  **d3-array 3.2.5** (ISC, Mike Bostock), **topojson-client 3.1.0** (ISC, Copyright 2012-2019 Michael Bostock): the UMD builds in
  `assets/geo/vendor/` with their licence headers intact (projections, great-circle interpolation, TopoJSON decoding).
  Sources: https://github.com/d3/d3-geo · https://github.com/d3/d3-array · https://github.com/topojson/topojson-client
- **Cliopatria** (CC BY 4.0, Seshat Global History Databank; Bennett et al. 2025, doi:10.1038/s41597-025-04516-9): historical
  borders, NOT vendored: `factory/geo.py` downloads v0.2.1 once on first use (46 MB zip), simplifies it into `work/geo/` (~10 MB gzipped)
  and writes one small JSON per year. The attribution is required: the licence ledger (`factory/licence.py`) adds the credit line
  "Tarihî sınırlar: Cliopatria, Seshat Global History Databank ... CC BY 4.0" to the publish description for any film whose map
  asks for a `year`. Source: https://github.com/Seshat-Global-History-Databank/cliopatria

ISC License — Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby
granted, provided that the above copyright notice and this permission notice appear in all copies. THE SOFTWARE IS PROVIDED "AS
IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

flag-icons — The MIT License (MIT), Copyright (c) 2013 Panayiotis Lipiridis. Permission is hereby granted, free of charge, to any
person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions: The
above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE
SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

AI-Video-Factory — texture, paper base, build-in and ambience particles in `motion/templates/fxlib.js` (and their recipe
cards in `motion/recipes/texture.yaml`, `living.yaml`, `rhythm.yaml`) are ported from the MIT-licensed reference
implementation `AI-Video-Factory` (Copyright (c) Ersin KOÇ), files `packages/core/src/texture.ts`,
`packages/video/src/{entrance,paperBase,particles}.ts` and `packages/video/src/Ambience.tsx`. The mechanics carried over
are the SVG/turbulence texture recipes and their opacities, the "normal alpha, never a blend mode" decision, the paper
silhouette thresholds (faint 0.3 / translucent 0.9 / share 0.1 / shadow), the ENTER/PACE entrance timing (0.15 s pause,
0.15 s gaps, 0.35 s length, within 40 % of the shot, pop 0.45 / fade 0.8 / slide 0.9 s) and the particle constants
(depth layers, 0.18 rain slant, 1400–2400 px/s rain, 30–120 px/s snow, confetti launch 0.8 s / 300–440 px/s / floor band
0.74–0.97). Rewritten in this project's own style: a canvas-painted, baked bitmap texture instead of a live SVG filter
(measured 2x render time here), seeded value noise instead of feTurbulence for the baked path, palette-aware polarity, and
this kit's (tl, at, opts) call conventions.

MIT License — Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to
whom the Software is furnished to do so, subject to the following conditions: The above copyright notice and this permission
notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT
WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

AI-Video-Factory — the 43 media film styles added to `data/film_styles.json` (ottoman_miniature, byzantine_mosaic,
illuminated_manuscript, anatolian_kilim, egyptian_papyrus, greek_vase, stained_glass, ukiyo_e, art_deco, constructivist,
linocut, cyanotype, manga_screentone, art_nouveau, cave_painting, vintage_engraving, watercolor, gouache, oil_impasto,
charcoal, graphite_sketch, crayon, scratchboard, mid_century, comic_pop, bauhaus, synthwave, silkscreen_travel,
botanical_plate, technical_cutaway, pictogram, felt_applique, embroidery, sand_art, paper_quilling, origami, wood_inlay,
low_poly, vinyl_toy, frosted_glass, cyberpunk, gothic, terracotta_relief) take their choice of media and the starting
palettes / art-direction notes from the style packs in `packages/core/src/styles.ts` of the same MIT-licensed project
(Copyright (c) Ersin KOÇ). The cards' render recipes, the preview scenes in `styles/<id>.json` and all TR/EN text are our own.
