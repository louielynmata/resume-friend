import { useState } from "react";
import { api } from "../api/client";

interface Props {
  value: string;
  onChange: (text: string) => void;
  companyContext: string;
  onCompanyContextChange: (text: string) => void;
  onClearForm: () => void;
  onNext: () => void;
}

export function StepJobInput({
  value,
  onChange,
  companyContext,
  onCompanyContextChange,
  onClearForm,
  onNext,
}: Props) {
  const [mode, setMode] = useState<"text" | "url">("text");
  const [url, setUrl] = useState("");
  const [scraping, setScraping] = useState(false);
  const [scrapeError, setScrapeError] = useState("");

  const [companyUrl, setCompanyUrl] = useState("");
  const [scrapingCompany, setScrapingCompany] = useState(false);
  const [companyError, setCompanyError] = useState("");

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

  async function handleScrapeCompany() {
    if (!companyUrl.trim()) return;
    setScrapingCompany(true);
    setCompanyError("");
    try {
      const result = await api.scrapeJob(companyUrl.trim());
      onCompanyContextChange(result.text);
    } catch (e: unknown) {
      setCompanyError(e instanceof Error ? e.message : "Failed to fetch company page");
    } finally {
      setScrapingCompany(false);
    }
  }

  function clearCompany() {
    onCompanyContextChange("");
    setCompanyUrl("");
    setCompanyError("");
  }

  function handleClearForm() {
    if (!window.confirm("Clear all saved job and application form values?")) {
      return;
    }
    setMode("text");
    setUrl("");
    setScrapeError("");
    setCompanyUrl("");
    setCompanyError("");
    onClearForm();
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Job Description</h2>
        <p className="text-sm text-slate-500">
          Paste the job posting text or enter a URL to scrape it. Entries are saved in this browser.
        </p>
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
            name="job_posting_url"
            autoComplete="url"
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
          name="job_description"
          autoComplete="on"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Paste the full job description here…"
          rows={12}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
      )}

      {/* Company About Page */}
      <div className="border-t border-slate-200 pt-4 space-y-2">
        <div>
          <p className="text-sm font-medium text-slate-700">
            Company Website{" "}
            <span className="text-xs text-slate-400 font-normal">— optional</span>
          </p>
          <p className="text-xs text-slate-400 mt-0.5">
            Paste the company's About page URL. The AI will use their mission, values, and culture to
            personalise the cover letter and tailor the analysis.
          </p>
        </div>

        {companyContext ? (
          <div className="flex items-center justify-between bg-green-50 border border-green-200 rounded-lg px-3 py-2">
            <p className="text-xs text-green-700">
              ✓ About page fetched — {companyContext.length.toLocaleString()} chars
            </p>
            <button
              onClick={clearCompany}
              className="text-xs text-slate-400 hover:text-slate-600 underline ml-4"
            >
              Clear
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            <input
              type="url"
              name="company_about_url"
              autoComplete="url"
              value={companyUrl}
              onChange={(e) => setCompanyUrl(e.target.value)}
              placeholder="https://company.com/about"
              className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              onKeyDown={(e) => e.key === "Enter" && handleScrapeCompany()}
            />
            <button
              onClick={handleScrapeCompany}
              disabled={!companyUrl.trim() || scrapingCompany}
              className="px-3 py-2 bg-slate-700 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {scrapingCompany ? "Fetching…" : "Fetch"}
            </button>
          </div>
        )}
        {companyError && <p className="text-red-500 text-xs">{companyError}</p>}
      </div>

      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={handleClearForm}
          className="px-4 py-2 text-red-600 border border-red-200 rounded-lg text-sm font-medium hover:bg-red-50"
        >
          Clear Form
        </button>
        <button
          type="button"
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
