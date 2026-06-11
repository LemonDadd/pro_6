from weasyprint import HTML
from pypdf import PdfReader
import io

doc = HTML(string='<h1>PDF/A Test</h1><p>Hello World</p>').render()

# Test normal
pdf_normal = doc.write_pdf()
print(f'Normal PDF: {len(pdf_normal)} bytes')

# Test PDF/A-2b
try:
    pdf_a = doc.write_pdf(pdf_variant='pdf/a-2b')
    print(f'PDF/A-2b: {len(pdf_a)} bytes')
    
    # Verify with pypdf
    reader = PdfReader(io.BytesIO(pdf_a))
    print(f'  Pages: {len(reader.pages)}')
    print(f'  PDF version: {reader.trailer.get("/Version", "unknown")}')
    
    # Check for PDF/A metadata
    metadata = reader.metadata
    print(f'  Producer: {metadata.producer if metadata else "n/a"}')
    print('  PDF/A verification: OK (file generated without error)')
except Exception as e:
    print(f'PDF/A-2b FAILED: {e}')
    import traceback
    traceback.print_exc()
