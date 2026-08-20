export type AppPage = "generate" | "personal" | "prompts";

const PAGE_HASHES: Record<AppPage, string> = {
  generate: "#/generate",
  personal: "#/edit/personal",
  prompts: "#/edit/prompts",
};

export function pageFromHash(hash: string): AppPage {
  const match = (Object.entries(PAGE_HASHES) as Array<[AppPage, string]>).find(
    ([, route]) => route === hash,
  );
  return match?.[0] ?? "generate";
}

export function hashForPage(page: AppPage): string {
  return PAGE_HASHES[page];
}

export function mergeLocations(
  current: string[],
  incoming: string[],
): string[] {
  const locations = new Map<string, string>();
  for (const value of [...current, ...incoming]) {
    const trimmed = value.trim();
    if (trimmed && !locations.has(trimmed.toLocaleLowerCase())) {
      locations.set(trimmed.toLocaleLowerCase(), trimmed);
    }
  }
  return [...locations.values()].sort((left, right) => {
    if (left.toLocaleLowerCase() === "remote") return -1;
    if (right.toLocaleLowerCase() === "remote") return 1;
    return left.localeCompare(right, undefined, { sensitivity: "base" });
  });
}
