# wiki-polis flow diagram — assets

How a wiki-polis conversation works, drawn in the production tool's design language
(off-white canvas, `--ink`/`--pass`/`--agree`/`--disagree`/`--spot` tokens, Inter Tight + JetBrains Mono).

## Files

| File | What it is |
|---|---|
| `wiki-polis-flow.svg` | **Master.** Full 1200×600 vector diagram — edit this. Text is live `<text>` with `<title>`/`<desc>` for accessibility. |
| `wiki-polis-flow.png` | Raster export of the full diagram, for places that can't take SVG. |
| `box-1-explore.svg` | Standalone "Explore the questions" panel (380×326). |
| `box-2-arguments.svg` | Standalone "Map the arguments" panel (380×326). |
| `box-3-informed-voting.svg` | Standalone "Express informed opinions" panel (380×326). |

## Re-exporting the PNG at any size

The SVG is the source of truth. To get a crisp raster at any scale, open
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
