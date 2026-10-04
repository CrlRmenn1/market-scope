import sys
from pathlib import Path

# Allow running as `python scripts/utils_test_pdf.py` from the backend folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.reporting import try_render_pdf_bytes
html = '<html><body><h1>WeasyPrint test</h1><p>Testing PDF generation.</p></body></html>'
pdf = try_render_pdf_bytes(html)
if pdf:
    with open('test_out.pdf','wb') as f:
        f.write(pdf)
    print('PDF_OK', len(pdf))
else:
    print('PDF_FAIL')
