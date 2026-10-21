"""
Text out of the documents a user attaches in the assistant chat.

The chat sends images straight to the model (vision); everything else comes here first
(``POST /ai/extract``) and the app puts the text into the conversation. Supported:

* **PDF** — ``pypdf``; each page prefixed ``--- page N ---``. A PDF without a text layer
  (a scan) comes back with a note asking for photos of the pages instead.
* **Word (.docx)** — ``word/document.xml``: paragraphs as lines, table rows tab-separated.
* **Excel (.xlsx)** — shared strings + cell values of the first sheets, rows tab-separated.
* **Text** — .txt .csv .tsv .md .json .geojson .kml .gpx .xml (UTF-8, or UTF-16 with a BOM).

Safety: the decoded file is capped (``MAX_BYTES``), zip members are read with a running
uncompressed budget (zip bombs), XML with a DOCTYPE is refused (entity expansion) and at most
``MAX_PDF_PAGES`` pages / ``MAX_SHEETS`` sheets are read.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

MAX_BYTES = 15 * 1024 * 1024          # decoded upload
MAX_UNZIPPED = 30 * 1024 * 1024       # total uncompressed bytes read out of a .docx / .xlsx
MAX_PDF_PAGES = 60
MAX_SHEETS = 3
MAX_SHEET_ROWS = 2000
MAX_COLS = 60
MAX_TEXT = 24_000                     # characters returned to the app

TEXT_EXTENSIONS = {".txt", ".csv", ".tsv", ".md", ".json", ".geojson", ".kml", ".gpx", ".xml"}
UNSUPPORTED = "This file type can't be read — send a PDF, Word, Excel, text/CSV or an image"
SCANNED_NOTE = "This PDF has no text layer (scanned). Ask the user to send photos / screenshots of the pages instead."

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class ExtractError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ input


def max_b64_chars() -> int:
    """Longest base64 text that can decode to ``MAX_BYTES`` (plus room for a data-URL header)."""
    return MAX_BYTES * 4 // 3 + 512


def decode_data_url(data_url: str) -> Tuple[bytes, str]:
    """``data:<mime>;base64,<data>`` or bare base64 -> (bytes, mime). Raises ExtractError."""
    raw = (data_url or "").strip()
    mime = ""
    if raw.startswith("data:"):
        header, _, raw = raw.partition(",")
        mime = header[5:].split(";")[0].strip().lower()
        if ";base64" not in header.lower():
            raise ExtractError("The file must be sent as a base64 data URL")
    if len(raw) > max_b64_chars():
        raise ExtractError(too_big_message(), status=413)
    raw = re.sub(r"\s+", "", raw)
    try:
        data = base64.b64decode(raw + "=" * (-len(raw) % 4), validate=False)
    except (binascii.Error, ValueError):
        raise ExtractError("The file is not valid base64")
    if not data:
        raise ExtractError("The file is empty")
    if len(data) > MAX_BYTES:
        raise ExtractError(too_big_message(), status=413)
    return data, mime


def too_big_message() -> str:
    return f"This file is too large to read — the limit is {MAX_BYTES // (1024 * 1024)} MB. Send a smaller file or only the pages you need."


# ------------------------------------------------------------------ detection


def _ext(name: str) -> str:
    m = re.search(r"(\.[A-Za-z0-9]+)$", (name or "").strip())
    return m.group(1).lower() if m else ""


def detect(name: str, data: bytes, mime: str = "") -> str:
    """'pdf' | 'docx' | 'xlsx' | 'text' | 'image' | '' (unsupported). Magic bytes first."""
    head = data[:16]
    # PDF readers allow junk before the header; only trust that for a .pdf name.
    if data.lstrip()[:5] == b"%PDF-" or (b"%PDF-" in data[:1024] and _ext(name) == ".pdf"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
        except (zipfile.BadZipFile, ValueError):
            return ""
        if "word/document.xml" in names:
            return "docx"
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
        return ""
    if (head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG") or head[:6] in (b"GIF87a", b"GIF89a")
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
        return "image"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff") or head.startswith(b"\xef\xbb\xbf"):
        return "text"
    ext = _ext(name)
    if ext in TEXT_EXTENSIONS or mime.startswith("text/") or mime in ("application/json", "application/geo+json",
                                                                         "application/xml"):
        return "text" if b"\x00" not in data[:4096] else ""
    return ""


# ------------------------------------------------------------------ zip helpers


class _ZipBudget:
    """Reads zip members while keeping the total uncompressed size under ``MAX_UNZIPPED``."""

    def __init__(self, zf: zipfile.ZipFile) -> None:
        self.zf = zf
        self.left = MAX_UNZIPPED

    def read(self, member: str) -> Optional[bytes]:
        try:
            info = self.zf.getinfo(member)
        except KeyError:
            return None
        if info.file_size > self.left:
            raise ExtractError("This document is too large once unpacked to read safely", status=413)
        with self.zf.open(info) as fh:
            blob = fh.read(self.left + 1)
        if len(blob) > self.left:  # the header lied about the size
            raise ExtractError("This document is too large once unpacked to read safely", status=413)
        self.left -= len(blob)
        return blob

    def xml(self, member: str) -> Optional[ET.Element]:
        blob = self.read(member)
        if blob is None:
            return None
        if b"<!DOCTYPE" in blob[:4096] or b"<!ENTITY" in blob[:4096]:
            raise ExtractError("This document contains content that can't be read safely", status=422)
        try:
            return ET.fromstring(blob)
        except ET.ParseError:
            raise ExtractError("This document is damaged and can't be read", status=422)


def _open_zip(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError):
        raise ExtractError("This document is damaged and can't be read", status=422)


# ------------------------------------------------------------------ DOCX


def _docx_runs(elem: ET.Element) -> str:
    out: List[str] = []
    for node in elem.iter():
        tag = node.tag
        if tag == _W + "t" and node.text:
            out.append(node.text)
        elif tag == _W + "tab":
            out.append("\t")
        elif tag in (_W + "br", _W + "cr"):
            out.append("\n")
    return "".join(out)


def _docx_block(elem: ET.Element, lines: List[str]) -> None:
    for child in elem:
        if child.tag == _W + "p":
            lines.append(_docx_runs(child))
        elif child.tag == _W + "tbl":
            for row in child.iter(_W + "tr"):
                cells = [" ".join(_docx_runs(p) for p in tc.iter(_W + "p")).strip()
                         for tc in row if tc.tag == _W + "tc"]
                if any(cells):
                    lines.append("\t".join(cells))
        elif child.tag != _W + "sectPr":
            _docx_block(child, lines)  # content controls (w:sdt / w:sdtContent) and the like


def extract_docx(data: bytes) -> Dict[str, Any]:
    with _open_zip(data) as zf:
        root = _ZipBudget(zf).xml("word/document.xml")
    if root is None:
        raise ExtractError("This Word document is damaged and can't be read", status=422)
    body = root.find(_W + "body")
    lines: List[str] = []
    _docx_block(body if body is not None else root, lines)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return {"kind": "docx", "pages": None, "text": text,
            "note": None if text else "This Word document has no text in it."}


# ------------------------------------------------------------------ XLSX


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if "A" <= ch <= "Z":
            n = n * 26 + (ord(ch) - 64)
        else:
            break
    return max(0, n - 1)


def _xlsx_sheets(budget: _ZipBudget) -> List[Tuple[str, str]]:
    """[(sheet name, zip member)] in workbook order."""
    names = budget.zf.namelist()
    book = budget.xml("xl/workbook.xml")
    rels = budget.xml("xl/_rels/workbook.xml.rels")
    targets: Dict[str, str] = {}
    if rels is not None:
        for rel in rels.iter(_PKG_REL + "Relationship"):
            target = rel.get("Target") or ""
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            targets[rel.get("Id") or ""] = target
    out: List[Tuple[str, str]] = []
    if book is not None:
        for sheet in book.iter(_S + "sheet"):
            member = targets.get(sheet.get(_R + "id") or "")
            if member and member in names:
                out.append((sheet.get("name") or member, member))
    if not out:
        files = sorted((n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                       key=lambda n: int(re.findall(r"\d+", n)[-1]))
        out = [(f"Sheet{i + 1}", n) for i, n in enumerate(files)]
    return out


def extract_xlsx(data: bytes) -> Dict[str, Any]:
    with _open_zip(data) as zf:
        budget = _ZipBudget(zf)
        shared: List[str] = []
        sst = budget.xml("xl/sharedStrings.xml")
        if sst is not None:
            for si in sst.iter(_S + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_S + "t")))
        sheets = _xlsx_sheets(budget)
        blocks: List[str] = []
        for name, member in sheets[:MAX_SHEETS]:
            root = budget.xml(member)
            if root is None:
                continue
            rows: List[str] = []
            for row in root.iter(_S + "row"):
                if len(rows) >= MAX_SHEET_ROWS:
                    rows.append(f"… (only the first {MAX_SHEET_ROWS} rows were read)")
                    break
                values: Dict[int, str] = {}
                for pos, cell in enumerate(row.iter(_S + "c")):
                    col = _col_index(cell.get("r") or "") if cell.get("r") else pos
                    if col >= MAX_COLS:
                        continue
                    kind = cell.get("t")
                    v = cell.find(_S + "v")
                    if kind == "s" and v is not None and (v.text or "").strip().isdigit():
                        idx = int(v.text.strip())
                        value = shared[idx] if idx < len(shared) else ""
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(_S + "t"))
                    elif kind == "b" and v is not None:
                        value = "TRUE" if (v.text or "").strip() == "1" else "FALSE"
                    else:
                        value = (v.text or "") if v is not None else ""
                    value = value.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
                    if value:
                        values[col] = value
                if values:
                    width = max(values) + 1
                    rows.append("\t".join(values.get(i, "") for i in range(width)).rstrip("\t"))
            blocks.append(f"--- sheet {name} ---\n" + "\n".join(rows))
    text = "\n\n".join(blocks).strip()
    note = None
    if len(sheets) > MAX_SHEETS:
        note = f"Only the first {MAX_SHEETS} of {len(sheets)} sheets were read."
    if not any(b.count("\n") for b in blocks):
        note = "This spreadsheet has no values in it."
    return {"kind": "xlsx", "pages": None, "text": text, "note": note}


# ------------------------------------------------------------------ PDF


def extract_pdf(data: bytes) -> Dict[str, Any]:
    try:
        import pypdf
        from pypdf.errors import PdfReadError
    except ImportError:  # pragma: no cover - dependency missing
        raise ExtractError("PDF reading is not installed on the server (pypdf)", status=501)
    try:
        reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:
                ok = 0
            if not ok:
                return {"kind": "pdf", "pages": None, "text": "",
                        "note": "This PDF is password-protected. Ask the user to send an unlocked copy, or photos / screenshots of the pages."}
        total = len(reader.pages)
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ExtractError(f"This PDF is damaged and can't be read ({type(exc).__name__})", status=422)
    parts: List[str] = []
    visible = 0  # non-whitespace characters: tells a real text layer from a scan
    read = min(total, MAX_PDF_PAGES)
    for i in range(read):
        try:
            page_text = (reader.pages[i].extract_text() or "").strip()
        except Exception:  # one broken page should not lose the rest
            page_text = ""
        visible += len(re.sub(r"\s+", "", page_text))
        parts.append(f"--- page {i + 1} ---\n{page_text}")
    text = "\n\n".join(parts).strip()
    notes: List[str] = []
    if visible < 20 * max(1, read):
        notes.append(SCANNED_NOTE)
    if total > read:
        notes.append(f"Only the first {read} of {total} pages were read.")
    return {"kind": "pdf", "pages": total, "text": text, "note": " ".join(notes) or None}


# ------------------------------------------------------------------ text


def extract_text(data: bytes) -> Dict[str, Any]:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16", errors="replace")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return {"kind": "text", "pages": None, "text": text, "note": None if text else "This file is empty."}


# ------------------------------------------------------------------ entry point


def extract(name: str, data: bytes, mime: str = "") -> Dict[str, Any]:
    """Text of one attached file -> the ``/ai/extract`` response. Raises ExtractError."""
    if not data:
        raise ExtractError("The file is empty")
    if len(data) > MAX_BYTES:
        raise ExtractError(too_big_message(), status=413)
    kind = detect(name, data, mime)
    if kind == "image":
        raise ExtractError("Images are sent to the assistant directly — attach them as pictures, not documents", status=415)
    reader = {"pdf": extract_pdf, "docx": extract_docx, "xlsx": extract_xlsx, "text": extract_text}.get(kind)
    if reader is None:
        raise ExtractError(UNSUPPORTED, status=415)
    result = reader(data)
    full = result.pop("text") or ""
    return {"name": name, "kind": result["kind"], "pages": result["pages"], "chars": len(full),
            "text": full[:MAX_TEXT], "truncated": len(full) > MAX_TEXT, "note": result["note"]}
