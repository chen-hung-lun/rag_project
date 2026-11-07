"""從檔案取出文字，PDF 會保留頁碼。

支援 PDF、Word（.docx）、TXT、Markdown。
每種格式都轉成 Section（頁碼 + 文字）清單，後面的切塊程式就不用管原本是什麼格式。
"""
from pathlib import Path
from typing import NamedTuple

from docx import Document
from pypdf import PdfReader

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class Section(NamedTuple):
    """一段文字。PDF 一頁一段；其他格式沒有頁碼，整份一段，page 為 None。"""
    page: int | None
    text: str


def _clean(text: str) -> str:
    """每行的連續空白壓成一個，並去掉空行。"""
    # PostgreSQL 的 TEXT 不能存 NUL；保留換行，切塊時才知道段落在哪裡
    lines = (" ".join(line.split()) for line in text.replace("\x00", " ").splitlines())
    return "\n".join(line for line in lines if line)


def _parse_pdf(path: Path) -> list[Section]:
    """一頁一個 Section，頁碼從 1 開始。掃描檔沒有文字層，會取到空字串。"""
    reader = PdfReader(path)
    # PDF 的換行是版面造成的，常在句子中間，不能當段落
    return [
        Section(number, " ".join((page.extract_text() or "").split()))
        for number, page in enumerate(reader.pages, start=1)
    ]


def _parse_docx(path: Path) -> list[Section]:
    """取出段落和表格；表格每列用 | 隔開儲存格。"""
    document = Document(path)
    lines = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return [Section(None, "\n".join(lines))]


def _parse_text(path: Path, filename: str) -> list[Section]:
    """依序試 UTF-8 和 Big5，能解開就用。"""
    data = path.read_bytes()
    # 台灣的舊文字檔常是 Big5（cp950）
    # utf-8-sig 會順便去掉 Windows 記事本加在開頭的 BOM
    for encoding in ("utf-8-sig", "cp950"):
        try:
            return [Section(None, data.decode(encoding))]
        except UnicodeDecodeError:
            continue
    raise ValueError(f"無法判斷文字編碼：{filename}")


def parse_file(path: Path, filename: str | None = None) -> list[Section]:
    """依副檔名選擇解析方式，回傳清理過、非空白的段落。"""
    filename = filename or path.name
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        sections = _parse_pdf(path)
    elif suffix == ".docx":
        sections = _parse_docx(path)
    elif suffix in SUPPORTED_SUFFIXES:
        sections = _parse_text(path, filename)
    else:
        raise ValueError(f"不支援的檔案類型：{suffix or filename}")

    cleaned = [Section(section.page, _clean(section.text)) for section in sections]
    cleaned = [section for section in cleaned if section.text]
    # 全部都是空的，通常是掃描成圖片的 PDF，需要先做文字辨識（OCR）
    if not cleaned:
        raise ValueError(f"讀不到文字，可能是掃描檔或空白檔案：{filename}")
    return cleaned
