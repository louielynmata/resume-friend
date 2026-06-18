import re
from pathlib import Path
from typing import Optional
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


async def build_documents(
    ai_response: str,
    owner_name: str,
    position_slug: str,
    output_dir: Path,
) -> dict:
    resume_text = _extract_tag(ai_response, "RESUME")
    cl_text = _extract_tag(ai_response, "COVER_LETTER")

    result: dict = {}

    if resume_text:
        docx_path = _resolve_output_path(output_dir / f"{owner_name}_Resume_{position_slug}.docx")
        docx_path = _build_resume_docx(resume_text, docx_path)
        result["resume_docx"] = str(docx_path)
        result["resume_pdf"] = _to_pdf(docx_path)
    else:
        raise ValueError("AI response did not contain a <RESUME> section.")

    if cl_text:
        cl_path = _resolve_output_path(output_dir / f"{owner_name}_CoverLetter_{position_slug}.docx")
        cl_path = _build_cover_letter_docx(cl_text, cl_path)
        result["cover_letter_docx"] = str(cl_path)
        result["cover_letter_pdf"] = _to_pdf(cl_path)
    else:
        raise ValueError("AI response did not contain a <COVER_LETTER> section.")

    return result


# ── Parsing ────────────────────────────────────────────────────────────────────

def _extract_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _resolve_output_path(path: Path) -> Path:
    if not path.exists():
        return path

    if _is_locked_word_document(path):
        return _next_available_path(path)

    return path


def _next_available_path(path: Path) -> Path:
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"Could not find an available output filename for {path.name}.")


def _is_locked_word_document(path: Path) -> bool:
    names = [f"~${path.name}"]
    if len(path.name) >= 2:
        names.append(f"~${path.name[2:]}")
    return any(path.with_name(name).exists() for name in names)


def _normalize_document_text(content: str) -> list[str]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*", "", normalized)
    normalized = re.sub(r"\s*```$", "", normalized)

    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        line = re.sub(r"^\s{0,3}(?:[-*+]\s|\d+\.\s)", "- ", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", line)
        line = re.sub(r"[*_`~]+", "", line)
        line = re.sub(r"\s{2,}", " ", line).strip()
        lines.append(line)

    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    return lines


def _resume_line_kind(line: str, index: int) -> tuple[str, str]:
    if not line:
        return "blank", ""

    legacy_name = re.match(r"^#\s+(.+)$", line)
    if legacy_name:
        return "name", legacy_name.group(1).strip()

    name_match = re.match(r"^\[?(?:NAME|FULL NAME)\s*:\s*(.+?)\]?$", line, re.IGNORECASE)
    if name_match:
        return "name", name_match.group(1).strip()

    contact_match = re.match(r"^\[?(?:CONTACT|CONTACT INFO)\s*:\s*(.+?)\]?$", line, re.IGNORECASE)
    if contact_match:
        return "contact", contact_match.group(1).strip()

    legacy_section = re.match(r"^##\s+(.+)$", line)
    if legacy_section:
        return "section", legacy_section.group(1).strip()

    if re.fullmatch(r"[A-Z][A-Z /&-]{2,}", line):
        return "section", line

    legacy_entry = re.match(r"^###\s+(.+)$", line)
    if legacy_entry:
        return "entry", legacy_entry.group(1).strip()

    if line.startswith("- "):
        return "bullet", line[2:].strip()

    if index <= 2 and "|" in line:
        return "contact", line

    if "|" in line and index > 2:
        return "entry", line

    return "body", line


def _cover_letter_lines(content: str) -> list[str]:
    lines = _normalize_document_text(content)
    return [re.sub(r"^#{1,6}\s*", "", line).strip() if line else "" for line in lines]


# ── Resume .docx ───────────────────────────────────────────────────────────────

def _build_resume_docx(content: str, path: Path) -> Path:
    doc = Document()
    _set_margins(doc, top=0.75, bottom=0.75, left=0.9, right=0.9)
    _set_default_font(doc)

    lines = _normalize_document_text(content)
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        kind, value = _resume_line_kind(line, i)

        if kind == "blank":
            i += 1
            continue

        if kind == "name":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(value)
            run.bold = True
            _set_run_font(run, size=20)
            _set_para_spacing(p, before=0, after=2)

        elif kind == "contact":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(value)
            _set_run_font(run, size=10)
            _set_para_spacing(p, before=0, after=2)

        elif kind == "section":
            _add_section_header(doc, value)

        elif kind == "entry":
            _add_entry_header(doc, value)

        elif kind == "bullet":
            p = doc.add_paragraph(style="List Bullet")
            _set_run_font(p.add_run(value), size=10)
            _set_para_spacing(p, before=0, after=1)

        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(value)
            _set_run_font(run, size=10)
            _set_para_spacing(p, before=0, after=2)

        i += 1

    return _save_document(doc, path)


def _add_section_header(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    _set_para_spacing(p, before=6, after=2)
    run = p.add_run(text.upper())
    run.bold = True
    _set_run_font(run, size=11)
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
    _add_bottom_border(p)


def _add_entry_header(doc: Document, text: str) -> None:
    parts = [p.strip() for p in text.split("|")]
    p = doc.add_paragraph()
    _set_para_spacing(p, before=3, after=1)
    if parts:
        run = p.add_run(parts[0])
        run.bold = True
        _set_run_font(run, size=11)
    if len(parts) > 1:
        run = p.add_run("  |  " + "  |  ".join(parts[1:]))
        _set_run_font(run, size=10)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


# ── Cover Letter .docx ─────────────────────────────────────────────────────────

def _build_cover_letter_docx(content: str, path: Path) -> Path:
    doc = Document()
    _set_margins(doc, top=1.0, bottom=1.0, left=1.1, right=1.1)
    _set_default_font(doc)

    for line in _cover_letter_lines(content):
        if not line:
            doc.add_paragraph()
            continue
        p = doc.add_paragraph()
        _set_run_font(p.add_run(line), size=11)
        _set_para_spacing(p, before=0, after=4)

    return _save_document(doc, path)


# ── PDF conversion ─────────────────────────────────────────────────────────────

def _to_pdf(docx_path: Path) -> Optional[str]:
    try:
        from docx2pdf import convert
        pdf_path = docx_path.with_suffix(".pdf")
        convert(str(docx_path), str(pdf_path))
        return str(pdf_path) if pdf_path.exists() else None
    except Exception:
        return None  # PDF conversion is best-effort; .docx always saved


# ── Helpers ────────────────────────────────────────────────────────────────────

def _set_margins(doc: Document, top: float, bottom: float, left: float, right: float) -> None:
    for section in doc.sections:
        section.top_margin = Inches(top)
        section.bottom_margin = Inches(bottom)
        section.left_margin = Inches(left)
        section.right_margin = Inches(right)


def _set_default_font(doc: Document) -> None:
    normal_style = doc.styles["Normal"]
    _apply_font_family(normal_style.font)
    normal_style.font.size = Pt(10)


def _set_run_font(run, size: int) -> None:
    _apply_font_family(run.font)
    run.font.size = Pt(size)


def _apply_font_family(font) -> None:
    font.name = "Poppins"
    font._element.rPr.rFonts.set(qn("w:ascii"), "Poppins")
    font._element.rPr.rFonts.set(qn("w:hAnsi"), "Poppins")
    font._element.rPr.rFonts.set(qn("w:eastAsia"), "Poppins")
    font._element.rPr.rFonts.set(qn("w:cs"), "Poppins")


def _save_document(doc: Document, path: Path) -> Path:
    try:
        doc.save(str(path))
        return path
    except PermissionError:
        fallback_path = _next_available_path(path)
        doc.save(str(fallback_path))
        return fallback_path


def _set_para_spacing(p, before: int = 0, after: int = 4) -> None:
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)


def _add_bottom_border(paragraph) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "CCCCCC")
    pBdr.append(bottom)
    pPr.append(pBdr)
