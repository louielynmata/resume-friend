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


if __name__ == "__main__":
    unittest.main()
