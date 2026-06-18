import { useState } from "react";
import { api } from "../api/client";

interface Props {
  value: string;
  onChange: (text: string) => void;
  onNext: () => void;
}

export function StepJobInput({ value, onChange, onNext }: Props) {
  const [mode, setMode] = useState<"text" | "url">("text");
  const [url, setUrl] = useState("");
  const [scraping, setScraping] = useState(false);
  const [scrapeError, setScrapeError] = useState("");

  async function handleScrape() {
    if (!url.trim()) return;
    setScraping(true);
    setScrapeError("");
    try {
      const result = await api.scrapeJob(url.trim());
      onChange(result.text);
      setMode("text");
    } catch (e: unknown) {
      setScrapeError(e instanceof Error ? e.message : "Failed to scrape URL");
    } finally {
      setScraping(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Job Description</h2>
        <p className="text-sm text-slate-500">Paste the job posting text or enter a URL to scrape it.</p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setMode("text")}
          className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
            mode === "text"
              ? "bg-indigo-600 text-white"
              : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-50"
          }`}
        >
          Paste Text
        </button>
        <button
          onClick={() => setMode("url")}
          className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
            mode === "url"
              ? "bg-indigo-600 text-white"
              : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-50"
          }`}
        >
          Scrape URL
        </button>
      </div>

      {mode === "url" ? (
        <div className="space-y-2">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://jobs.example.com/position/12345"
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            onKeyDown={(e) => e.key === "Enter" && handleScrape()}
          />
          {scrapeError && <p className="text-red-500 text-sm">{scrapeError}</p>}
          <button
            onClick={handleScrape}
            disabled={!url.trim() || scraping}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {scraping ? "Scraping…" : "Fetch Job Description"}
          </button>
          {value && (
            <p className="text-green-600 text-sm">
              ✓ Job description fetched ({value.length.toLocaleString()} chars).{" "}
              <button onClick={() => setMode("text")} className="underline">
                Review text
              </button>
            </p>
          )}
        </div>
      ) : (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Paste the full job description here…"
          rows={14}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
      )}

      <div className="flex justify-end">
        <button
          onClick={onNext}
          disabled={!value.trim()}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
