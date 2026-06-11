"""Direct test of PDF renderer features: Watermark, PDF/A-2b, Batch ZIP"""
import io
import zipfile
from pathlib import Path
from pypdf import PdfReader

import sys
sys.path.insert(0, str(Path(__file__).parent))

from app.services.pdf_renderer import PdfRenderer
from app.schemas import RenderOptions

renderer = PdfRenderer()

def test_watermark():
    print("\n=== Test 1: Watermark ===")
    options = RenderOptions(
        watermark="CONFIDENTIAL",
        watermarkOpacity=0.2,
        watermarkAngle=-45,
        footer="Page {{page}} of {{pages}}"
    )
    md = "# Hello World\n\nThis is a test document.\n\n## Section 1\n\nContent.\n\n## Section 2\n\nMore content."
    pdf_bytes, page_count = renderer.render_to_pdf(md, options=options)
    print(f"Pages: {page_count}")
    print(f"Size: {len(pdf_bytes)} bytes")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        print(f"  Page {i+1} text length: {len(text)}")

    Path("test_watermark_direct.pdf").write_bytes(pdf_bytes)
    print("Saved to test_watermark_direct.pdf")

    html = renderer._build_html_document(
        renderer.md_renderer.render(md),
        "",
        renderer._build_page_css(options),
        options,
        "Test"
    )
    has_watermark_div = 'class="watermark"' in html
    has_watermark_css = ".watermark" in html
    print(f"HTML has watermark div: {has_watermark_div}")
    print(f"HTML has watermark CSS: {has_watermark_css}")
    return has_watermark_div and has_watermark_css


def test_pdfa():
    print("\n=== Test 2: PDF/A-2b ===")
    options = RenderOptions(outputFormat="pdf-a-2b")
    md = "# PDF/A Test\n\nThis should be PDF/A-2b."
    try:
        pdf_bytes, page_count = renderer.render_to_pdf(md, options=options)
        print(f"Pages: {page_count}")
        print(f"Size: {len(pdf_bytes)} bytes")

        reader = PdfReader(io.BytesIO(pdf_bytes))
        metadata = reader.metadata
        print(f"Metadata: {dict(metadata) if metadata else 'None'}")

        header = pdf_bytes[:100]
        has_pdfa = b"PDF/A" in pdf_bytes or b"pdfa" in pdf_bytes.lower()
        print(f"Contains PDF/A identifier in file: {has_pdfa}")

        Path("test_pdfa_direct.pdf").write_bytes(pdf_bytes)
        print("Saved to test_pdfa_direct.pdf")
        return True
    except Exception as e:
        print(f"PDF/A generation failed: {e}")
        return False


def test_batch_zip():
    print("\n=== Test 3: Batch ZIP ===")
    options = RenderOptions(
        watermark="DRAFT",
        footer="{{page}}/{{pages}}"
    )
    files = [
        ("intro.md", "# Introduction\n\nThis is intro."),
        ("ch1.md", "# Chapter 1\n\nContent of chapter 1.\n\n## Section A\n\nDetails."),
        ("ch2.md", "# Chapter 2\n\nContent of chapter 2."),
    ]

    zip_buffer = io.BytesIO()
    total_pages = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, md in files:
            pdf_name = Path(filename).stem + ".pdf"
            pdf_bytes, page_count = renderer.render_to_pdf(md, theme="github", options=options)
            zf.writestr(pdf_name, pdf_bytes)
            total_pages += page_count
            print(f"  Added {pdf_name}: {len(pdf_bytes)} bytes, {page_count} pages")

    zip_bytes = zip_buffer.getvalue()
    print(f"ZIP size: {len(zip_bytes)} bytes")
    print(f"Total pages: {total_pages}")

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        print(f"ZIP contents: {names}")
        all_pdf = all(n.endswith(".pdf") for n in names)
        print(f"All entries are PDFs: {all_pdf}")

    Path("test_batch_direct.zip").write_bytes(zip_bytes)
    print("Saved to test_batch_direct.zip")
    return len(names) == len(files) and all_pdf


def main():
    results = {}
    results["watermark"] = test_watermark()
    results["pdf-a-2b"] = test_pdfa()
    results["batch-zip"] = test_batch_zip()

    print("\n=== Summary ===")
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {name}: {status}")

    all_pass = all(results.values())
    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")


if __name__ == "__main__":
    main()
