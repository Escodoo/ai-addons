# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import html
import io
import logging
import re

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_EXPORT_CONTENT_MAX_LEN = 200000
_HTML_HINTS = ("<p", "<h1", "<h2", "<h3", "<ul", "<ol", "<table", "<div")

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")
_UL_RE = re.compile(r"^[-*]\s+(.+)$")
_OL_RE = re.compile(r"^(\d+)[.)]\s+(.+)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _safe_filename(name, suffix):
    raw = (name or "assistant-briefing").strip() or "assistant-briefing"
    cleaned = _FILENAME_RE.sub("-", raw).strip("-._") or "assistant-briefing"
    if not cleaned.lower().endswith(suffix):
        cleaned = f"{cleaned}{suffix}"
    return cleaned[:120]


def _is_pipe_row(line):
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_pipe_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _inline_html(text):
    escaped = html.escape(text or "", quote=False)
    return _BOLD_RE.sub(r"<b>\1</b>", escaped)


def _table_html(rows):
    if not rows:
        return ""
    header, *body = rows
    parts = ["<table>"]
    if header:
        parts.append("<thead><tr>")
        parts.extend(f"<th>{_inline_html(cell)}</th>" for cell in header)
        parts.append("</tr></thead>")
    if body:
        parts.append("<tbody>")
        for row in body:
            parts.append("<tr>")
            padded = list(row) + [""] * max(0, len(header) - len(row))
            parts.extend(
                f"<td>{_inline_html(cell)}</td>" for cell in padded[: len(header)]
            )
            parts.append("</tr>")
        parts.append("</tbody>")
    parts.append("</table>")
    return "".join(parts)


def markdownish_to_html(content):
    """Turn briefing text (Markdown-ish or loose HTML) into report fragments."""
    text = (content or "").replace("\r\n", "\n")
    lowered = text.lower()
    if any(hint in lowered for hint in _HTML_HINTS):
        return text
    lines = text.split("\n")
    parts = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _is_pipe_row(line):
            rows = []
            while index < len(lines) and (
                _is_pipe_row(lines[index]) or _TABLE_SEP_RE.match(lines[index])
            ):
                if not _TABLE_SEP_RE.match(lines[index]):
                    rows.append(_split_pipe_row(lines[index]))
                index += 1
            parts.append(_table_html(rows))
            continue
        heading = _HEADING_RE.match(line.strip())
        if heading:
            level = min(len(heading.group(1)), 3)
            parts.append(f"<h{level}>{_inline_html(heading.group(2))}</h{level}>")
            index += 1
            continue
        unordered = _UL_RE.match(line.strip())
        if unordered:
            parts.append("<ul>")
            while index < len(lines):
                item = _UL_RE.match(lines[index].strip())
                if not item:
                    break
                parts.append(f"<li>{_inline_html(item.group(1))}</li>")
                index += 1
            parts.append("</ul>")
            continue
        ordered = _OL_RE.match(line.strip())
        if ordered:
            parts.append("<ol>")
            while index < len(lines):
                item = _OL_RE.match(lines[index].strip())
                if not item:
                    break
                parts.append(f"<li>{_inline_html(item.group(2))}</li>")
                index += 1
            parts.append("</ol>")
            continue
        if line.strip():
            parts.append(f"<p>{_inline_html(line.strip())}</p>")
        index += 1
    return "".join(parts)


def wrap_report_html(title, inner_html):
    heading = html.escape((title or "Report").strip() or "Report")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{heading}</title>
<style>
  body {{
    font-family: DejaVu Sans, Liberation Sans, Arial, sans-serif;
    font-size: 12px;
    color: #111827;
    margin: 0;
    line-height: 1.45;
  }}
  .page {{
    padding: 8px 48px 20px;
  }}
  h1 {{ font-size: 20px; margin: 0 0 16px; }}
  h2 {{ font-size: 15px; margin: 18px 0 8px; }}
  h3 {{ font-size: 13px; margin: 14px 0 6px; }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0 16px;
  }}
  th, td {{
    border: 1px solid #d1d5db;
    padding: 6px 8px;
    text-align: left;
    vertical-align: top;
  }}
  th {{ background: #f3f4f6; font-weight: 600; }}
  ul, ol {{ margin: 0 0 12px 20px; }}
  p {{ margin: 0 0 8px; }}
</style>
</head>
<body>
<div class="page">
<h1>{heading}</h1>
{inner_html}
</div>
</body>
</html>
"""


def _plain_text_to_pdf(title, body):
    """Fallback single-page PDF when wkhtmltopdf is unavailable."""
    title_text = (title or "Report").strip()[:80]
    paragraphs = (body or "").replace("\r\n", "\n").split("\n")
    wrapped = []
    for paragraph in paragraphs:
        line = paragraph.strip() or " "
        while len(line) > 90:
            wrapped.append(line[:90])
            line = line[90:]
        wrapped.append(line)
        if len(wrapped) >= 48:
            break
        if not wrapped:  # pragma: no cover
            wrapped = [" "]

    def _escape(text):
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream_lines = ["BT", "/F1 14 Tf", "50 750 Td", f"({_escape(title_text)}) Tj"]
    stream_lines += ["0 -24 Td", "/F1 11 Tf"]
    for line in wrapped:
        stream_lines.append(f"({_escape(line)}) Tj")
        stream_lines.append("0 -14 Td")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        encoded = f"{index} 0 obj\n{obj}\nendobj\n"
        output.write(encoded.encode("latin-1", errors="replace"))
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    )
    output.write(trailer.encode())
    return output.getvalue()


class AiAssistantArtifacts(models.AbstractModel):
    _inherit = "ai.assistant"  # pylint: disable=consider-merging-classes-inherited

    @api.model
    def _html_report_to_pdf(self, html_doc):
        """Render UTF-8 HTML via wkhtmltopdf so tables and accents survive.

        Company paperformats reserve ~40 mm + header-spacing for a letterhead
        we never render. Keep a small paper margin and let the HTML padding
        provide the visible gutter.
        """
        if not html_doc:
            return b""
        try:
            pdf = self.env["ir.actions.report"]._run_wkhtmltopdf(
                [html_doc],
                specific_paperformat_args={
                    "data-report-margin-top": 16,
                    "data-report-margin-bottom": 16,
                    "data-report-header-spacing": 0,
                },
            )
        except Exception:  # noqa: BLE001 - fall back to the built-in text PDF
            _logger.warning("wkhtmltopdf failed for assistant report", exc_info=True)
            return b""
        if isinstance(pdf, bytes | bytearray) and pdf.startswith(b"%PDF"):
            return bytes(pdf)
        return b""

    @api.model
    def action_ai_export_message(self, content=None, title=None, export_format=None):
        """Build a Markdown or PDF download without storing an attachment."""
        self._check_ai_user()
        text = content if isinstance(content, str) else ""
        if not text.strip():
            raise UserError(_("Nothing to export."))
        if len(text) > _EXPORT_CONTENT_MAX_LEN:
            text = text[:_EXPORT_CONTENT_MAX_LEN]
        heading = (
            title if isinstance(title, str) and title.strip() else "Assistant briefing"
        )
        fmt = (export_format or "markdown").strip().lower()
        if fmt in {"md", "markdown"}:
            raw = f"# {heading.strip()}\n\n{text.strip()}\n".encode()
            return {
                "filename": _safe_filename(heading, ".md"),
                "mimetype": "text/markdown",
                "datas": base64.b64encode(raw).decode(),
            }
        if fmt != "pdf":
            raise UserError(_("Unsupported export format."))
        html_doc = wrap_report_html(heading, markdownish_to_html(text))
        raw = self._html_report_to_pdf(html_doc) or _plain_text_to_pdf(heading, text)
        return {
            "filename": _safe_filename(heading, ".pdf"),
            "mimetype": "application/pdf",
            "datas": base64.b64encode(raw).decode(),
        }
