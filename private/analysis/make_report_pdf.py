#!/usr/bin/env python3
"""Render a consultation report HTML to a print-ready PDF.

Two things the browser-printed version does not do:

  * Drops the faint warm background (`--surface: #fcfcfb`) to true white. On
    screen it reads as paper; in print it reads as a scanning artefact, and it
    costs ink on every page.
  * Puts a running header on *every* page naming the product, the round, the
    consultation and the URL it came from. A PDF gets separated from its
    context the moment someone downloads it — page 14 on its own should still
    say what it is and where it came from.

WeasyPrint rather than headless Chrome: Chrome emits no `@page` margin boxes
(so no running header), and its Skia PDF writer produced files Acrobat would
not open — the participant report came out with zero embedded font resources.

Usage:
    ./make_report_pdf.py report_participant.html out.pdf \
        --round 1 --process "nl.wikipedia arbitragecommissie" \
        --url wiki-polis.toolforge.org/c/2026-nlwiki-arbcom
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[2] / "v2" / "static" / "fonts"

# Inter Tight and JetBrains Mono, both SIL Open Font License, both already
# self-hosted by the product. An embedded font ships inside the PDF, so for a
# Commons upload it has to be one that may be freely redistributed — which
# rules out the system UI faces the screen stylesheet falls back to.
FONT_CSS = """
@font-face {{
    font-family: 'Inter Tight PDF';
    font-style: normal;
    font-weight: 400 700;
    src: url('file://{font_dir}/inter-tight-latin.woff2') format('woff2');
}}
@font-face {{
    font-family: 'Inter Tight PDF';
    font-style: normal;
    font-weight: 400 700;
    src: url('file://{font_dir}/inter-tight-latin-ext.woff2') format('woff2');
    unicode-range: U+0100-02BA, U+1E00-1EFF, U+2020, U+20A0-20AB, U+2113, U+2C60-2C7F, U+A720-A7FF;
}}
@font-face {{
    font-family: 'JetBrains Mono PDF';
    font-style: normal;
    font-weight: 400 700;
    src: url('file://{font_dir}/jetbrains-mono-latin.woff2') format('woff2');
}}
"""

# Inter Tight's latin subset stops at U+206F, so a maths operator like "≥"
# (U+2265, used in the participation table) falls through to whatever the system
# offers — Verdana here, which is proprietary and would then be embedded in the
# PDF. DejaVu Sans covers the range and is freely licensed, so it is used as the
# fallback when present. Not fatal if absent: the document still renders, just
# with a system face for those few glyphs.
DEJAVU_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/opt/homebrew/share/fonts/DejaVuSans.ttf",
    "/usr/local/share/fonts/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
)

FALLBACK_CSS = """
@font-face {{
    font-family: 'Fallback PDF';
    src: url('file://{path}');
}}
"""


def find_fallback() -> Path | None:
    """First freely-licensed font on disk that covers the maths operators."""
    for candidate in DEJAVU_CANDIDATES:
        if Path(candidate).is_file():
            return Path(candidate)
    # TeX Live ships DejaVu and is common on machines that build documents.
    for root in (Path("/usr/local/texlive"), Path("/opt/texlive")):
        if root.is_dir():
            found = sorted(root.glob("*/texmf-dist/fonts/truetype/public/dejavu/DejaVuSans.ttf"))
            if found:
                return found[-1]
    return None

PRINT_CSS = """
@page {{
    size: A4;
    margin: 16mm 14mm 14mm 14mm;

    @top-left {{
        content: "{header}";
        font-family: 'Inter Tight PDF', sans-serif;
        font-size: 7.5pt;
        color: #6f6f6a;
        padding-bottom: 3mm;
        border-bottom: 0.4pt solid #ddddd8;
        width: 100%;
        vertical-align: bottom;
    }}

    @bottom-right {{
        content: counter(page) " / " counter(pages);
        font-family: 'Inter Tight PDF', sans-serif;
        font-size: 7.5pt;
        color: #8a8880;
    }}
}}

/* True white. The screen palette's warm off-white prints as a dirty cast. */
:root {{ --surface: #ffffff; }}
html, body {{ background: #ffffff !important; }}
.caveats {{ background: #f7f7f6 !important; }}

/* Open fonts, and a tighter measure. The screen sizing is generous because a
   browser window scrolls; a page does not, and the loose version ran to 57
   pages against a browser print's 30. */
/* Universal, because any element with its own font-family would otherwise
   fall through to a system face and embed it. Verdana, Arial and Menlo are
   proprietary; shipping them inside a Commons upload is a licence problem. */
* {{ font-family: 'Inter Tight PDF', 'Fallback PDF', sans-serif !important; }}
html, body {{
    font-family: 'Inter Tight PDF', 'Fallback PDF', sans-serif !important;
    font-size: 9pt !important;
    line-height: 1.42 !important;
}}
code, pre, kbd, samp, .check, .diff .ids {{
    font-family: 'JetBrains Mono PDF', 'Fallback PDF', monospace !important;
    font-size: 8pt !important;
}}

/* Say who this is for, before anything else. The two versions of this report
   differ in what they contain and in what they assume the reader wants; a PDF
   circulates without its filename, so the document has to say so itself. */
body::before {{
    content: "{audience}";
    display: block;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: #55554f;
    border: 0.6pt solid #d9d9d2;
    border-left: 2.5pt solid #55554f;
    padding: 4pt 8pt;
    margin: 0 0 12pt;
}}
h1 {{ font-size: 17pt !important; }}
h2 {{ font-size: 12.5pt !important; }}
h3 {{ font-size: 10.5pt !important; }}
table {{ font-size: 8.2pt !important; }}
th, td {{ padding: 2.5pt 5pt !important; }}
p {{ margin: 0 0 5pt !important; }}
figure {{ margin: 7pt 0 !important; }}

/* Keep small blocks whole. Deliberately NOT `table`: these reports carry
   tables longer than a page, and forcing those whole pushes each one to a
   fresh page and leaves half the preceding page empty. Let long tables split
   and repeat their header row instead. */
figure, .callout, .caveats {{ break-inside: avoid; }}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; }}
h1, h2, h3 {{ break-after: avoid; }}
img, svg {{ max-width: 100% !important; height: auto !important; }}
"""


def build(source: Path, out: Path, header: str, audience: str) -> int:
    """Shell out to the weasyprint CLI.

    Importing weasyprint is not an option: Homebrew installs it against its own
    pinned interpreter, so `import weasyprint` fails under whichever python
    happens to run this script. The CLI is the stable interface.
    """
    exe = shutil.which("weasyprint")
    if exe is None:
        sys.exit("weasyprint not found on PATH: brew install weasyprint")

    # Escape for the CSS string context: backslash first, then the quote.
    def css_str(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    if not FONT_DIR.is_dir():
        sys.exit(f"font directory not found: {FONT_DIR}")

    fallback = find_fallback()
    if fallback is None:
        print("  note: no free fallback font found; a system face will be embedded "
              "for maths glyphs such as \u2265", file=sys.stderr)

    with tempfile.NamedTemporaryFile("w", suffix=".css", delete=False) as fh:
        fh.write(FONT_CSS.format(font_dir=FONT_DIR))
        if fallback is not None:
            fh.write(FALLBACK_CSS.format(path=fallback))
        fh.write(PRINT_CSS.format(
            header=css_str(header), audience=css_str(audience),
        ))
        css_path = fh.name
    try:
        result = subprocess.run(
            [exe, "-s", css_path, str(source), str(out)],
            capture_output=True, text=True,
        )
    finally:
        Path(css_path).unlink(missing_ok=True)

    if result.returncode != 0 or not out.is_file():
        sys.exit(f"weasyprint failed:\n{result.stderr.strip()}")
    return out.stat().st_size


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", type=Path, help="report HTML")
    p.add_argument("out", type=Path, help="PDF to write")
    p.add_argument("--round", required=True, help="round number, e.g. 1")
    p.add_argument("--process", required=True, help="consultation name")
    p.add_argument("--url", required=True, help="URL of the original process")
    p.add_argument("--brand", default="Proto", help="product name (default: Proto)")
    p.add_argument("--audience", required=True,
                   help='who the report is for, e.g. "For participants in this consultation"')
    args = p.parse_args()

    if not args.source.is_file():
        sys.exit(f"no such file: {args.source}")

    header = f"{args.brand} · Round {args.round} · {args.process} · {args.url}"
    size = build(args.source, args.out, header, args.audience)
    print(f"{args.out}  {size:,} bytes")
    print(f"  header:   {header}")
    print(f"  audience: {args.audience}")


if __name__ == "__main__":
    main()
