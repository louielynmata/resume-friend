import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const compiledModuleUrl = new URL(
  "../src/components/MarkdownFileTabs.js",
  import.meta.url,
);

async function loadTabsModule() {
  assert.equal(
    existsSync(compiledModuleUrl),
    true,
    "The Markdown file tabs have not been implemented.",
  );
  return import(compiledModuleUrl.href);
}

describe("Markdown file tabs", () => {
  it("renders each file as an accessible tab instead of a select control", async () => {
    const { MarkdownFileTabs } = await loadTabsModule();
    const markup = renderToStaticMarkup(
      createElement(MarkdownFileTabs, {
        group: "personal",
        files: [
          {
            group: "personal",
            file_id: "design_resume",
            filename: "design_resume.md",
            display_name: "Design resume",
            exists: true,
            source: "personal",
            writable: true,
          },
          {
            group: "personal",
            file_id: "dev_resume",
            filename: "dev_resume.md",
            display_name: "Development resume",
            exists: true,
            source: "personal",
            writable: true,
          },
        ],
        selectedId: "design_resume",
        disabled: false,
        onSelect: () => undefined,
      }),
    );

    assert.match(markup, /role="tablist"/);
    assert.equal(markup.match(/role="tab"/g)?.length, 2);
    assert.match(markup, /aria-label="Personal Markdown files"/);
    assert.match(markup, /aria-controls="personal-markdown-panel"/);
    assert.match(markup, /aria-selected="true"/);
    assert.match(markup, /aria-selected="false"/);
    assert.match(markup, />Design resume</);
    assert.match(markup, />design_resume\.md</);
    assert.doesNotMatch(markup, /<select/);
  });
});
