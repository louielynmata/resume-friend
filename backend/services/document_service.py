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
        docx_path = output_dir / f"{owner_name}_Resume_{position_slug}.docx"
        _build_resume_docx(resume_text, docx_path)
        result["resume_docx"] = str(docx_path)
        result["resume_pdf"] = _to_pdf(docx_path)
    else:
        raise ValueError("AI response did not contain a <RESUME> section.")

    if cl_text:
        cl_path = output_dir / f"{owner_name}_CoverLetter_{position_slug}.docx"
        _build_cover_letter_docx(cl_text, cl_path)
        result["cover_letter_docx"] = str(cl_path)
        result["cover_letter_pdf"] = _to_pdf(cl_path)
    else:
        raise ValueError("AI response did not contain a <COVER_LETTER> section.")

    return result


# ── Parsing ────────────────────────────────────────────────────────────────────

def _extract_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


# ── Resume .docx ───────────────────────────────────────────────────────────────

def _build_resume_docx(content: str, path: Path) -> None:
    doc = Document()
    _set_margins(doc, top=0.75, bottom=0.75, left=0.9, right=0.9)

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.startswith("# "):  # Name
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(line[2:].strip())
            run.bold = True
            run.font.size = Pt(20)
            _set_para_spacing(p, before=0, after=2)

        elif line.startswith("## "):  # Section header
            _add_section_header(doc, line[3:].strip())

        elif line.startswith("### "):  # Sub-entry (job title / degree)
            _add_entry_header(doc, line[4:].strip())

        elif line.startswith("- "):  # Bullet
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(line[2:].strip()).font.size = Pt(10)
            _set_para_spacing(p, before=0, after=1)

        else:  # Contact line or body text
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i < 3 else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(line)
            run.font.size = Pt(10)
            _set_para_spacing(p, before=0, after=2)

        i += 1

    doc.save(str(path))


def _add_section_header(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    _set_para_spacing(p, before=6, after=2)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
    _add_bottom_border(p)


def _add_entry_header(doc: Document, text: str) -> None:
    parts = [p.strip() for p in text.split("|")]
    p = doc.add_paragraph()
    _set_para_spacing(p, before=3, after=1)
    if parts:
        run = p.add_run(parts[0])
        run.bold = True
        run.font.size = Pt(11)
    if len(parts) > 1:
        run = p.add_run("  |  " + "  |  ".join(parts[1:]))
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


# ── Cover Letter .docx ─────────────────────────────────────────────────────────

def _build_cover_letter_docx(content: str, path: Path) -> None:
    doc = Document()
    _set_margins(doc, top=1.0, bottom=1.0, left=1.1, right=1.1)

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            doc.add_paragraph()
            continue
        p = doc.add_paragraph()
        p.add_run(line).font.size = Pt(11)
        _set_para_spacing(p, before=0, after=4)

    doc.save(str(path))


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
