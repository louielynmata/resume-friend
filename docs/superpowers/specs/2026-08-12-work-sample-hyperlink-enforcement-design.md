# Work-Sample Hyperlink Enforcement Design

## Context

Resume Friend already stores source-supported work-sample links in
`models_personal/instructions_prompt.md` and restores the applicable
`WORK_SAMPLES:` header line during deterministic QA. The intended track rules
are:

- Design resumes include `Design Portfolio (Reel and PDF)` and
  `Case Studies and Product Work`.
- Development resumes include `Case Studies and Product Work` only.

Retained outputs show two distinct risks. Development resumes correctly omit
the design portfolio under the current track contract, but some generated PDFs
displayed work-sample labels without external hyperlink annotations. Semantic
text validation alone therefore does not prove that a submitted artifact is
clickable.

## Invariant

Every work-sample link required by the selected track must:

1. Use the exact visible label and URL supplied by the applicant's personal
   Markdown.
2. Appear in the semantic resume draft as a labeled Markdown link.
3. Render as a hyperlink with the exact expected target in the resume DOCX.
4. Render as a clickable external link with the exact expected target in the
   resume PDF whenever a PDF is produced.

The system must never invent, infer, or substitute a work-sample URL. A missing,
plain-text, or incorrectly targeted required link is a blocking QA failure and
must prevent Notion logging.

## Scope

The current insertion rules remain unchanged:

| Track | Required work-sample links |
| --- | --- |
| Design | `Design Portfolio (Reel and PDF)` and `Case Studies and Product Work` |
| Development | `Case Studies and Product Work` |

This change strengthens validation and artifact integrity. It does not add the
design portfolio to Development resumes, change page limits, change general
contact links, or require PDF conversion on systems where it is unavailable.
When a resume PDF is produced, however, its required work-sample links must be
clickable for QA to pass.

## Architecture and Components

### Trusted-link extraction

Add one deterministic helper that extracts the two recognized labeled Markdown
links from the applicant instructions and returns the subset required for the
selected track. The helper preserves each URL character-for-character and does
not accept an unlabeled URL as a substitute.

The helper is the shared definition of the work-sample contract. Semantic QA
and artifact QA consume its result rather than reimplementing track logic.
Generation calls it immediately after loading the personal source files and
before invoking an AI provider. A missing required labeled source link returns
an actionable HTTP 422 error with code
`SOURCE_REQUIRED_WORK_SAMPLE_LINK_MISSING`; it cannot consume a paid-provider
call or enter an impossible content-repair loop.

### Semantic draft enforcement

Keep the existing required-header restoration path. Strengthen its validation
with a specific blocking issue when a required work-sample labeled link is
absent, malformed, or differs from the trusted source pair. Deterministic repair
continues to restore the exact applicable `WORK_SAMPLES:` line before asking an
AI reviewer to repair content.

If the semantic draft omits or changes an expected pair after deterministic
repair, report blocking issue `RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH`. Do
not let an AI guess a replacement URL.

### DOCX artifact enforcement

Extend artifact inspection with the expected label-to-URL mapping. For the
resume DOCX, inspect the underlying hyperlink relationships and hyperlink text.
Each required label must be inside a hyperlink and its relationship target must
equal the source URL. Merely finding the label in paragraph text is insufficient.

### PDF artifact enforcement

When a resume PDF exists, inspect its external link annotations. Each expected
source URL must be present as a clickable target, and the corresponding label
must remain visible in extracted page text. A visible label without an external
link annotation is a blocking artifact error.

The existing `PDF_NOT_AVAILABLE` behavior remains a warning because PDF
conversion depends on local software. This design does not broaden the request
into a mandatory-conversion change.

### Prompts and example configuration

Clarify the public generation and QA prompts and the example personal
instructions: preserve the current track-specific inclusion rules, but never
return an included work-sample label without its Markdown URL. Applicant-specific
URLs remain only in `models_personal/`; tests and examples use non-personal URLs.

## Data Flow

1. Load applicant instructions and select the Design or Development track.
2. Extract and preflight the exact required labeled links from the trusted
   instructions before any provider call.
3. Deterministically restore the track-specific `WORK_SAMPLES:` line.
4. Validate the semantic draft against the expected label-to-URL mapping.
5. Build DOCX and, when conversion is available, PDF artifacts.
6. Inspect DOCX relationships and PDF link annotations against the same mapping.
7. Continue to successful output and optional Notion logging only when all
   blocking checks pass.

## Error Handling

Use these stable, actionable issue codes to distinguish source configuration,
semantic output, and rendered artifacts:

- `SOURCE_REQUIRED_WORK_SAMPLE_LINK_MISSING`
- `RESUME_REQUIRED_WORK_SAMPLE_LINK_MISMATCH`
- `DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_MISSING`
- `DOCX_REQUIRED_WORK_SAMPLE_HYPERLINK_TARGET_MISMATCH`
- `PDF_REQUIRED_WORK_SAMPLE_LINK_MISSING`
- `PDF_REQUIRED_WORK_SAMPLE_LINK_TARGET_MISMATCH`

Messages may name the public label but must not expose unnecessary personal
data. Existing QA failure evidence remains retained, and failed packages remain
blocked from Notion.

## Testing

Follow test-driven development with focused regression cases:

- Design track selects both exact labeled source links.
- Development track selects only Case Studies.
- Deterministic repair restores the applicable complete `WORK_SAMPLES:` line.
- Missing or malformed required source links fail closed without URL invention.
- A DOCX with correct labels and relationship targets passes.
- A DOCX with plain-text labels, a missing label, or a wrong target fails.
- A PDF with visible labels and correct external annotations passes.
- A PDF with visible labels but no annotation, a missing label, or a wrong target
  fails.
- Artifact failures remain blocking through the QA pipeline and prevent Notion
  logging.

Run the focused QA, artifact, document-layout, and generation-route tests, then
the full backend suite. Render a non-personal fixture package and inspect both
the DOCX hyperlink relationships and PDF link annotations. No live paid-provider
call is required.

## Acceptance Criteria

- Every Design resume contains both required labels as hyperlinks to the exact
  source URLs in its DOCX and in its PDF when produced.
- Every Development resume contains Case Studies as a hyperlink to the exact
  source URL and does not gain the Design Portfolio link.
- Visible-but-not-clickable work-sample labels cannot pass artifact QA.
- Unsupported URLs are never introduced.
- A package with a blocking work-sample issue is not logged to Notion.
