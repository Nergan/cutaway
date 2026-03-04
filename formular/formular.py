from pathlib import Path
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, Response, RedirectResponse
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

router = APIRouter()
BASE_DIR = Path(__file__).parent


@router.get('/', response_class=FileResponse, name='formular_root')
async def formular_page():
    """Страница конвертера документов."""
    return FileResponse(BASE_DIR / 'formular.html')


@router.get('/{rest_of_path:path}', include_in_schema=False)
async def formular_fallback(request: Request):
    """Редирект на главную страницу конвертера."""
    return RedirectResponse(url=request.url_for('formular_root'))


async def convert_docx_to_pdf(docx_content: bytes) -> bytes:
    try:
        docx_file = BytesIO(docx_content)
        doc = Document(docx_file)
        pdf_buffer = BytesIO()
        pdf = SimpleDocTemplate(
            pdf_buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        story = []
        styles = getSampleStyleSheet()
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            try:
                pdfmetrics.registerFont(TTFont('DejaVu', 'DejaVuSans.ttf'))
                styles['Normal'].fontName = 'DejaVu'
            except:
                try:
                    pdfmetrics.registerFont(TTFont('ArialUnicode', 'arialuni.ttf'))
                    styles['Normal'].fontName = 'ArialUnicode'
                except:
                    pass
        except ImportError:
            pass

        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text = paragraph.text
                p = Paragraph(text.replace('\n', '<br/>'), styles['Normal'])
                story.append(p)
                story.append(Spacer(1, 12))

        pdf.build(story)
        pdf_buffer.seek(0)
        return pdf_buffer.read()
    except Exception as e:
        import logging
        logging.error(f'PDF conversion error: {str(e)}')
        raise Exception(f'PDF conversion failed: {str(e)}')


@router.post('/api/convert')
async def formular_convert(
    file: UploadFile = File(...),
    from_format: str = Form(...),
    to_format: str = Form(...)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail='No file provided')

    original_name = file.filename
    name_without_ext = original_name.rsplit('.', 1)[0]
    new_name = f'{name_without_ext}.{to_format}'
    encoded_filename = quote(new_name)

    if from_format == 'docx' and to_format == 'pdf':
        try:
            content = await file.read()
            pdf_bytes = await convert_docx_to_pdf(content)
            return Response(
                content=pdf_bytes,
                media_type='application/pdf',
                headers={
                    'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Conversion error: {str(e)}')

    elif from_format == 'html' and to_format == 'pdf':
        from playwright.async_api import async_playwright

        async def html_to_pdf(html_bytes: bytes) -> bytes:
            async with async_playwright() as p:
                browser = await p.chromium.launch(channel='chrome', headless=True)
                page = await browser.new_page()
                await page.set_content(html_bytes.decode('utf-8'))
                pdf_bytes = await page.pdf()
                await browser.close()
                return pdf_bytes

        try:
            content = await file.read()
            pdf_bytes = await html_to_pdf(content)
            return Response(
                content=pdf_bytes,
                media_type='application/pdf',
                headers={
                    'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Conversion error: {str(e)}')

    else:
        raise HTTPException(status_code=400, detail='Unsupported conversion format')