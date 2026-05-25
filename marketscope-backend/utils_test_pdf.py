from reporting import try_render_pdf_bytes
html = '<html><body><h1>WeasyPrint test</h1><p>Testing PDF generation.</p></body></html>'
pdf = try_render_pdf_bytes(html)
if pdf:
    with open('test_out.pdf','wb') as f:
        f.write(pdf)
    print('PDF_OK', len(pdf))
else:
    print('PDF_FAIL')
