import unittest
from pathlib import Path

from backend.services.work_sample_links import (
    CASE_STUDIES_LABEL,
    DESIGN_PORTFOLIO_LABEL,
    RequiredWorkSampleLinkError,
    format_work_samples_line,
    required_work_sample_links,
)


PORTFOLIO_URL = "https://drive.example/design-portfolio?usp=sharing&source=resume"
CASE_STUDIES_URL = "https://figma.example/case-studies?node-id=1-2"
DEVELOPMENT_CASE_STUDIES_URL = (
    "https://figma.example/development-case-studies?node-id=3-4"
)
INSTRUCTIONS = f"""DESIGN RESUME HEADER - REQUIRED EXACT VALUES:
WORK_SAMPLES: [{DESIGN_PORTFOLIO_LABEL}]({PORTFOLIO_URL}) | [{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})
END DESIGN RESUME HEADER

DEVELOPMENT RESUME HEADER - REQUIRED EXACT VALUES:
WORK_SAMPLES: [{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})
END DEVELOPMENT RESUME HEADER"""


class WorkSampleLinkTests(unittest.TestCase):
    def test_design_requires_both_exact_source_links_in_display_order(self):
        self.assertEqual(
            required_work_sample_links(INSTRUCTIONS, "design"),
            {
                DESIGN_PORTFOLIO_LABEL: PORTFOLIO_URL,
                CASE_STUDIES_LABEL: CASE_STUDIES_URL,
            },
        )

    def test_development_requires_case_studies_only(self):
        self.assertEqual(
            required_work_sample_links(INSTRUCTIONS, "development"),
            {CASE_STUDIES_LABEL: CASE_STUDIES_URL},
        )

    def test_each_track_selects_its_own_case_studies_link(self):
        track_specific = INSTRUCTIONS.replace(
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})\n"
            "END DEVELOPMENT RESUME HEADER",
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL}]"
            f"({DEVELOPMENT_CASE_STUDIES_URL})\n"
            "END DEVELOPMENT RESUME HEADER",
        )

        self.assertEqual(
            required_work_sample_links(track_specific, "design"),
            {
                DESIGN_PORTFOLIO_LABEL: PORTFOLIO_URL,
                CASE_STUDIES_LABEL: CASE_STUDIES_URL,
            },
        )
        self.assertEqual(
            required_work_sample_links(track_specific, "development"),
            {CASE_STUDIES_LABEL: DEVELOPMENT_CASE_STUDIES_URL},
        )

    def test_repeated_identical_case_study_link_is_unambiguous(self):
        repeated = INSTRUCTIONS + (
            f"\n[{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})"
        )
        self.assertEqual(
            required_work_sample_links(repeated, "development"),
            {CASE_STUDIES_LABEL: CASE_STUDIES_URL},
        )

    def test_conflicting_urls_for_one_label_fail_closed(self):
        conflicting = INSTRUCTIONS + (
            f"\n[{CASE_STUDIES_LABEL}](https://other.example/case-studies)"
        )
        with self.assertRaises(RequiredWorkSampleLinkError) as raised:
            required_work_sample_links(conflicting, "development")
        self.assertEqual(raised.exception.labels, (CASE_STUDIES_LABEL,))
        self.assertNotIn(CASE_STUDIES_URL, str(raised.exception))

    def test_plain_text_label_does_not_count_as_a_link(self):
        plain_text = f"WORK_SAMPLES: {CASE_STUDIES_LABEL} | {CASE_STUDIES_URL}"
        with self.assertRaises(RequiredWorkSampleLinkError) as raised:
            required_work_sample_links(plain_text, "development")
        self.assertEqual(raised.exception.labels, (CASE_STUDIES_LABEL,))

    def test_case_mutated_required_label_does_not_count_as_exact_source_link(self):
        mutated = (
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL.lower()}]"
            f"({CASE_STUDIES_URL})"
        )

        with self.assertRaises(RequiredWorkSampleLinkError) as raised:
            required_work_sample_links(mutated, "development")

        self.assertEqual(raised.exception.labels, (CASE_STUDIES_LABEL,))

    def test_balanced_parentheses_in_source_url_are_preserved_exactly(self):
        balanced_url = (
            "https://figma.example/files/a_(b)?node=(c)&mode=dev#section"
        )
        instructions = (
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL}]({balanced_url})"
        )

        self.assertEqual(
            required_work_sample_links(instructions, "development"),
            {CASE_STUDIES_LABEL: balanced_url},
        )

    def test_unbalanced_parenthesis_source_destination_fails_closed(self):
        malformed = (
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL}]"
            "(https://figma.example/files/a_(b)"
        )

        with self.assertRaises(RequiredWorkSampleLinkError) as raised:
            required_work_sample_links(malformed, "development")

        self.assertEqual(raised.exception.labels, (CASE_STUDIES_LABEL,))

    def test_formatter_preserves_exact_labels_and_urls(self):
        self.assertEqual(
            format_work_samples_line(
                {
                    DESIGN_PORTFOLIO_LABEL: PORTFOLIO_URL,
                    CASE_STUDIES_LABEL: CASE_STUDIES_URL,
                }
            ),
            f"WORK_SAMPLES: [{DESIGN_PORTFOLIO_LABEL}]({PORTFOLIO_URL}) | "
            f"[{CASE_STUDIES_LABEL}]({CASE_STUDIES_URL})",
        )

    def test_example_instructions_preserve_current_track_rules(self):
        example = Path("models_personal_example/instructions_prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            tuple(required_work_sample_links(example, "design")),
            (DESIGN_PORTFOLIO_LABEL, CASE_STUDIES_LABEL),
        )
        self.assertEqual(
            tuple(required_work_sample_links(example, "development")),
            (CASE_STUDIES_LABEL,),
        )


if __name__ == "__main__":
    unittest.main()
