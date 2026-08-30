# Development Skill Preservation Design

## Goal

Development resumes must retain every skill and tool listed in the applicant's source resume. Tailoring may reorganize or deduplicate those entries, but job relevance, model preference, and the two-page layout target must never cause an omission.

## Invariant

For a development resume, every non-empty bullet beneath each third-level category in the source `Toolkit and Technical Skills` section must appear in the generated resume exactly once as a `CATEGORY:` value. Preserve the source spelling, category order, item order, and category labels. This rule does not apply to design resumes.

If retaining the complete source skillset makes a development resume exceed two pages, artifact QA must report the existing page-limit failure. The application must not resolve that failure by deleting skills.

## Existing Behavior and Cause

The current generation and QA prompts ask for only two to four compact non-Toolkit categories and permit only two to four Toolkit categories. Deterministic QA also truncates non-Toolkit categories to four. Only the `AI Tools` source subsection currently has an explicit source-completeness restoration and validation rule.

Together, these behaviors allow development resumes to reduce a broad source skillset even though every retained item remains truthful.

## Design

### Source extraction

Add a deterministic parser in `backend/services/qa_service.py` that reads the development source resume's `Toolkit and Technical Skills` section. It will collect each third-level heading as a category and its non-empty bullet items as ordered source values. Duplicate source values will be retained at their first occurrence only, using the same normalized matching strategy used by existing category QA.

The parser returns no categories when the expected source section is absent. In that case, existing behavior remains unchanged and the application does not infer skills.

### Deterministic restoration

During `apply_safe_deterministic_fixes`, after category syntax normalization and consolidation:

1. For `job_type="development"`, rebuild the generated `TOOLKIT` block from the extracted source categories.
2. Preserve each source category label and value exactly, in source order.
3. Remove matching source values from other compact skill sections so each source item appears once.
4. Remove empty category lines and collapse resulting blank space.
5. Skip the four-category limiter for development resumes. Keep its existing design-resume behavior.

The transformation must be idempotent: applying it twice produces the same resume and no second change record.

### Validation

Extend deterministic validation for development resumes with stable blocking issue codes:

- `RESUME_SOURCE_SKILLS_MISSING` when one or more extracted source values do not appear in parsed `CATEGORY:` values.
- `RESUME_SOURCE_SKILLS_DUPLICATED` when an extracted source value appears more than once across parsed `CATEGORY:` values.

Comparisons use normalized exact category values rather than substring searching, so names such as `React` and `React Native` remain distinct. Issue messages list the affected source values and direct the reviewer to restore or deduplicate them without inventing replacements.

### Prompt alignment

Update `prompts/system_prompt.md` and `prompts/qa_prompt.md` with a development-specific exception:

- Preserve every source skill and tool exactly once.
- Preserve source category and item order.
- Regrouping is not necessary because deterministic QA emits the canonical source structure.
- Do not remove skills for relevance or page count.
- Keep the existing compact category limits for design resumes only.

The backend remains the authority; prompt wording reduces avoidable model repairs but is not relied upon for correctness.

## Data Flow

The source development resume is passed through the existing generation pipeline. Initial AI output may omit or duplicate skills. Deterministic QA then extracts the canonical source categories, normalizes the draft, restores the canonical Toolkit block, and removes duplicates. Validation compares the repaired category values against the source. Document generation and artifact QA run only after the blocking semantic checks pass.

## Tests

Add focused regression tests before production changes:

1. A development draft with more than four source categories retains every category and value.
2. Missing source skills are restored deterministically.
3. Duplicate source skills outside Toolkit are removed while the canonical Toolkit value remains.
4. Similar names are treated as distinct exact values.
5. The transformation is idempotent.
6. Validation reports missing and duplicated development source skills.
7. Design resumes retain the existing four-category limit and do not inherit the development-only preservation rule.

Run the focused QA service tests followed by the complete backend test suite. No frontend contract or document-layout code changes are planned, so frontend builds and rendered-document inspection are not required unless implementation reveals an unexpected cross-layer effect.

## Compatibility and Risks

The change may increase development resume length. This is intentional: the two-page limit remains observable and fail-closed, while the applicant's source skillset takes precedence over automatic trimming. Existing source truthfulness rules remain unchanged, and no skill can be added unless present in the source resume.

The implementation will preserve unrelated working-tree changes and will modify only the approved prompt, QA service, and regression-test areas required by this invariant.
