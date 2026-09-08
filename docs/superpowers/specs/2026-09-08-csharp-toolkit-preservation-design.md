# C# Toolkit Preservation Design

## Goal

Development resume generation must preserve the source skill `C#` exactly. It must never normalize that value to `C` or `C++`, and the canonical development `TOOLKIT` must continue to use source-backed spelling.

## Root Cause

The development Toolkit parser passes bullet values through the shared `_plain_text` helper. That helper currently removes every `#` character while stripping Markdown syntax, so `C#` becomes `C` before `_restore_development_source_skills` builds the canonical Toolkit.

## Design

Change `_plain_text` so it removes Markdown heading markers only when they are structural markers at the start of a line. Preserve literal `#` characters within content. This fixes the problem at the normalization boundary and retains source spelling for `C#` without adding a technology-specific exception.

No frontend, API, provider, document-builder, or Notion behavior changes. Existing deterministic Toolkit restoration remains the owner of the development skill invariant.

## Validation

Add a focused QA-service regression test whose source development resume contains `C#` and whose generated draft contains `C`. The deterministic repair must emit `CATEGORY: Languages | C#`, contain neither a standalone `C` value nor `C++`, and pass the source-skill completeness validator.

Run the focused QA test module followed by the full backend test suite. No document rendering check is required because this change affects semantic text normalization and not document layout.

## Risks

Preserving literal `#` may affect normalized comparisons that previously discarded it. That distinction is intentional for programming-language names: `C#` and `C` must not compare as the same source-backed fact. Structural Markdown headings remain normalized by removing only their leading heading marker.
