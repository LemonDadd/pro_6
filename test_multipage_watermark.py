"""Multi-page watermark test"""
import io
from pathlib import Path
from pypdf import PdfReader
import sys
sys.path.insert(0, str(Path(__file__).parent))

from app.services.pdf_renderer import PdfRenderer
from app.schemas import RenderOptions, CoverOptions

renderer = PdfRenderer()

options = RenderOptions(
    watermark="CONFIDENTIAL",
    watermarkOpacity=0.15,
    watermarkAngle=-30,
    footer="Page {{page}} / {{pages}}",
    toc=True,
    cover=CoverOptions(title="My Document", author="Test Author", date="2024"),
)

md = """# Chapter 1

This is the first chapter. It has some content.

## Section 1.1

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

## Section 1.2

Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.

# Chapter 2

This is the second chapter.

## Section 2.1

Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.

## Section 2.2

Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt.

# Chapter 3

Third chapter content here. More text to ensure multiple pages.

## Section 3.1

Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem.

## Section 3.2

Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur?

# Chapter 4

Final chapter.

## Section 4.1

Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur?

## Section 4.2

At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident.
"""

pdf_bytes, page_count = renderer.render_to_pdf(md, options=options)
print(f"Total pages: {page_count}")
print(f"PDF size: {len(pdf_bytes)} bytes")

reader = PdfReader(io.BytesIO(pdf_bytes))
print(f"Pages (pypdf): {len(reader.pages)}")

for i, page in enumerate(reader.pages):
    text = page.extract_text() or ""
    print(f"  Page {i+1}: {len(text)} chars, first 80: {text[:80].strip()!r}")

Path("test_multipage_watermark.pdf").write_bytes(pdf_bytes)
print("\nSaved to test_multipage_watermark.pdf")
print("\nWatermark should appear on EVERY page (cover, TOC, all content pages)")
print("(position: fixed elements repeat on every page in WeasyPrint)")
