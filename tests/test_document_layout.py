import tempfile
import unittest
from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from backend.services.document_service import (
    _build_cover_letter_docx,
    _build_resume_docx,
)


RESUME_TEXT = """NAME: Alex Example
ROLE: Product Designer
CONTACT: alex@example.com

WORK EXPERIENCE
PRODUCT DESIGNER
Example Studio | Calgary
2020 - Present
● Built accessible customer workflows.

EDUCATION
Example University | Design Diploma
Second University | Arts Degree

CERTIFICATIONS
● Example Certification
"""

COVER_LETTER_TEXT = """Cover Letter

Dear Hiring Team,

I design accessible products and would bring that focus to this role.

I would welcome the opportunity to contribute to the team.

Sincerely,
Alex Example
"""


def paragraph_starting_with(document: Document, prefix: str):
    return next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.startswith(prefix)
    )


class DocumentLayoutTests(unittest.TestCase):
    def test_resume_keeps_entry_headers_with_first_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(RESUME_TEXT, path)
            document = Document(path)

            work_header = paragraph_starting_with(document, "WORK EXPERIENCE")
            role_header = paragraph_starting_with(document, "PRODUCT DESIGNER")
            company = paragraph_starting_with(document, "Example Studio")
            date_range = paragraph_starting_with(document, "2020 - Present")
            first_bullet = paragraph_starting_with(
                document,
                "Built accessible customer workflows.",
            )

            self.assertTrue(work_header.paragraph_format.keep_with_next)
            self.assertTrue(role_header.paragraph_format.keep_with_next)
            self.assertTrue(company.paragraph_format.keep_with_next)
            self.assertTrue(date_range.paragraph_format.keep_with_next)
            self.assertTrue(first_bullet.paragraph_format.keep_together)

    def test_resume_keeps_education_group_but_not_next_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(RESUME_TEXT, path)
            document = Document(path)

            education = paragraph_starting_with(document, "EDUCATION")
            first_school = paragraph_starting_with(document, "Example University")
            second_school = paragraph_starting_with(document, "Second University")

            self.assertTrue(education.paragraph_format.keep_with_next)
            self.assertTrue(first_school.paragraph_format.keep_with_next)
            self.assertFalse(second_school.paragraph_format.keep_with_next)
            self.assertEqual(education.paragraph_format.space_before.pt, 4)
            self.assertEqual(education.paragraph_format.space_after.pt, 1)

    def test_cover_letter_uses_compact_spacing_and_keeps_closing_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cover-letter.docx"
            _build_cover_letter_docx(COVER_LETTER_TEXT, path)
            document = Document(path)

            heading = paragraph_starting_with(document, "Cover Letter")
            greeting = paragraph_starting_with(document, "Dear Hiring Team")
            opening = paragraph_starting_with(document, "I design accessible")
            closing = paragraph_starting_with(document, "Sincerely,")
            name = paragraph_starting_with(document, "Alex Example")

            self.assertTrue(heading.paragraph_format.keep_with_next)
            self.assertTrue(greeting.paragraph_format.keep_with_next)
            self.assertEqual(greeting.paragraph_format.space_after.pt, 12)
            self.assertEqual(opening.paragraph_format.space_after.pt, 12)
            self.assertTrue(closing.paragraph_format.keep_with_next)
            self.assertTrue(name.runs[0].bold)
            self.assertEqual(heading.runs[0].font.size.pt, 16)
            self.assertEqual(opening.runs[0].font.size.pt, 12)
            self.assertEqual(opening.runs[0].font.name, "Work Sans")

    def test_resume_uses_reference_typography_geometry_and_category_grid(self):
        content = """NAME: Alex Example
ROLE: Product Designer
CONTACT: alex@example.com

PROFESSIONAL SUMMARY
Designer focused on accessible digital experiences.

---

CORE SKILLS
CATEGORY: Product Design | UX research, prototyping, design systems
CATEGORY: Collaboration | stakeholder workshops, presentations
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(content, path)
            document = Document(path)

            name = paragraph_starting_with(document, "ALEX EXAMPLE")
            summary = paragraph_starting_with(document, "Designer focused")
            section = document.sections[0]

            self.assertEqual(name.runs[0].font.size.pt, 13)
            self.assertEqual(str(name.runs[0].font.color.rgb), "205968")
            self.assertEqual(summary.runs[0].font.size.pt, 8.5)
            self.assertEqual(summary.runs[0].font.name, "Poppins")
            self.assertAlmostEqual(section.top_margin.inches, 0.4, places=2)
            self.assertAlmostEqual(section.bottom_margin.inches, 0.4, places=2)
            self.assertAlmostEqual(section.left_margin.inches, 0.4, places=2)
            self.assertAlmostEqual(section.right_margin.inches, 0.4, places=2)
            self.assertEqual(len(document.tables), 1)
            self.assertEqual(len(document.tables[0].columns), 2)
            self.assertIn("Product Design", document.tables[0].cell(0, 0).text)
            self.assertIn("Collaboration", document.tables[0].cell(0, 1).text)
            self.assertIn(
                "UX research, prototyping, design systems",
                document.tables[0].cell(0, 0).text,
            )
            self.assertNotIn(";", document.tables[0].cell(0, 0).text)
            self.assertIn("PAGE", document.sections[0].footer._element.xml)

    def test_resume_renders_approved_title_case_section_headers_uppercase_and_bold(self):
        content = """NAME: Alex Example
ROLE: Software Developer
CONTACT: alex@example.com

Professional Summary
Developer focused on reliable customer workflows.

---

Work Experience
SOFTWARE DEVELOPER - 2020 - Present
Example Studio | Calgary
\u25cf Built reliable customer workflows.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(content, path)
            document = Document(path)

            paragraph_text = [paragraph.text for paragraph in document.paragraphs]
            self.assertIn("PROFESSIONAL SUMMARY", paragraph_text)
            self.assertIn("WORK EXPERIENCE", paragraph_text)
            summary_heading = paragraph_starting_with(
                document,
                "PROFESSIONAL SUMMARY",
            )
            work_heading = paragraph_starting_with(
                document,
                "WORK EXPERIENCE",
            )

            self.assertTrue(all(run.bold for run in summary_heading.runs))
            self.assertTrue(all(run.bold for run in work_heading.runs))

    def test_resume_matches_reference_work_section_and_entry_hierarchy(self):
        content = """NAME: Alex Example
ROLE: Software Developer
CONTACT: alex@example.com

PROFESSIONAL SUMMARY
Developer focused on reliable customer workflows.

---

Related Work Experiences
Example Labs | Product Engineering
SOFTWARE ENGINEER - 2025
\u25cf Built reliable customer workflows.

Other Experiences
Example Retail | Calgary
SALESPERSON - 2024 - Present
\u25cf Supported customers.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(content, path)
            document = Document(path)

            paragraph_text = [paragraph.text for paragraph in document.paragraphs]
            self.assertIn("RELATED WORK EXPERIENCES", paragraph_text)
            self.assertIn("OTHER EXPERIENCES", paragraph_text)

            related_heading = paragraph_starting_with(
                document,
                "RELATED WORK EXPERIENCES",
            )
            other_heading = paragraph_starting_with(
                document,
                "OTHER EXPERIENCES",
            )
            company = paragraph_starting_with(document, "Example Labs")
            position = paragraph_starting_with(document, "SOFTWARE ENGINEER")

            self.assertTrue(all(run.bold for run in related_heading.runs))
            self.assertTrue(all(run.bold for run in other_heading.runs))
            self.assertEqual(company.runs[0].text, "Example Labs")
            self.assertTrue(company.runs[0].bold)
            self.assertNotEqual(company.runs[0].text, company.runs[0].text.upper())
            self.assertEqual(position.runs[0].text, "SOFTWARE ENGINEER")
            self.assertTrue(position.runs[0].bold)

    def test_resume_matches_reference_project_hierarchy_and_pagination(self):
        content = """NAME: Alex Example
ROLE: Software Developer
CONTACT: alex@example.com

PROJECTS
PROJECT: FlyDocs Contract Management App – Example Client
PROJECT_META: Capstone for Example Digital Services | 2025 - 2026
● Designed a modular backend architecture.
● Applied product design and delivery practices.
PROJECT: React Native Social Site | 2025 - Present
● Developed an Android-first social platform.
● Continues development for iOS compatibility.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(content, path)
            document = Document(path)
            paragraph_text = [paragraph.text for paragraph in document.paragraphs]

            self.assertIn(
                "FlyDocs Contract Management App – Example Client",
                paragraph_text,
            )
            self.assertIn(
                "Capstone for Example Digital Services | 2025 – 2026",
                paragraph_text,
            )
            self.assertIn(
                "React Native Social Site | 2025 – Present",
                paragraph_text,
            )

            flydocs = paragraph_starting_with(
                document,
                "FlyDocs Contract Management App",
            )
            context = paragraph_starting_with(
                document,
                "Capstone for Example Digital Services",
            )
            first_bullet = paragraph_starting_with(
                document,
                "Designed a modular backend architecture.",
            )
            second_bullet = paragraph_starting_with(
                document,
                "Applied product design and delivery practices.",
            )

            self.assertTrue(flydocs.runs[0].bold)
            self.assertFalse(context.runs[0].bold)
            self.assertTrue(flydocs.paragraph_format.keep_with_next)
            self.assertTrue(context.paragraph_format.keep_with_next)
            self.assertTrue(first_bullet.paragraph_format.keep_with_next)
            self.assertFalse(second_bullet.paragraph_format.keep_with_next)

    def test_resume_matches_reference_company_role_hierarchy_and_pagination(self):
        content = """NAME: Alex Example
ROLE: Software Developer
CONTACT: alex@example.com

RELATED WORK EXPERIENCES
COMPANY: Example Labs
SOFTWARE ENGINEER - Jan 2025 - Present
● Built reliable customer workflows.
● Improved operational productivity.

OTHER EXPERIENCES
COMPANY: Example Retail, Customer Service
SALESPERSON - Nov 2024 - Present, Part-time
● Supported customers.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(content, path)
            document = Document(path)
            paragraph_text = [paragraph.text for paragraph in document.paragraphs]

            self.assertIn("Example Labs", paragraph_text)
            self.assertNotIn("COMPANY: Example Labs", paragraph_text)

            company = paragraph_starting_with(document, "Example Labs")
            role = paragraph_starting_with(document, "SOFTWARE ENGINEER")
            first_bullet = paragraph_starting_with(
                document,
                "Built reliable customer workflows.",
            )
            second_bullet = paragraph_starting_with(
                document,
                "Improved operational productivity.",
            )

            self.assertTrue(company.runs[0].bold)
            self.assertTrue(company.paragraph_format.keep_with_next)
            self.assertTrue(role.paragraph_format.keep_with_next)
            self.assertEqual(
                role.text,
                "SOFTWARE ENGINEER – Jan 2025 – Present",
            )
            self.assertTrue(first_bullet.paragraph_format.keep_with_next)
            self.assertFalse(second_bullet.paragraph_format.keep_with_next)

    def test_resume_does_not_make_optional_section_bullets_one_unbreakable_block(self):
        content = """NAME: Alex Example
ROLE: Software Developer
CONTACT: alex@example.com

ACHIEVEMENTS
● First supported achievement.
● Second supported achievement.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(content, path)
            document = Document(path)

            first_bullet = paragraph_starting_with(
                document,
                "First supported achievement.",
            )
            second_bullet = paragraph_starting_with(
                document,
                "Second supported achievement.",
            )

            self.assertFalse(first_bullet.paragraph_format.keep_with_next)
            self.assertFalse(second_bullet.paragraph_format.keep_with_next)
            self.assertTrue(first_bullet.paragraph_format.keep_together)

    def test_resume_hyperlinks_bare_website_without_linking_email_domain(self):
        content = """NAME: Alex Example
ROLE: Product Designer
CONTACT: alex@example.com
LINKS: alex.example
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            _build_resume_docx(content, path)
            document = Document(path)
            hyperlink_targets = {
                relationship.target_ref
                for relationship in document.part.rels.values()
                if relationship.reltype == RT.HYPERLINK
            }

            self.assertIn("https://alex.example/", hyperlink_targets)
            self.assertNotIn("https://example.com", hyperlink_targets)


if __name__ == "__main__":
    unittest.main()
