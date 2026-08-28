# Visible Work-Sample URLs Design

## Context

Resume Friend currently renders the required `WORK_SAMPLES:` entries as
friendly hyperlink labels. The exact source URL is stored in each DOCX
hyperlink relationship, but it is not visible in the document text. Microsoft
Word's **Print as PDF** path can omit those hyperlink relationships, leaving the
printed PDF with labels that no longer expose their destinations.

The application-owned PDF conversion and repair path remains useful, but it
cannot protect a PDF created later through Word. The DOCX therefore needs to be
self-describing before it leaves Resume Friend.

## Invariant

Every required work-sample entry must show the applicant-supplied URL as
visible text in the resume DOCX while retaining the existing exact hyperlink
target. If hyperlink metadata is removed by a later print operation, a reader
must still be able to see and copy the destination.

The URL must come from the trusted, track-specific link mapping extracted from
the applicant instructions. Resume Friend must not infer, shorten, rewrite, or
substitute a URL.

## Scope

The existing track rules remain unchanged:

| Track | Visible work-sample entries |
| --- | --- |
| Design | `Design Portfolio (Reel and PDF)` and `Case Studies and Product Work` |
| Development | `Case Studies and Product Work` only |

This change does not alter the semantic `WORK_SAMPLES:` Markdown contract,
general contact links, source-link extraction, Notion gating, or PDF conversion
policy. It changes only how required work-sample links are rendered in the
resume header and clarifies the related prompt rule.

## Design

The document builder will continue receiving the trusted label-to-URL mapping
already passed through the QA pipeline. For each required Markdown work-sample
link, it will render one centered paragraph in this form:

```text
Design Portfolio (Reel and PDF): https://example.com/design-portfolio
Case Studies and Product Work: https://example.com/case-studies
```

Both the friendly label and visible URL will be hyperlinks to the same exact
trusted target. The URL remains readable if Word later strips the hyperlink
relationship. Long URLs may wrap naturally within their centered paragraph;
they must not be shortened because query parameters and fragments can be part
of the required destination.

The semantic draft remains concise and source-compatible:

```text
WORK_SAMPLES: [Design Portfolio (Reel and PDF)](exact URL) | [Case Studies and Product Work](exact URL)
```

Keeping visible-URL rendering in the deterministic builder avoids depending on
an AI provider to duplicate the URLs correctly. The generation and QA prompts
will clarify that the complete Markdown target must remain exact because the
builder exposes that target in the final document.

## Failure Handling

Existing fail-closed behavior remains authoritative. A missing, ambiguous, or
incorrect source link is rejected before generation or during semantic/artifact
QA. The builder will not display an untrusted generated target in place of the
trusted mapping. Existing retained QA evidence and Notion gating are unchanged.

## Testing and Validation

Implementation will follow test-driven development:

1. Add a focused DOCX layout regression test that expects two centered
   work-sample paragraphs and verifies that each contains the exact visible URL.
2. Verify that each label and displayed URL targets the exact trusted source
   URL in the DOCX relationships.
3. Cover the Development case to ensure it displays only the Case Studies URL.
4. Run the focused document, work-sample, QA, artifact, and pipeline tests, then
   the complete backend suite.
5. Render a non-personal Design fixture and visually inspect header wrapping,
   spacing, labels, and full URL text. Report if local PDF conversion is
   unavailable.

No live AI-provider call is needed.

## Acceptance Criteria

- Design resumes visibly display the exact Design Portfolio and Case Studies
  URLs beside their friendly labels.
- Development resumes visibly display only the exact Case Studies URL.
- Labels and visible URLs remain clickable in the DOCX.
- The URLs remain readable after hyperlink metadata is removed by Word's print
  path.
- Long URLs are preserved character-for-character and may wrap without being
  truncated.
- Existing truthfulness checks, artifact QA, retained failure evidence, and
  Notion fail-closed behavior remain intact.
