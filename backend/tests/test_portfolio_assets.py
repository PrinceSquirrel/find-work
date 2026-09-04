from pathlib import Path
from zipfile import ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_ROOT = PROJECT_ROOT / "outputs" / "trusted-evidence-portfolio-20260817"


def assert_office_package(filename: str, required_entry: str) -> None:
    path = PORTFOLIO_ROOT / filename
    assert path.stat().st_size > 10_000
    with ZipFile(path) as package:
        assert package.testzip() is None
        assert required_entry in package.namelist()


def test_research_prd_and_evaluation_workbook_are_valid_office_files() -> None:
    assert_office_package("可信经历资料库_用户研究与访谈执行包.docx", "word/document.xml")
    assert_office_package("可信经历资料库_PRD.docx", "word/document.xml")
    assert_office_package("可信经历资料库_AI评测数据集.xlsx", "xl/workbook.xml")


def test_evaluation_report_and_interview_portfolio_are_valid_documents() -> None:
    assert_office_package("可信经历资料库_AI效果评测报告.docx", "word/document.xml")
    assert_office_package("可信经历资料库_作品集与面试包.docx", "word/document.xml")
