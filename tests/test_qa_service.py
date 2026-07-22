import unittest

from backend.qa_models import DocumentDraft, QASeverity
from backend.services.qa_service import (
    apply_safe_deterministic_fixes,
    draft_to_ai_response,
    parse_document_draft,
    validate_draft,
)


SOURCE_RESUME = """Alex Example
alex@example.com
https://github.com/alex
Designer at Example Studio, 2020 - Present
"""


def valid_draft() -> DocumentDraft:
    return DocumentDraft(
        resume="""NAME: Alex Example
ROLE: Product Designer
CONTACT: alex@example.com
LINKS: https://github.com/alex

PROFESSIONAL SUMMARY
Product designer focused on accessible digital experiences.

---

EXPERIENCE
Example Studio | Calgary
PRODUCT DESIGNER - 2020 - Present
● Built **accessible interfaces** for customer workflows.
""",
        cover_letter="""Cover Letter

To the Hiring Team,

I design accessible digital products and would bring that focus to this role.

Sincerely,
Alex Example
alex@example.com
""",
        analysis="""ATS_SCORE: 80

SCORE_RATIONALE: Supported design experience aligns with the role.
""",
    )


class QAServiceTests(unittest.TestCase):
    def test_parse_and_serialize_round_trip(self):
        original = valid_draft()
        parsed = parse_document_draft(draft_to_ai_response(original))
        self.assertEqual(parsed.resume, original.resume.strip())
        self.assertEqual(parsed.cover_letter, original.cover_letter.strip())
        self.assertEqual(parsed.analysis, original.analysis.strip())

    def test_parse_rejects_missing_required_section(self):
        with self.assertRaisesRegex(ValueError, "COVER_LETTER"):
            parse_document_draft("<RESUME>NAME: Alex Example</RESUME>")

    def test_valid_draft_has_no_blocking_findings(self):
        issues = validate_draft(
            valid_draft(),
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_RESUME,
        )
        blocking = [issue for issue in issues if issue.severity == QASeverity.ERROR]
        self.assertEqual(blocking, [])

    def test_validator_finds_truthfulness_grammar_and_format_errors(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "Product designer focused",
            "I am a product designer — focused",
        ).replace("2020", "2024")
        draft.cover_letter += "\n[Insert portfolio]\nmade-up@example.net"

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_RESUME,
        )
        codes = {issue.code for issue in issues}
        self.assertIn("RESUME_FIRST_PERSON", codes)
        self.assertIn("RESUME_EM_DASH", codes)
        self.assertIn("UNSUPPORTED_RESUME_YEAR", codes)
        self.assertIn("COVER_LETTER_PLACEHOLDER", codes)
        self.assertIn("UNSUPPORTED_EMAIL", codes)

    def test_validator_rejects_bulleted_section_and_missing_category_markers(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "EXPERIENCE\n",
            "● CORE SKILLS\nDesign Systems\n",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_RESUME,
        )
        codes = {issue.code for issue in issues}
        self.assertIn("RESUME_SECTION_AS_BULLET", codes)

    def test_validator_rejects_semicolon_category_values(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "CORE SKILLS\nCATEGORY: Design Skills | Branding; typography\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_RESUME,
        )

        self.assertIn(
            "RESUME_CATEGORY_DELIMITER_INVALID",
            {issue.code for issue in issues},
        )

    def test_validator_requires_personal_header_and_closing_blocks(self):
        instructions = """RESUME HEADER - REQUIRED EXACT VALUES:
CONTACT: alex@example.com
LINKS: https://github.com/alex
END REQUIRED RESUME HEADER

COVER LETTER CLOSING BLOCK - REQUIRED EXACT LINES:
Cheers and all the best!
Sincerely,
Alex Example
alex@example.com
END REQUIRED COVER LETTER CLOSING BLOCK"""
        issues = validate_draft(
            valid_draft(),
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=f"{SOURCE_RESUME}\n\n{instructions}",
        )
        codes = {issue.code for issue in issues}
        self.assertNotIn("RESUME_REQUIRED_HEADER_MISMATCH", codes)
        self.assertIn("COVER_LETTER_REQUIRED_CLOSING_MISMATCH", codes)

    def test_validator_restores_source_completeness_contract(self):
        source_resume = """# Alex Example

## Work Experience

### Product Designer
**Example Studio**
2020 - Present

### Salesperson
**Club Monaco**
2021 - 2022

## Educational Attainment

### Example University
2018 - 2020

## Achievements

- **Award One:** Recognized for accessible design.
"""
        issues = validate_draft(
            valid_draft(),
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )
        codes = {issue.code for issue in issues}
        self.assertIn("RESUME_SOURCE_ROLES_MISSING", codes)
        self.assertIn("RESUME_SOURCE_EMPLOYERS_MISSING", codes)
        self.assertIn("RESUME_SOURCE_DATES_MISSING", codes)
        self.assertIn("RESUME_SOURCE_ACHIEVEMENTS_MISSING", codes)

    def test_safe_fixes_restore_exact_cover_letter_signoff_name(self):
        draft = valid_draft()
        draft.cover_letter = draft.cover_letter.replace("Alex Example", "Alex")

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
        )

        self.assertIn("Sincerely,\nAlex Example", fixed.cover_letter)
        self.assertNotIn("Sincerely,\nAlex\n", fixed.cover_letter)
        self.assertIn("cover-letter sign-off", " ".join(changes))

    def test_safe_fixes_add_missing_signoff_name_before_contact(self):
        draft = valid_draft()
        draft.cover_letter = draft.cover_letter.replace("Alex Example\n", "")

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
        )

        self.assertIn("Sincerely,\nAlex Example\nalex@example.com", fixed.cover_letter)

    def test_safe_fixes_normalize_ats_score_and_are_idempotent(self):
        draft = valid_draft()
        draft.analysis = draft.analysis.replace("ATS_SCORE: 80", "**ATS_SCORE:** 80/100")

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
        )

        self.assertIn("ATS_SCORE: 80", fixed.analysis)
        self.assertNotIn("80/100", fixed.analysis)
        self.assertIn("Normalized ATS_SCORE", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_normalize_resume_bullets_and_preserve_markdown(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "● Built **accessible interfaces** for customer workflows.",
            """* Built **accessible interfaces** for customer workflows.
- Added another supported achievement.
+ Improved another supported workflow.
1. Documented another supported result.
• Preserved another supported detail.

---

**Bold body text is not a bullet.**""",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
        )

        self.assertEqual(fixed.resume.count("● "), 5)
        self.assertIn("\n---\n", fixed.resume)
        self.assertIn("**Bold body text is not a bullet.**", fixed.resume)
        self.assertIn("Normalized 5 resume bullet marker(s)", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_remove_duplicate_cover_letter_signoffs(self):
        draft = valid_draft()
        draft.cover_letter = draft.cover_letter.replace(
            "Sincerely,\nAlex Example",
            """Sincerely and thankfully,
Alex Example

Sincerely,
Alex Example""",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
        )

        self.assertIn("Sincerely and thankfully,\nAlex Example", fixed.cover_letter)
        self.assertNotIn("\nSincerely,\nAlex Example", fixed.cover_letter)
        self.assertEqual(fixed.cover_letter.count("Alex Example"), 1)
        self.assertIn("cover-letter sign-off", " ".join(changes))

    def test_safe_fixes_restore_previous_valid_ats_score(self):
        draft = valid_draft()
        previous_analysis = draft.analysis
        draft.analysis = "## Keyword Alignment\n\nRelevant keywords remain supported."

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            previous_analysis=previous_analysis,
        )

        self.assertTrue(fixed.analysis.startswith("ATS_SCORE: 80\n"))
        self.assertIn("## Keyword Alignment", fixed.analysis)
        self.assertIn("Restored the prior validated ATS_SCORE", " ".join(changes))

    def test_safe_fixes_estimate_missing_ats_score_from_keyword_coverage(self):
        draft = valid_draft()
        draft.analysis = """KEYWORDS_APPLIED:
- accessibility - summary
- prototyping - skills
- design systems - experience

KEYWORDS_MISSING:
- enterprise SaaS - unsupported

KEY_DECISIONS:
- Prioritized supported design evidence.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
        )

        self.assertTrue(fixed.analysis.startswith("ATS_SCORE: 75\n"))
        self.assertIn("Calculated the missing ATS_SCORE", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_restore_target_role_after_reviewer_drops_it(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace("ROLE: Product Designer\n", "")

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Senior Product Designer",
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            target_role="Senior Product Designer",
        )

        self.assertIn(
            "NAME: Alex Example\nROLE: Senior Product Designer\nCONTACT:",
            fixed.resume,
        )
        self.assertIn("Restored the target ROLE line", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_normalize_split_freelance_role_entry(self):
        source_resume = """# Alex Example

## Work Experience

### Freelance Multimedia Designer & Creative Director
**Alex Example**
May 2012 - 2021 | Oct 2024 - 2026
"""
        draft = valid_draft()
        draft.resume += """

Alex Example | Freelance Multimedia Designer & Creative Director
alex.example.com | May 2012 - 2021; Oct 2024 - 2026 (Freelance)
â— Delivered verified creative work.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Multimedia Designer",
            source_resume=source_resume,
        )
        issues = validate_draft(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )

        self.assertIn("Alex Example | alex.example.com", fixed.resume)
        self.assertIn(
            "FREELANCE MULTIMEDIA DESIGNER & CREATIVE DIRECTOR - "
            "May 2012 - 2021; Oct 2024 - 2026",
            fixed.resume,
        )
        self.assertIn("Normalized verified role titles", " ".join(changes))
        self.assertNotIn(
            "RESUME_ROLE_FORMAT_INVALID",
            {issue.code for issue in issues},
        )

    def test_safe_fixes_repair_category_dates_and_cover_letter_dash(self):
        source_resume = """# Alex Example
alex@example.com
https://github.com/alex

## Work Experience

### Product Designer
**Example Studio**
**Product Designer:** 2021 - Present | 2019 - 2020, Freelance

## Educational Attainment

### Example University
**Design Diploma**
2009 - 2013
"""
        draft = valid_draft()
        draft.resume = """NAME: Alex Example
ROLE: Product Designer
CONTACT: alex@example.com
LINKS: https://github.com/alex

CORE SKILLS
Design Skills: Accessibility | prototyping; design systems

---

DESIGN SKILLS
\u25cf Designed accessible customer workflows.

---

TECHNICAL SKILLS
\u25cf Built production interfaces.

---

WORK EXPERIENCE
Example Studio | Calgary
PRODUCT DESIGNER - 2021 - Present
\u25cf Built accessible customer workflows.

---

EDUCATION
Example University | Design Diploma
Graduated with honors
"""
        draft.cover_letter = draft.cover_letter.replace(
            "digital products and would",
            "digital products\u2014and would",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Product Designer",
            source_resume=source_resume,
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            target_role="Product Designer",
            source_resume=source_resume,
        )
        issues = validate_draft(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )
        codes = {issue.code for issue in issues}

        self.assertIn(
            "CATEGORY: Design Skills | Accessibility, prototyping, design systems",
            fixed.resume,
        )
        self.assertIn(
            "CATEGORY: Design Skills | Accessibility, prototyping, design systems",
            fixed.resume,
        )
        self.assertIn(
            "CATEGORY: Design Delivery | Designed accessible customer workflows",
            fixed.resume,
        )
        self.assertEqual(fixed.resume.count("\nDESIGN SKILLS\n"), 0)
        self.assertEqual(fixed.resume.count("\nTECHNICAL SKILLS\n"), 0)
        self.assertIn(
            "PRODUCT DESIGNER - 2021 - Present; 2019 - 2020, Freelance",
            fixed.resume,
        )
        self.assertIn("Example University | 2009 - 2013", fixed.resume)
        self.assertIn("\nDesign Diploma\n", fixed.resume)
        self.assertNotIn("\u2014", fixed.cover_letter)
        self.assertNotIn("RESUME_CATEGORY_MARKERS_MISSING", codes)
        self.assertNotIn("RESUME_SOURCE_DATES_MISSING", codes)
        self.assertNotIn("COVER_LETTER_EM_DASH", codes)
        self.assertIn("CATEGORY builder markers", " ".join(changes))
        self.assertIn("Restored verified role titles", " ".join(changes))
        self.assertIn("prohibited em dash", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_repair_collapsed_roles_dates_and_colon_categories(self):
        source_resume = """# Alex Example

## Work Experience

### Creative Director / Senior Art Director
**Ant Savvy Creatives**
**Creative Director:** April 2021 - Oct 2024, Full-time | Oct 2024 - 2026, Present Freelance
**Senior Art Director:** April 2017 - April 2018, Full-time | 2019 - 2020, Freelance

### Freelance Multimedia Designer & Creative Director
**Alex Example**
May 2012 - 2021 | Oct 2024 - 2026
"""
        draft = valid_draft()
        draft.resume = """NAME: Alex Example
ROLE: Multimedia Designer
CONTACT: alex@example.com
LINKS: alex.example.com

PROFESSIONAL SUMMARY
Multimedia designer focused on accessible brand experiences.

---

CORE SKILLS
Design Skills: Branding; motion graphics; visual storytelling
Technical Tools: Photoshop; Illustrator; After Effects
Strategy & Leadership: Creative direction; stakeholder management

---

WORK EXPERIENCE
Ant Savvy Creatives | Advertising Agency
CREATIVE DIRECTOR / SENIOR ART DIRECTOR - April 2017 - Oct 2024, Full-time
● Led integrated campaigns.

Alex Example | alex.example.com
MULTIMEDIA DESIGNER & CREATIVE DIRECTOR - May 2012 - 2021; Oct 2024 - 2026
● Delivered multimedia work.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Multimedia Designer",
            source_resume=source_resume,
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            target_role="Multimedia Designer",
            source_resume=source_resume,
        )
        issues = validate_draft(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )
        codes = {issue.code for issue in issues}

        self.assertIn(
            "CATEGORY: Design Skills | Branding, motion graphics, visual storytelling",
            fixed.resume,
        )
        self.assertIn(
            "CREATIVE DIRECTOR - April 2021 - Oct 2024, Full-time; "
            "Oct 2024 - 2026, Present Freelance",
            fixed.resume,
        )
        self.assertIn(
            "SENIOR ART DIRECTOR - April 2017 - April 2018, Full-time; "
            "2019 - 2020, Freelance",
            fixed.resume,
        )
        self.assertIn(
            "FREELANCE MULTIMEDIA DESIGNER & CREATIVE DIRECTOR - "
            "May 2012 - 2021; Oct 2024 - 2026",
            fixed.resume,
        )
        self.assertNotIn("RESUME_CATEGORY_MARKERS_MISSING", codes)
        self.assertNotIn("RESUME_SOURCE_ROLES_MISSING", codes)
        self.assertNotIn("RESUME_SOURCE_DATES_MISSING", codes)
        self.assertIn("CATEGORY builder markers", " ".join(changes))
        self.assertIn("Restored verified role titles", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_repair_retained_qa_failure_cluster(self):
        source_resume = """# Alex Example

[alex.example](https://alex.example/)

## Work Experience

### Creative Lead & Multimedia Artist
**Example Network**
March – July 2015
"""
        draft = valid_draft()
        draft.resume = """NAME: Alex Example
ROLE: Multimedia Designer
CONTACT: alex@example.com
LINKS: www.alex.example

PROFESSIONAL SUMMARY
Multimedia designer focused on accessible digital experiences.

---

EXPERIENCE
Example Network
CREATIVE LEAD & MULTIMEDIA ARTIST - N/A
● Led a multidisciplinary creative team.
"""
        draft.cover_letter = draft.cover_letter.replace(
            "Cover Letter",
            "# Cover Letter",
            1,
        )

        before_codes = {
            issue.code
            for issue in validate_draft(
                draft,
                owner_name="Alex Example",
                source_resume=source_resume,
                source_materials=source_resume,
            )
        }
        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Multimedia Designer",
            source_resume=source_resume,
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            target_role="Multimedia Designer",
            source_resume=source_resume,
        )
        after_codes = {
            issue.code
            for issue in validate_draft(
                fixed,
                owner_name="Alex Example",
                source_resume=source_resume,
                source_materials=source_resume,
            )
        }

        self.assertTrue(
            {
                "COVER_LETTER_HEADING_MISSING",
                "RESUME_ROLE_FORMAT_INVALID",
                "UNSUPPORTED_URL",
            }.issubset(before_codes)
        )
        self.assertTrue(fixed.cover_letter.startswith("Cover Letter\n"))
        self.assertIn(
            "CREATIVE LEAD & MULTIMEDIA ARTIST - March - July 2015",
            fixed.resume,
        )
        self.assertIn("LINKS: alex.example", fixed.resume)
        self.assertFalse(
            {
                "COVER_LETTER_HEADING_MISSING",
                "RESUME_ROLE_FORMAT_INVALID",
                "UNSUPPORTED_URL",
            }
            & after_codes
        )
        self.assertIn("Cover Letter heading", " ".join(changes))
        self.assertIn("source-supported URL", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_do_not_replace_unrelated_unsupported_url(self):
        source_resume = """# Alex Example

[alex.example](https://alex.example/)
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "https://github.com/alex",
            "www.unrelated.example",
        )

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
        )
        codes = {
            issue.code
            for issue in validate_draft(
                fixed,
                owner_name="Alex Example",
                source_resume=source_resume,
                source_materials=source_resume,
            )
        }

        self.assertIn("www.unrelated.example", fixed.resume)
        self.assertIn("UNSUPPORTED_URL", codes)


if __name__ == "__main__":
    unittest.main()
