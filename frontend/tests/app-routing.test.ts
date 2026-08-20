import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { describe, it } from "node:test";

const compiledModuleUrl = new URL("../src/utils/app-routing.js", import.meta.url);

async function loadRoutingModule() {
  assert.equal(
    existsSync(compiledModuleUrl),
    true,
    "The hash-routing and catalog helpers have not been implemented.",
  );
  return import(compiledModuleUrl.href);
}

describe("application routing and location catalog helpers", () => {
  it("maps only the three supported hashes to top-level pages", async () => {
    const { pageFromHash, hashForPage } = await loadRoutingModule();

    assert.equal(pageFromHash("#/generate"), "generate");
    assert.equal(pageFromHash("#/edit/personal"), "personal");
    assert.equal(pageFromHash("#/edit/prompts"), "prompts");
    assert.equal(pageFromHash("#/unknown"), "generate");
    assert.equal(hashForPage("personal"), "#/edit/personal");
  });

  it("merges location suggestions without case-only duplicates", async () => {
    const { mergeLocations } = await loadRoutingModule();

    assert.deepEqual(
      mergeLocations(["Remote", "Calgary"], ["calgary", "New York", "REMOTE"]),
      ["Remote", "Calgary", "New York"],
    );
  });
});
