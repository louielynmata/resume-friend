import unittest

from backend.qa_models import DocumentDraft, QASeverity
from backend.services import document_service, qa_service
from backend.services.qa_service import (
    apply_safe_deterministic_fixes,
    draft_to_ai_response,
    parse_document_draft,
    validate_draft,
)
from backend.services.work_sample_links import (
    CASE_STUDIES_LABEL,
    DESIGN_PORTFOLIO_LABEL,
    format_work_samples_line,
)


SOURCE_RESUME = """Alex Example
alex@example.com
https://github.com/alex
Designer at Example Studio, 2020 - Present
"""

DESIGN_LINKS = {
    DESIGN_PORTFOLIO_LABEL: "https://drive.example/design-portfolio",
    CASE_STUDIES_LABEL: "https://figma.example/case-studies",
}
DEVELOPMENT_LINKS = {
    CASE_STUDIES_LABEL: "https://figma.example/case-studies",
}
SOURCE_WITH_DEVELOPMENT_LINKS = (
    SOURCE_RESUME + "\n" + format_work_samples_line(DEVELOPMENT_LINKS)
)

DEVELOPMENT_SOURCE_WITH_SKILLS = """# Alex Example

## Toolkit and Technical Skills

### Languages
- Python
- TypeScript

### Frameworks
- React
- React Native

### Testing
- unittest
- Playwright

### Delivery
- Docker
- CI/CD

### Architecture
- REST APIs
- Event-driven systems

### Currently Learning
- Rust

## Educational Attainment
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


class WorkSampleSemanticQATests(unittest.TestCase):
    def test_safe_fixes_restore_design_links_without_relying_on_model_output(self):
        draft = valid_draft()

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_materials=SOURCE_RESUME,
            job_type="design",
            required_work_sample_links=DESIGN_LINKS,
        )

        self.assertIn(format_work_samples_line(DESIGN_LINKS), fixed.resume)
        self.assertIn("work-sample links", " ".join(changes).lower())

    def test_safe_fixes_keep_development_track_case_studies_only(self):
        draft = valid_draft()

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_materials=SOURCE_RESUME,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )

        self.assertIn(format_work_samples_line(DEVELOPMENT_LINKS), fixed.resume)
        self.assertNotIn(DESIGN_PORTFOLIO_LABEL, fixed.resume)

    def test_safe_fixes_preserve_identity_when_only_work_samples_are_required(self):
        fixed, _ = apply_safe_deterministic_fixes(
            valid_draft(),
            owner_name="Alex Example",
            source_materials=SOURCE_RESUME,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )

        self.assertIn("NAME: Alex Example", fixed.resume)
        self.assertIn("ROLE: Product Designer", fixed.resume)
        self.assertIn("CONTACT: alex@example.com", fixed.resume)
        self.assertIn(format_work_samples_line(DEVELOPMENT_LINKS), fixed.resume)

    def test_validator_rejects_plain_text_required_label(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            f"WORK_SAMPLES: {CASE_STUDIES_LABEL}",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_WITH_DEVELOPMENT_LINKS,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )

        self.assertIn(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            {issue.code for issue in issues},
        )

    def test_validator_rejects_wrong_required_target(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL}]"
            "(https://wrong.example/case-studies)",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_WITH_DEVELOPMENT_LINKS,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )

        self.assertIn(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            {issue.code for issue in issues},
        )

    def test_validator_rejects_case_mutated_required_link_line(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            f"WORK_SAMPLES: [{CASE_STUDIES_LABEL.lower()}]"
            f"({DEVELOPMENT_LINKS[CASE_STUDIES_LABEL]})",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_WITH_DEVELOPMENT_LINKS,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )

        self.assertIn(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            {issue.code for issue in issues},
        )

    def test_source_url_candidates_preserve_balanced_parentheses_exactly(self):
        balanced_url = (
            "https://figma.example/files/a_(b)?node=(c)&mode=dev#section"
        )

        candidates = qa_service._source_url_candidates(
            f"[{CASE_STUDIES_LABEL}]({balanced_url})"
        )

        self.assertIn(balanced_url, candidates)

    def test_validator_accepts_exact_track_required_line(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "LINKS: https://github.com/alex",
            "LINKS: https://github.com/alex\n"
            + format_work_samples_line(DEVELOPMENT_LINKS),
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=SOURCE_RESUME,
            source_materials=SOURCE_WITH_DEVELOPMENT_LINKS,
            job_type="development",
            required_work_sample_links=DEVELOPMENT_LINKS,
        )

        self.assertNotIn(
            "RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH",
            {issue.code for issue in issues},
        )


class QAServiceTests(unittest.TestCase):
    def test_validator_and_docx_builder_share_resume_section_names(self):
        self.assertIs(
            qa_service._RESUME_SECTION_NAMES,
            document_service._KNOWN_SECTION_NAMES,
        )
        for section_name in qa_service._RESUME_SECTION_NAMES:
            self.assertEqual(
                qa_service._resume_section_name(section_name),
                section_name,
            )
            self.assertTrue(document_service._is_section_header(section_name))

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

    def test_validator_rejects_missing_source_backed_ai_tools(self):
        source_resume = """# Alex Example

## Toolkit and Technical Skills

### AI Tools
- Pair Pilot
- Local Assistant
"""

        issues = validate_draft(
            valid_draft(),
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )

        self.assertIn(
            "RESUME_SOURCE_AI_TOOLS_MISSING",
            {issue.code for issue in issues},
        )

    def test_validator_rejects_ai_tool_content_outside_ai_tools_category(self):
        source_resume = f"""{SOURCE_RESUME}

## Toolkit and Technical Skills

### AI Tools
- Pair Pilot
- Local Assistant
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "Product designer focused on accessible digital experiences.",
            "Product designer using Pair Pilot for accessible digital experiences.",
        ).replace(
            "PROFESSIONAL SUMMARY\n",
            "TECHNICAL SKILLS\n"
            "CATEGORY: AI Tools | Pair Pilot, Local Assistant\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )

        self.assertIn(
            "RESUME_AI_CONTENT_OUTSIDE_TOOLS_CATEGORY",
            {issue.code for issue in issues},
        )

    def test_validator_allows_source_backed_ai_product_project_description(self):
        source_resume = f"""{SOURCE_RESUME}

## Toolkit and Technical Skills

### AI Tools
- Pair Pilot
- Local Assistant

## Projects

### Resume Friend
- A local AI tool that generates tailored resumes and cover letters.
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TECHNICAL SKILLS\n"
            "CATEGORY: AI Tools | Pair Pilot, Local Assistant\n\n"
            "PROFESSIONAL SUMMARY\n",
        )
        draft.resume += (
            "\n\nPROJECTS\n"
            "RESUME FRIEND\n"
            "● Developed a local AI tool that generates tailored resumes "
            "and cover letters.\n"
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )

        self.assertNotIn(
            "RESUME_AI_CONTENT_OUTSIDE_TOOLS_CATEGORY",
            {issue.code for issue in issues},
        )

    def test_validator_requires_related_and_other_experience_sections(self):
        source_resume = """# Alex Example

## Related Work Experience

### Software Engineer
**Example Labs**
**Software Engineer:** 2025

## Other Experience

### Salesperson
**Example Retail**
**Salesperson:** 2024 - Present
"""
        draft = valid_draft()
        draft.resume += """

Example Labs
SOFTWARE ENGINEER - 2025

Example Retail
SALESPERSON - 2024 - Present
"""

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )

        self.assertIn(
            "RESUME_SOURCE_EXPERIENCE_SECTIONS_MISSING",
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

    def test_validator_accepts_employer_without_descriptive_source_suffix(self):
        source_resume = """# Alex Example
alex@example.com
https://github.com/alex

## Work Experience

### Product Designer
**Club Monaco — Upscale Retail in Canada**
2020 - Present
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace("Example Studio", "Club Monaco")

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )
        codes = {issue.code for issue in issues}

        self.assertNotIn("RESUME_SOURCE_EMPLOYERS_MISSING", codes)

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

    def test_safe_fixes_apply_design_header_and_section_contract(self):
        instructions = """RESUME HEADER - REQUIRED EXACT VALUES:
CONTACT: alex@example.com | +1 555 010 0000 | Calgary, AB
LINKS: alex.example | linkedin.com/in/alex | github.com/alex
END REQUIRED RESUME HEADER

DESIGN RESUME HEADER - REQUIRED EXACT VALUES:
WORK_SAMPLES: [Design Portfolio (Reel and PDF)](https://drive.example/portfolio) | [Case Studies and Product Work](https://figma.example/case-studies)
END DESIGN RESUME HEADER"""
        draft = valid_draft()
        draft.resume += """

EDUCATIONAL ATTAINMENT
Example University | 2020
Design Diploma

CERTIFICATIONS
● Example Certificate

ACHIEVEMENTS
● Example Award

WORK EXPERIENCE
PRODUCT DESIGNER - 2020 - Present
Example Studio
● Built accessible interfaces.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_materials=instructions,
            job_type="design",
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            source_materials=instructions,
            job_type="design",
        )

        self.assertIn(
            "WORK_SAMPLES: [Design Portfolio (Reel and PDF)](https://drive.example/portfolio) "
            "| [Case Studies and Product Work](https://figma.example/case-studies)",
            fixed.resume,
        )
        self.assertNotIn("CERTIFICATIONS", fixed.resume)
        self.assertLess(fixed.resume.index("WORK EXPERIENCE"), fixed.resume.index("EDUCATION"))
        self.assertLess(
            fixed.resume.index("EDUCATION"),
            fixed.resume.index("AWARDS AND ACHIEVEMENTS"),
        )
        self.assertIn("Applied the design resume section order", " ".join(changes))
        self.assertEqual(fixed_again.model_dump(), fixed.model_dump())
        self.assertEqual(second_changes, [])

    def test_validator_rejects_modified_design_reference_entry_structure(self):
        source_resume = """# Alex Example

## Work Experience

### Creative Director / Senior Art Director
**Example Creative Agency**
360 Entertainment & Advertising Agency
**Creative Director:** April 2021 - Oct 2024, Full-time | Oct 2024 - 2026, Present Freelance
**Senior Art Director:** April 2017 - April 2018, Full-time | 2019 - 2020, Freelance

- Directed integrated campaigns.

#### Notable Clients

- Example Beverage Group - regional portfolio
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "Example Studio | Calgary\n"
            "PRODUCT DESIGNER - 2020 - Present\n"
            "● Built **accessible interfaces** for customer workflows.",
            "Example Creative Agency | Rewritten descriptor\n"
            "CREATIVE DIRECTOR / SENIOR ART DIRECTOR - 2017 - 2026\n"
            "Unapproved structural subtitle\n"
            "● Added a source-supported campaign bullet.",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="design",
        )

        self.assertIn(
            "RESUME_DESIGN_REFERENCE_ENTRY_MISMATCH",
            {issue.code for issue in issues},
        )

    def test_safe_fixes_lock_design_reference_entry_and_notable_clients(self):
        source_resume = """# Alex Example

## Work Experience

### Creative Director / Senior Art Director
**Example Creative Agency**
360 Entertainment & Advertising Agency
**Creative Director:** April 2021 - Oct 2024, Full-time | Oct 2024 - 2026, Present Freelance
**Senior Art Director:** April 2017 - April 2018, Full-time | 2019 - 2020, Freelance

- Directed integrated campaigns.
- Mentored multidisciplinary design teams.

#### Notable Clients

- Example Beverage Group - regional portfolio
- Example Retail Group - seasonal campaigns

### Multimedia Designer
**Example Production Studio**
2020 - Present

- Produced digital campaign assets.
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "Example Studio | Calgary\n"
            "PRODUCT DESIGNER - 2020 - Present\n"
            "● Built **accessible interfaces** for customer workflows.",
            "Example Creative Agency | Rewritten descriptor\n"
            "CREATIVE DIRECTOR / SENIOR ART DIRECTOR - 2017 - 2026\n"
            "Unapproved structural subtitle\n"
            "● Added a source-supported campaign bullet.\n\n"
            "NOTABLE CLIENTS\n"
            "● Example Beverage Group only\n\n"
            "Example Production Studio\n"
            "MULTIMEDIA DESIGNER - 2020 - Present\n"
            "● Produced digital campaign assets.",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Product Designer",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="design",
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            target_role="Product Designer",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="design",
        )
        issue_codes = {
            issue.code
            for issue in validate_draft(
                fixed,
                owner_name="Alex Example",
                source_resume=source_resume,
                source_materials=source_resume,
                job_type="design",
            )
        }

        expected_block = """COMPANY: Example Creative Agency | 360 Entertainment & Advertising Agency
CREATIVE DIRECTOR - April 2021 - Oct 2024, Full-time; Oct 2024 - 2026, Present Freelance
SENIOR ART DIRECTOR - April 2017 - April 2018, Full-time; 2019 - 2020, Freelance
● Directed integrated campaigns.
● Mentored multidisciplinary design teams.
● Added a source-supported campaign bullet.

SUBHEADING: Notable Clients
● Example Beverage Group - regional portfolio
● Example Retail Group - seasonal campaigns"""
        self.assertIn(expected_block, fixed.resume)
        self.assertNotIn("Rewritten descriptor", fixed.resume)
        self.assertNotIn("CREATIVE DIRECTOR / SENIOR ART DIRECTOR", fixed.resume)
        self.assertNotIn("Unapproved structural subtitle", fixed.resume)
        self.assertNotIn("Example Beverage Group only", fixed.resume)
        self.assertIn("Example Production Studio", fixed.resume)
        self.assertIn(
            "Restored fixed design entry structure and Notable Clients",
            " ".join(changes),
        )
        self.assertNotIn("RESUME_DESIGN_REFERENCE_ENTRY_MISMATCH", issue_codes)
        self.assertEqual(fixed_again.model_dump(), fixed.model_dump())
        self.assertEqual(second_changes, [])

    def test_safe_fixes_normalize_first_person_in_locked_design_source_bullets(self):
        source_resume = """# Alex Example

## Work Experience

### Creative Director
**Example Creative Agency**
360 Entertainment & Advertising Agency
**Creative Director:** April 2021 - Oct 2024, Full-time

- I led my team through integrated campaigns.
- Mentored and improved motivation for designers under my team, resulting in a regional award.

#### Notable Clients

- Example Beverage Group - regional portfolio
"""
        draft = valid_draft()
        draft.resume += """

COMPANY: Example Creative Agency | 360 Entertainment & Advertising Agency
CREATIVE DIRECTOR - April 2021 - Oct 2024, Full-time
- I led my team through integrated campaigns.
- Mentored and improved motivation for designers under my team, resulting in a regional award.

SUBHEADING: Notable Clients
- Example Beverage Group - regional portfolio
"""

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Product Designer",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="design",
        )
        issue_codes = {
            issue.code
            for issue in validate_draft(
                fixed,
                owner_name="Alex Example",
                source_resume=source_resume,
                source_materials=source_resume,
                job_type="design",
            )
        }

        self.assertIn("Led the team through integrated campaigns.", fixed.resume)
        self.assertIn(
            "Mentored and improved motivation for designers on the team, "
            "resulting in a regional award.",
            fixed.resume,
        )
        self.assertEqual(
            fixed.resume.count("Led the team through integrated campaigns."),
            1,
        )
        self.assertEqual(
            fixed.resume.count(
                "Mentored and improved motivation for designers on the team, "
                "resulting in a regional award."
            ),
            1,
        )
        self.assertNotIn("RESUME_FIRST_PERSON", issue_codes)

    def test_safe_fixes_filter_only_rewritten_design_source_bullets(self):
        source_resume = """# Alex Example

## Work Experience

### Creative Director
**Example Creative Agency**
360 Entertainment & Advertising Agency
**Creative Director:** April 2021 - Oct 2024, Full-time

- Spearheaded numerous 360-degree marketing campaigns and stakeholder communication from ideation to execution that led to 90M+ impressions across APAC, increased revenue, and elevated brand positioning.
- Provided creative leadership and contributed to key board-level decision-making, resulting in 300% company growth and CAD 1.5M-2M in gross profits yearly.
- Mentored and improved motivation for designers on the team, resulting in a regional award, millions of impressions, and millions in positive brand value.
- Handled 10+ active clients across Southeast Asia, ensuring a 90%+ repeat business rate and showing commitment to customer loyalty and service excellence.

#### Notable Clients

- Example Beverage Group - regional portfolio
"""
        source_materials = source_resume + """

## Interview Transcript

Developed a production intake system that cut approval cycles by 35%.
"""
        rewritten_campaign = (
            "Spearheaded numerous 360-degree marketing campaigns and stakeholder "
            "communications from ideation to execution. These initiatives generated "
            "over 90M+ impressions across the APAC region, significantly increasing "
            "revenue and elevating brand positioning."
        )
        rewritten_growth = (
            "Provided creative leadership and directly contributed to key board-level "
            "decision making, resulting in a recorded 300% company growth and "
            "generating an annual gross profit between CAD 1.5M-2M."
        )
        rewritten_mentorship = (
            "Mentored team designers, leading improvements that resulted in regional "
            "awards, millions of impressions, and increased positive brand value."
        )
        rewritten_client_work = (
            "Managed over 10 active client accounts across Southeast Asia, maintaining "
            "a 90%+ repeat business rate and establishing deep customer loyalty through "
            "service excellence."
        )
        distinct_addition = (
            "Developed a production intake system that cut approval cycles by 35%."
        )
        draft = valid_draft()
        draft.resume += f"""

COMPANY: Example Creative Agency | 360 Entertainment & Advertising Agency
CREATIVE DIRECTOR - April 2021 - Oct 2024, Full-time
● {rewritten_campaign}
● {rewritten_growth}
● {rewritten_mentorship}
● {rewritten_client_work}
● {distinct_addition}

SUBHEADING: Notable Clients
● Example Beverage Group - regional portfolio
"""

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Product Designer",
            source_resume=source_resume,
            source_materials=source_materials,
            job_type="design",
        )

        self.assertNotIn(rewritten_campaign, fixed.resume)
        self.assertNotIn(rewritten_growth, fixed.resume)
        self.assertNotIn(rewritten_mentorship, fixed.resume)
        self.assertNotIn(rewritten_client_work, fixed.resume)
        self.assertIn(distinct_addition, fixed.resume)
        self.assertEqual(fixed.resume.count("90M+ impressions across APAC"), 1)
        self.assertEqual(fixed.resume.count("300% company growth"), 1)
        self.assertEqual(fixed.resume.count("millions of impressions"), 1)
        self.assertEqual(fixed.resume.count("10+ active clients"), 1)

    def test_safe_fixes_apply_development_header_and_section_contract(self):
        instructions = """RESUME HEADER - REQUIRED EXACT VALUES:
CONTACT: alex@example.com | +1 555 010 0000 | Calgary, AB
LINKS: alex.example | linkedin.com/in/alex | github.com/alex
END REQUIRED RESUME HEADER

DEVELOPMENT RESUME HEADER - REQUIRED EXACT VALUES:
WORK_SAMPLES: [Case Studies and Product Work](https://figma.example/case-studies)
END DEVELOPMENT RESUME HEADER"""
        draft = valid_draft()
        draft.resume += """

ACHIEVEMENTS
● Example Award

CERTIFICATIONS
● Example Certificate

OTHER EXPERIENCES
SALESPERSON - 2021 - 2022
Example Retail
● Supported customers.

RELATED WORK EXPERIENCES
SOFTWARE ENGINEER - 2023 - Present
Example Labs
● Built reliable systems.

PROJECTS
PROJECT: Example App | 2023
● Built an application.

EDUCATIONAL ATTAINMENT
Example University | 2020
Software Development Diploma
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_materials=instructions,
            job_type="development",
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            source_materials=instructions,
            job_type="development",
        )

        self.assertIn(
            "WORK_SAMPLES: [Case Studies and Product Work](https://figma.example/case-studies)",
            fixed.resume,
        )
        ordered_sections = [
            "EDUCATION",
            "PROJECTS",
            "RELATED WORK EXPERIENCES",
            "OTHER WORK EXPERIENCES",
            "CERTIFICATES",
            "AWARDS AND ACHIEVEMENTS",
        ]
        positions = [fixed.resume.index(section) for section in ordered_sections]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Applied the development resume section order", " ".join(changes))
        self.assertEqual(fixed_again.model_dump(), fixed.model_dump())
        self.assertEqual(second_changes, [])

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

    def test_safe_fixes_split_company_from_inline_role_and_dates(self):
        source_resume = """# Alex Example

## Work Experience

### Senior Art Director
**Ant Savvy Creatives**
**Senior Art Director:** April 2017 - April 2018, Full-time | 2019 - 2020, Freelance
"""
        draft = valid_draft()
        draft.resume += """

Ant Savvy Creatives | SENIOR ART DIRECTOR - April 2017 - April 2018, Full-time; 2019 - 2020, Freelance
● Led verified creative work.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
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

        self.assertIn(
            "\nAnt Savvy Creatives\n"
            "SENIOR ART DIRECTOR - April 2017 - April 2018, Full-time; "
            "2019 - 2020, Freelance\n",
            fixed.resume,
        )
        self.assertNotIn(
            "Ant Savvy Creatives | SENIOR ART DIRECTOR",
            fixed.resume,
        )
        self.assertNotIn(
            "RESUME_ROLE_FORMAT_INVALID",
            {issue.code for issue in issues},
        )
        self.assertIn("Normalized verified role titles", " ".join(changes))

    def test_safe_fixes_split_inline_role_when_longer_role_also_matches(self):
        source_resume = """# Alex Example

## Work Experience

### Creative Director
**Ant Savvy Creatives**
**Creative Director:** April 2021 - October 2024

### Freelance Multimedia Designer & Creative Director
**Alex Example**
May 2012 - 2021
"""
        draft = valid_draft()
        draft.resume += """

Ant Savvy Creatives | CREATIVE DIRECTOR - April 2021 - October 2024
● Led verified campaign work.

Alex Example
FREELANCE MULTIMEDIA DESIGNER & CREATIVE DIRECTOR - May 2012 - 2021
● Delivered verified multimedia work.
"""

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Product Designer",
            source_resume=source_resume,
        )

        self.assertIn(
            "\nAnt Savvy Creatives\n"
            "CREATIVE DIRECTOR - April 2021 - October 2024\n",
            fixed.resume,
        )
        self.assertNotIn(
            "Ant Savvy Creatives | CREATIVE DIRECTOR",
            fixed.resume,
        )

    def test_safe_fixes_repair_role_company_line_with_dates_below(self):
        source_resume = """# Alex Example

## Other Experiences

### Salesperson
**Club Monaco - Upscale Retail in Canada**
Nov 2024 - Present, Part-time
"""
        draft = valid_draft()
        draft.resume += """

OTHER EXPERIENCES
SALESPERSON - Club Monaco | Upscale Retail in Canada
Dec 2024 - Present, Part-time
● Delivered personalized customer recommendations.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
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

        self.assertIn(
            "\nClub Monaco | Upscale Retail in Canada\n"
            "SALESPERSON - Nov 2024 - Present, Part-time\n"
            "● Delivered personalized customer recommendations.",
            fixed.resume,
        )
        self.assertNotIn(
            "SALESPERSON - Club Monaco",
            fixed.resume,
        )
        self.assertNotIn(
            "RESUME_ROLE_FORMAT_INVALID",
            {issue.code for issue in issues},
        )
        self.assertIn("Normalized verified role titles", " ".join(changes))

    def test_safe_fixes_repair_retained_standalone_role_layouts(self):
        source_resume = """# Alex Example

## Related Work Experiences

### Software Engineering Intern
**Newton Crypto Canada**
Summer 2025 Co-op / May 2025 – Aug 2025

## Other Experiences

### Salesperson
**Club Monaco — Upscale Retail in Canada**
Nov 2024 – Present, Part-time
"""
        draft = valid_draft()
        draft.resume += """

RELATED WORK EXPERIENCES
SOFTWARE ENGINEERING INTERN
Newton Crypto Canada | May 2025 – Aug 2025
● Built production-grade Python and Django modules.

OTHER EXPERIENCES
SALESPERSON
Club Monaco | Upscale Retail in Canada
Nov 2024 – Present, Part-time
● Delivered personalized customer recommendations.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Software Engineer",
            source_resume=source_resume,
        )
        issues = validate_draft(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
        )

        self.assertIn(
            "\nNewton Crypto Canada\n"
            "SOFTWARE ENGINEERING INTERN - "
            "Summer 2025 Co-op / May 2025 - Aug 2025\n"
            "● Built production-grade Python and Django modules.",
            fixed.resume,
        )
        self.assertIn(
            "\nClub Monaco | Upscale Retail in Canada\n"
            "SALESPERSON - Nov 2024 - Present, Part-time\n"
            "● Delivered personalized customer recommendations.",
            fixed.resume,
        )
        self.assertNotIn(
            "RESUME_ROLE_FORMAT_INVALID",
            {issue.code for issue in issues},
        )
        self.assertIn("Normalized verified role titles", " ".join(changes))

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

    def test_safe_fixes_remove_repeated_skill_prefixes_and_toolkit_duplicates(self):
        draft = valid_draft()
        draft.resume = """NAME: Alex Example
ROLE: Graphic Designer
CONTACT: alex@example.com
LINKS: https://example.com

DESIGN SKILLS
CATEGORY: DESIGN SKILLS: Visual Identity | branding, graphic design
CATEGORY: TECHNICAL SKILLS: Graphic & Multimedia Tools | Adobe Creative Suite, Figma
CATEGORY: CORE SKILLS: Production | print production, Adobe Creative Suite

---

TOOLKIT
CATEGORY: Design & Multimedia Tools | Adobe Creative Suite, Figma, Blender

---

WORK EXPERIENCE
Example Studio | Calgary
PRODUCT DESIGNER - 2020 - Present
● Built accessible interfaces.

---

EDUCATION
Example University | 2020
Design Diploma

---

AWARDS AND ACHIEVEMENTS
● Example Award
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            job_type="design",
        )

        self.assertIn(
            "CATEGORY: Visual Identity | branding, graphic design",
            fixed.resume,
        )
        self.assertIn(
            "CATEGORY: Production | print production",
            fixed.resume,
        )
        self.assertNotIn("DESIGN SKILLS: Visual Identity", fixed.resume)
        self.assertNotIn("TECHNICAL SKILLS: Graphic & Multimedia Tools", fixed.resume)
        self.assertNotIn("CORE SKILLS: Production", fixed.resume)
        self.assertNotIn("Graphic & Multimedia Tools", fixed.resume)
        self.assertEqual(fixed.resume.count("Adobe Creative Suite"), 1)
        self.assertEqual(fixed.resume.count("Figma"), 1)
        self.assertIn("CATEGORY builder markers", " ".join(changes))

    def test_safe_fixes_promote_prefixed_design_skill_rows_into_category_section(self):
        draft = valid_draft()
        draft.resume = """NAME: Alex Example
ROLE: Creative Lead
CONTACT: alex@example.com

PROFESSIONAL SUMMARY
Designer focused on accessible digital experiences.

---

DESIGN SKILLS: Visual Systems | Brand storytelling, visual identity systems
DESIGN TOOLS: Core Creative Software | Adobe Creative Suite, Figma
CORE SKILLS: Strategy & Execution | User-centered design, creative direction

---

TOOLKIT
CATEGORY: Design & Multimedia Tools | Adobe Creative Suite, Figma

---

WORK EXPERIENCE
COMPANY: Example Studio
CREATIVE LEAD - 2020 - Present
● Built accessible digital experiences.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            job_type="design",
        )

        self.assertIn(
            "DESIGN SKILLS\n"
            "CATEGORY: Visual Systems | Brand storytelling, visual identity systems\n"
            "CATEGORY: Strategy & Execution | User-centered design, creative direction",
            fixed.resume,
        )
        self.assertNotIn("DESIGN SKILLS: Visual Systems", fixed.resume)
        self.assertNotIn("DESIGN TOOLS: Core Creative Software", fixed.resume)
        self.assertNotIn("CORE SKILLS: Strategy & Execution", fixed.resume)
        self.assertNotIn("CATEGORY: Core Creative Software", fixed.resume)
        self.assertIn("CATEGORY builder markers", " ".join(changes))

    def test_safe_fixes_limit_non_toolkit_categories_across_skill_sections(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "DESIGN SKILLS\n"
            "CATEGORY: Visual Identity | branding\n"
            "CATEGORY: Production Strategy | campaign production\n"
            "CATEGORY: Business Operations | project management\n"
            "CATEGORY: Creative Leadership | mentoring\n"
            "CATEGORY: Client Management | client servicing\n"
            "CATEGORY: Technical Expertise | product thinking\n\n"
            "---\n\n"
            "TOOLKIT\n"
            "CATEGORY: Design Tools | Figma, Blender\n\n"
            "---\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            job_type="design",
        )

        before_toolkit = fixed.resume.split("\nTOOLKIT\n", 1)[0]
        self.assertEqual(before_toolkit.count("CATEGORY:"), 4)
        self.assertIn("Visual Identity", before_toolkit)
        self.assertIn("Creative Leadership", before_toolkit)
        self.assertNotIn("Client Management", before_toolkit)
        self.assertNotIn("Technical Expertise", before_toolkit)
        self.assertIn("limited compact skill categories", " ".join(changes))

    def test_safe_fixes_restore_every_development_source_skill_exactly_once(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TECHNICAL SKILLS\n"
            "CATEGORY: Languages | Python\n"
            "CATEGORY: Frameworks | React\n\n"
            "---\n\n"
            "TOOLKIT\n"
            "CATEGORY: Languages | Python\n"
            "CATEGORY: Delivery | Docker\n\n"
            "---\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_resume=DEVELOPMENT_SOURCE_WITH_SKILLS,
            job_type="development",
        )

        toolkit = fixed.resume.split("\nTOOLKIT\n", 1)[1].split("\n---\n", 1)[0]
        self.assertEqual(
            [line for line in toolkit.splitlines() if line.startswith("CATEGORY:")],
            [
                "CATEGORY: Languages | Python, TypeScript",
                "CATEGORY: Frameworks | React, React Native",
                "CATEGORY: Testing | unittest, Playwright",
                "CATEGORY: Delivery | Docker, CI/CD",
                "CATEGORY: Architecture | REST APIs, Event-driven systems",
                "CATEGORY: Currently Learning | Rust",
            ],
        )
        category_values = [
            value.strip()
            for line in fixed.resume.splitlines()
            if line.startswith("CATEGORY:")
            for value in line.split("|", 1)[1].split(",")
        ]
        self.assertEqual(category_values.count("Python"), 1)
        self.assertEqual(category_values.count("React"), 1)
        self.assertEqual(category_values.count("React Native"), 1)
        self.assertIn("source skill", " ".join(changes).lower())

        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            source_resume=DEVELOPMENT_SOURCE_WITH_SKILLS,
            job_type="development",
        )

        self.assertEqual(fixed_again, fixed)
        self.assertNotIn("source skill", " ".join(second_changes).lower())

    def test_safe_fixes_preserve_csharp_source_skill_exactly(self):
        source_resume = """# Alex Example

## Toolkit and Technical Skills

### Languages
- C#
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TOOLKIT\n"
            "CATEGORY: Languages | C\n\n"
            "---\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
            job_type="development",
        )

        self.assertIn("CATEGORY: Languages | C#", fixed.resume)
        self.assertNotIn("CATEGORY: Languages | C\n", fixed.resume)
        self.assertNotIn("C++", fixed.resume)
        issues = validate_draft(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="development",
        )
        self.assertNotIn(
            "RESUME_SOURCE_SKILLS_MISSING",
            {issue.code for issue in issues},
        )

    def test_safe_fixes_do_not_limit_development_skill_categories(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TECHNICAL SKILLS\n"
            "CATEGORY: Languages | Python\n"
            "CATEGORY: Frameworks | React\n"
            "CATEGORY: Testing | unittest\n"
            "CATEGORY: Delivery | Docker\n"
            "CATEGORY: Architecture | REST APIs\n"
            "CATEGORY: Learning | Rust\n\n"
            "---\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            job_type="development",
        )

        technical_skills = fixed.resume.split(
            "\nTECHNICAL SKILLS\n", 1
        )[1].split("\n---\n", 1)[0]
        self.assertEqual(technical_skills.count("CATEGORY:"), 6)
        self.assertNotIn("limited compact skill categories", " ".join(changes))

    def test_safe_fixes_keep_em_dash_source_skill_as_one_category_value(self):
        source_resume = """# Alex Example

## Toolkit and Technical Skills

### Delivery
- GitHub \u2014 Version Control and CI
"""

        fixed, _ = apply_safe_deterministic_fixes(
            valid_draft(),
            owner_name="Alex Example",
            source_resume=source_resume,
            job_type="development",
        )

        self.assertIn(
            "CATEGORY: Delivery | GitHub - Version Control and CI",
            fixed.resume,
        )
        issues = validate_draft(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="development",
        )
        self.assertNotIn(
            "RESUME_SOURCE_SKILLS_MISSING",
            {issue.code for issue in issues},
        )

    def test_validator_blocks_missing_development_source_skills(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TOOLKIT\n"
            "CATEGORY: Languages | Python, TypeScript\n"
            "CATEGORY: Frameworks | React Native\n"
            "CATEGORY: Testing | unittest, Playwright\n"
            "CATEGORY: Delivery | Docker, CI/CD\n"
            "CATEGORY: Architecture | REST APIs, Event-driven systems\n"
            "CATEGORY: Currently Learning | Rust\n\n"
            "---\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=DEVELOPMENT_SOURCE_WITH_SKILLS,
            source_materials=DEVELOPMENT_SOURCE_WITH_SKILLS,
            job_type="development",
        )

        self.assertIn(
            "RESUME_SOURCE_SKILLS_MISSING",
            {issue.code for issue in issues},
        )

    def test_validator_blocks_duplicated_development_source_skills(self):
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TECHNICAL SKILLS\n"
            "CATEGORY: Languages | Python\n\n"
            "---\n\n"
            "TOOLKIT\n"
            "CATEGORY: Languages | Python, TypeScript\n"
            "CATEGORY: Frameworks | React, React Native\n"
            "CATEGORY: Testing | unittest, Playwright\n"
            "CATEGORY: Delivery | Docker, CI/CD\n"
            "CATEGORY: Architecture | REST APIs, Event-driven systems\n"
            "CATEGORY: Currently Learning | Rust\n\n"
            "---\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        issues = validate_draft(
            draft,
            owner_name="Alex Example",
            source_resume=DEVELOPMENT_SOURCE_WITH_SKILLS,
            source_materials=DEVELOPMENT_SOURCE_WITH_SKILLS,
            job_type="development",
        )

        self.assertIn(
            "RESUME_SOURCE_SKILLS_DUPLICATED",
            {issue.code for issue in issues},
        )

    def test_safe_fixes_preserve_required_ai_tools_when_limiting_categories(self):
        source_resume = """# Alex Example

## Toolkit

### AI Tools
- Pair Pilot
- Local Assistant
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TECHNICAL SKILLS\n"
            "CATEGORY: Languages | Python\n"
            "CATEGORY: Frameworks | Django\n"
            "CATEGORY: Infrastructure | AWS\n"
            "CATEGORY: Delivery | CI/CD\n"
            "CATEGORY: AI Tools | Pair Pilot, Local Assistant\n\n"
            "---\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
        )

        self.assertEqual(fixed.resume.count("CATEGORY:"), 4)
        self.assertIn(
            "CATEGORY: AI Tools | Pair Pilot, Local Assistant",
            fixed.resume,
        )
        self.assertNotIn("CATEGORY: Delivery | CI/CD", fixed.resume)

    def test_validator_requires_singular_other_work_experience_source_section(self):
        source_resume = """# Alex Example

## Other Work Experience

### Salesperson
**Example Retailer**
2024 - Present

- Helped customers choose products.
"""

        issues = validate_draft(
            valid_draft(),
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="design",
        )

        codes = {issue.code for issue in issues}
        self.assertIn("RESUME_SOURCE_EXPERIENCE_SECTIONS_MISSING", codes)
        self.assertIn("RESUME_SOURCE_EMPLOYERS_MISSING", codes)
        self.assertIn("RESUME_SOURCE_ROLES_MISSING", codes)

    def test_safe_fixes_restore_source_backed_ai_tools_category(self):
        source_resume = """# Alex Example

## Toolkit and Technical Skills

### Languages
- Python

### AI Tools
- Pair Pilot
- Local Assistant

## Work Experience
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TECHNICAL SKILLS\n"
            "CATEGORY: Languages | Python\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
        )

        self.assertIn(
            "CATEGORY: AI Tools | Pair Pilot, Local Assistant",
            fixed.resume,
        )
        self.assertIn("source-backed AI tools", " ".join(changes))
        self.assertEqual(fixed_again, fixed)
        self.assertEqual(second_changes, [])

    def test_safe_fixes_move_source_ai_tools_out_of_legacy_toolkit_row(self):
        source_resume = """# Alex Example

## Toolkit and Technical Skills

### AI Tools
- Pair Pilot
- Local Assistant
"""
        draft = valid_draft()
        draft.resume = draft.resume.replace(
            "PROFESSIONAL SUMMARY\n",
            "TOOLKIT: Web & Tech Stack | Figma, Pair Pilot, Local Assistant\n\n"
            "PROFESSIONAL SUMMARY\n",
        )

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            source_resume=source_resume,
            job_type="design",
        )
        issues = validate_draft(
            fixed,
            owner_name="Alex Example",
            source_resume=source_resume,
            source_materials=source_resume,
            job_type="design",
        )
        codes = {issue.code for issue in issues}

        self.assertEqual(
            fixed.resume.count(
                "CATEGORY: AI Tools | Pair Pilot, Local Assistant"
            ),
            1,
        )
        self.assertIn("CATEGORY: Web & Tech Stack | Figma", fixed.resume)
        self.assertNotIn("TOOLKIT: Web & Tech Stack", fixed.resume)
        self.assertNotIn(
            "TOOLKIT: Web & Tech Stack | Figma, Pair Pilot, Local Assistant",
            fixed.resume,
        )
        self.assertNotIn("RESUME_SOURCE_AI_TOOLS_MISSING", codes)
        self.assertNotIn("RESUME_AI_CONTENT_OUTSIDE_TOOLS_CATEGORY", codes)
        self.assertIn("source-backed AI tools", " ".join(changes))

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

    def test_safe_fixes_restore_dates_from_unbolded_source_role_labels(self):
        source_resume = """# Alex Example

## Work Experience

### Creative Director / Senior Art Director
**Example Agency**
Creative Director: April 2021 - Oct 2024, Full-time
Senior Art Director: April 2017 - April 2018, Full-time; 2019 - 2020, Freelance
"""
        draft = valid_draft()
        draft.resume = """NAME: Alex Example
ROLE: Creative Director
CONTACT: alex@example.com
LINKS: https://github.com/alex

PROFESSIONAL SUMMARY
Creative director focused on integrated campaigns.

---

EXPERIENCE
Example Agency
SENIOR ART DIRECTOR - April 2017 - April 2018, Full-time
● Led integrated campaigns.

CREATIVE DIRECTOR - April 2021 - Oct 2024, Full-time
● Directed multidisciplinary teams.
"""

        fixed, _ = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Creative Director",
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

        self.assertIn(
            "SENIOR ART DIRECTOR - April 2017 - April 2018, Full-time; "
            "2019 - 2020, Freelance",
            fixed.resume,
        )
        self.assertNotIn("RESUME_SOURCE_DATES_MISSING", codes)

    def test_safe_fixes_restore_honors_for_each_source_education_entry(self):
        source_resume = """# Alex Example

## Educational Attainment

### North College

**Software Development Diploma**
2024–2026
Graduated with Honors (GPA 3.84 / 4.0)

### South University

**Bachelor of Arts in Multimedia Arts**
Graduated with Honors and Dean’s Lister
"""
        draft = valid_draft()
        draft.resume += """

---

EDUCATION
North College | 2024 - 2026
Software Development Diploma

South University
Bachelor of Arts in Multimedia Arts
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Software Engineer",
            source_resume=source_resume,
        )

        self.assertIn(
            "Software Development Diploma (Graduated with Honors)",
            fixed.resume,
        )
        self.assertIn(
            "Bachelor of Arts in Multimedia Arts (Graduated with Honors)",
            fixed.resume,
        )
        self.assertEqual(fixed.resume.count("Graduated with Honors"), 2)
        self.assertIn("education honors", " ".join(changes).lower())

    def test_safe_fixes_restore_development_reference_sections_from_source(self):
        source_resume = """# Alex Example

## Educational Attainment

### SAIT — The Southern Alberta Institute of Technology

**Software Development Diploma**
Graduated with Honors — June 2026 — GPA 3.84 / 4.0

## Projects

### Reference Platform – Example Client and SAIT

**Capstone for Example Digital Services**
2025–2026

- Designed a modular backend architecture.
- Applied product design and delivery practices.

### Mobile Social App

2025–Present

- Developed an Android-first social platform.

## Related Work Experiences

### Software Engineer

**Example Labs**
Jan 2025 – Present

- Built reliable customer workflows.
- Improved operational productivity.

## Other Experiences

### Salesperson

**Example Retail — Customer Service**
Nov 2024 – Present, Part-time

- Supported customers.
"""
        draft = valid_draft()
        draft.resume += """

EDUCATION
SAIT, The Southern Alberta Institute of Technology | Graduated with Honors - June 2026 - GPA 3.84 / 4.0
Software Development Diploma

PROJECTS
Example School | 2026
● Flattened project content.

RELATED WORK EXPERIENCES
SOFTWARE ENGINEER - 2025
Example Labs
● Rewritten work content.

OTHER EXPERIENCES
Example Retail
SALESPERSON - 2024 - Present
● Rewritten retail content.
"""

        fixed, changes = apply_safe_deterministic_fixes(
            draft,
            owner_name="Alex Example",
            target_role="Software Engineer",
            source_resume=source_resume,
        )
        fixed_again, second_changes = apply_safe_deterministic_fixes(
            fixed,
            owner_name="Alex Example",
            target_role="Software Engineer",
            source_resume=source_resume,
        )

        self.assertIn(
            "PROJECT: Reference Platform – Example Client and SAIT",
            fixed.resume,
        )
        self.assertIn(
            "PROJECT_META: Capstone for Example Digital Services | 2025 - 2026",
            fixed.resume,
        )
        self.assertIn("COMPANY: Example Labs", fixed.resume)
        self.assertIn(
            "SOFTWARE ENGINEER - Jan 2025 - Present",
            fixed.resume,
        )
        self.assertIn(
            "COMPANY: Example Retail, Customer Service",
            fixed.resume,
        )
        self.assertNotIn("Flattened project content", fixed.resume)
        self.assertNotIn("Rewritten work content", fixed.resume)
        self.assertIn(
            "Restored the development reference sections",
            " ".join(changes),
        )
        self.assertEqual(fixed_again.model_dump(), fixed.model_dump())
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
