from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from docx import Document
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.services.pdf_service import DocxProjectTemplateService, TailoredResumePdfService


def _docx_with_editable_body_and_image() -> bytes:
    image_buffer = BytesIO()
    Image.new("RGB", (8, 8), color="white").save(image_buffer, format="PNG")
    image_buffer.seek(0)
    document = Document()
    document.add_paragraph("胡俊")
    document.add_paragraph("电话: 15822716099")
    document.add_paragraph("教育经历: 吉林大学")
    document.add_picture(image_buffer)
    document.add_paragraph("技能: Python, SQL")
    document.add_paragraph("项目经历")
    document.add_paragraph("旧项目描述，应该被替换。")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _paragraphs(docx_bytes: bytes) -> list[str]:
    return [paragraph.text for paragraph in Document(BytesIO(docx_bytes)).paragraphs]


def _media_names(docx_bytes: bytes) -> list[str]:
    with ZipFile(BytesIO(docx_bytes)) as archive:
        return sorted(name for name in archive.namelist() if name.startswith("word/media/"))


def _pdf_with_pages(page_count: int) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for index in range(page_count):
        pdf.drawString(72, 720, f"page {index + 1}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_docx_template_preserves_identity_and_education_then_replaces_editable_body():
    template_bytes = _docx_with_editable_body_and_image()

    result = DocxProjectTemplateService().render(
        template_bytes,
        "技能: Python, SQL, 数据分析\n项目经历: 围绕岗位突出 Python、SQL 和数据看板。",
    )

    paragraphs = _paragraphs(result)
    assert "胡俊" in paragraphs
    assert "电话: 15822716099" in paragraphs
    assert "教育经历: 吉林大学" in paragraphs
    assert "技能: Python, SQL" not in paragraphs
    assert "旧项目描述，应该被替换。" not in paragraphs
    assert "技能: Python, SQL, 数据分析\n项目经历: 围绕岗位突出 Python、SQL 和数据看板。" in paragraphs
    assert _media_names(result) == _media_names(template_bytes)


def test_tailored_resume_pdf_service_retries_with_compressed_project_until_one_page():
    class FakeConverter:
        def __init__(self):
            self.docx_inputs: list[bytes] = []

        def convert(self, docx_bytes: bytes) -> bytes:
            self.docx_inputs.append(docx_bytes)
            return _pdf_with_pages(2 if len(self.docx_inputs) == 1 else 1)

    converter = FakeConverter()
    service = TailoredResumePdfService(converter=converter)
    bundle = {
        "id": 1,
        "resume_rewrite": "\n".join(f"第 {index} 行简历正文，需要被压缩。" for index in range(20)),
        "project_rewrite": "旧项目改写字段不应优先使用。",
    }

    pdf_bytes = service.render(bundle, _docx_with_editable_body_and_image())

    assert len(converter.docx_inputs) == 2
    assert len(PdfReader(BytesIO(pdf_bytes)).pages) == 1
