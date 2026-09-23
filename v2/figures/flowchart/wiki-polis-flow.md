# wiki-polis flow diagram — assets

How a wiki-polis conversation works, drawn in the production tool's design language
(off-white canvas, `--ink`/`--pass`/`--agree`/`--disagree`/`--spot` tokens, Inter Tight + JetBrains Mono).

## Where the diagram lives

The consultation list renders the diagram as HTML, from
[`frontend/src/features/legacy/consultation-flow.tsx`](../../frontend/src/features/legacy/consultation-flow.tsx),
with every word taken from the message catalogue (`flow-*` in `v2/i18n/en.json`), so it reads in the
page's language and wraps a longer translation instead of overflowing (#420). **That component is
the master.** A change to the diagram's wording goes into `en.json`; a change to its drawing goes
into the component.

The files below are **English-only exports** for slides, papers and posters. They are not kept in
sync with the component, and their wording is older than the catalogue's.

## Files

| File | What it is |
|---|---|
| `wiki-polis-flow.svg` | Full 1200×600 vector diagram, English. A copy is still served at `/static/wiki-polis-flow.svg` for links made to it, but no page uses it. |
| `wiki-polis-flow.png` | Raster export of the full diagram, for places that can't take SVG. |
| `box-1-explore.svg` | Standalone "Explore the questions" panel (380×326). |
| `box-2-arguments.svg` | Standalone "Map the arguments" panel (380×326). |
| `box-3-informed-voting.svg` | Standalone "Express informed opinions" panel (380×326). |

## Re-exporting the PNG at any size

To get a crisp raster at any scale, open
`wiki-polis-flow.svg` in a browser, Figma, or Inkscape and export at the multiple you need
(e.g. 2× = 2400×1200). Fonts: the SVG references **Inter Tight** (headings/body) and
**JetBrains Mono** (the WHAT WE LEARN labels) by name — install them, or substitute, before
exporting if exact metrics matter.

## The three phases

Each phase acts on the **same statement-card motif**, on purpose:

1. **Explore the questions** — pencil-on-card (you write/edit statements) + yes/no vote. → *Clusters of statements.*
2. **Map the arguments** — dashed +/− fields you fill in. → *A pro/con argument map.*
3. **Express informed opinions** — solid +/− chips shown *to* you + a re-vote. → *How the community feels.*

The three outputs converge into **a more balanced policy draft** — a starting point handed back to
the community, not a verdict. (That closing line is documentation caption text and is intentionally
*not* baked into the figure.)

## Colour meaning

Green `#15734a` = pro / yes · Red `#b23a3a` = no · Blue `#3d6dba` = the "what we learn" info layer ·
Amber `#b45309` = pencil accent only. Green is reserved to mean agreement, never decoration.
