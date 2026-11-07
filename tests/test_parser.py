from pathlib import Path

import pytest
from docx import Document

from document_parser import parse_file

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_utf8_text_keeps_lines(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("第一行  內容\n\n\n第二行\n", encoding="utf-8")
    assert parse_file(path)[0].text == "第一行 內容\n第二行"


def test_big5_text(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("臺中市西屯區", encoding="cp950")
    assert parse_file(path)[0].text == "臺中市西屯區"


def test_nul_characters_are_removed(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("甲\x00乙", encoding="utf-8")
    assert "\x00" not in parse_file(path)[0].text


def test_docx_reads_paragraphs_and_tables(tmp_path):
    document = Document()
    document.add_paragraph("段落內容")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "項目"
    table.cell(0, 1).text = "金額"
    path = tmp_path / "a.docx"
    document.save(path)

    text = parse_file(path)[0].text
    assert "段落內容" in text
    assert "項目 | 金額" in text


def test_pdf_keeps_page_numbers():
    sections = parse_file(SAMPLES / "報價單.pdf")
    assert [section.page for section in sections] == [1, 2]
    assert "雲端主機" in sections[0].text


def test_pdf_without_text_is_rejected():
    with pytest.raises(ValueError, match="掃描檔"):
        parse_file(SAMPLES / "掃描檔模擬.pdf")


def test_blank_file_error_uses_given_filename(tmp_path):
    path = tmp_path / "upload.txt"
    path.write_text("  ", encoding="utf-8")
    with pytest.raises(ValueError, match="空白.txt"):
        parse_file(path, "空白.txt")


def test_unsupported_type_is_rejected(tmp_path):
    path = tmp_path / "a.exe"
    path.write_bytes(b"x")
    with pytest.raises(ValueError, match="不支援"):
        parse_file(path)
