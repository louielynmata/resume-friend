import { useState } from "react";

import { api } from "../api/client";
import type { GenerateResult } from "../types";

interface Props {
  result: GenerateResult;
  onReset: () => void;
}

// ── Markdown → HTML (lightweight, analysis-scoped) ───────────────────────────

function md(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code class=\"bg-slate-100 px-1 rounded text-xs font-mono\">$1</code>");
}

function Md({ children }: { children: string }) {
  return <span dangerouslySetInnerHTML={{ __html: md(children) }} />;
}

// ── Analysis parsing ──────────────────────────────────────────────────────────

interface ParsedAnalysis {
  ats_score: number | null;
  score_rationale: string;
  keywords_applied: Array<{ keyword: string; placement: string }>;
  keywords_missing: Array<{ keyword: string; reason: string }>;
  key_decisions: string[];
  gaps: string[];
}

function parseAnalysis(raw: string): ParsedAnalysis {
  const result: ParsedAnalysis = {
    ats_score: null,
    score_rationale: "",
    keywords_applied: [],
    keywords_missing: [],
    key_decisions: [],
    gaps: [],
  };

  const scoreMatch = raw.match(/ATS_SCORE:\s*(\d+)/i);
  if (scoreMatch) result.ats_score = Math.min(100, Math.max(0, parseInt(scoreMatch[1], 10)));

  const rationaleMatch = raw.match(/SCORE_RATIONALE:\s*(.+?)(?=\n[A-Z_]+:|$)/is);
  if (rationaleMatch) result.score_rationale = rationaleMatch[1].trim();

  const appliedBlock = raw.match(/KEYWORDS_APPLIED:\s*([\s\S]+?)(?=\nKEYWORDS_MISSING:|$)/i);
  if (appliedBlock) {
    for (const line of appliedBlock[1].split("\n")) {
      const m = line.match(/^[-•]\s*(.+?)\s*[—–-]{1,2}\s*(.+)$/);
      if (m) result.keywords_applied.push({ keyword: m[1].trim(), placement: m[2].trim() });
    }
  }

  const missingBlock = raw.match(/KEYWORDS_MISSING:\s*([\s\S]+?)(?=\nKEY_DECISIONS:|$)/i);
  if (missingBlock) {
    for (const line of missingBlock[1].split("\n")) {
      const m = line.match(/^[-•]\s*(.+?)\s*[—–-]{1,2}\s*(.+)$/);
      if (m) result.keywords_missing.push({ keyword: m[1].trim(), reason: m[2].trim() });
    }
  }

  const decisionsBlock = raw.match(/KEY_DECISIONS:\s*([\s\S]+?)(?=\nGAPS:|$)/i);
  if (decisionsBlock) {
    for (const line of decisionsBlock[1].split("\n")) {
      const m = line.match(/^[-•]\s*(.+)$/);
      if (m) result.key_decisions.push(m[1].trim());
    }
  }

  const gapsBlock = raw.match(/GAPS:\s*([\s\S]+?)$/i);
  if (gapsBlock) {
    for (const line of gapsBlock[1].split("\n")) {
      const m = line.match(/^[-•]\s*(.+)$/);
      if (m) result.gaps.push(m[1].trim());
    }
  }

  return result;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function FileRow({ label, docx, pdf }: { label: string; docx?: string; pdf?: string | null }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 py-2 border-b border-slate-100 last:border-0">
      <span className="text-sm font-medium text-slate-700 sm:w-36 shrink-0">{label}</span>
      <div className="flex gap-2">
        {docx && (
          <span className="px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200 rounded text-xs font-mono">
            .docx ✓
          </span>
        )}
        {pdf ? (
          <span className="px-2 py-0.5 bg-green-50 text-green-700 border border-green-200 rounded text-xs font-mono">
            .pdf ✓
          </span>
        ) : (
          <span className="px-2 py-0.5 bg-slate-50 text-slate-400 border border-slate-200 rounded text-xs">
            .pdf — Word not installed
          </span>
        )}
      </div>
    </div>
  );
}

function AtsScoreRing({ score }: { score: number }) {
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const filled = (score / 100) * circumference;
  const color = score >= 75 ? "#16a34a" : score >= 50 ? "#d97706" : "#dc2626";
  const label = score >= 75 ? "Strong Match" : score >= 50 ? "Moderate Match" : "Needs Tailoring";

  return (
    <div className="flex flex-col items-center gap-1 shrink-0">
      <svg width="88" height="88" viewBox="0 0 96 96">
        <circle cx="48" cy="48" r={radius} fill="none" stroke="#e2e8f0" strokeWidth="8" />
        <circle
          cx="48" cy="48" r={radius} fill="none"
          stroke={color} strokeWidth="8"
          strokeDasharray={`${filled} ${circumference - filled}`}
          strokeLinecap="round"
          transform="rotate(-90 48 48)"
        />
        <text x="48" y="46" textAnchor="middle" dominantBaseline="middle" fontSize="20" fontWeight="700" fill={color}>
          {score}
        </text>
        <text x="48" y="63" textAnchor="middle" dominantBaseline="middle" fontSize="9" fill="#64748b">
          / 100
        </text>
      </svg>
      <span className="text-xs font-semibold" style={{ color }}>{label}</span>
    </div>
  );
}

function KeywordPill({ text, variant }: { text: string; variant: "applied" | "missing" }) {
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full border font-medium whitespace-nowrap ${
      variant === "applied"
        ? "bg-green-50 text-green-700 border-green-200"
        : "bg-red-50 text-red-600 border-red-200"
    }`}>
      {text}
    </span>
  );
}

function AnalysisPanel({ raw }: { raw: string }) {
  const [tab, setTab] = useState<"overview" | "keywords" | "decisions">("overview");
  const a = parseAnalysis(raw);

  const tabs: Array<{ id: typeof tab; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "keywords", label: `Keywords (${a.keywords_applied.length + a.keywords_missing.length})` },
    { id: "decisions", label: `Decisions (${a.key_decisions.length})` },
  ];

  return (
    <div className="flex flex-col h-full">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">AI Analysis</p>

      {/* Score row */}
      {a.ats_score !== null && (
        <div className="flex items-start gap-4 mb-4">
          <AtsScoreRing score={a.ats_score} />
          {a.score_rationale && (
            <p className="text-xs text-slate-600 leading-relaxed pt-1">
              <Md>{a.score_rationale}</Md>
            </p>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-slate-200 mb-3 gap-0">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`text-xs font-medium px-3 py-2 border-b-2 transition-colors ${
              tab === t.id
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto space-y-4 text-sm pr-0.5">

        {tab === "overview" && (
          <>
            {a.gaps.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Gaps</p>
                <ul className="space-y-2">
                  {a.gaps.map((g, i) => (
                    <li key={i} className="flex gap-2 text-slate-700 leading-snug">
                      <span className="text-amber-500 shrink-0 mt-0.5 text-xs">▲</span>
                      <span className="text-xs"><Md>{g}</Md></span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {a.keywords_missing.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Missing Keywords</p>
                <div className="flex flex-wrap gap-1.5">
                  {a.keywords_missing.map((k, i) => (
                    <KeywordPill key={i} text={k.keyword} variant="missing" />
                  ))}
                </div>
              </div>
            )}
            {a.gaps.length === 0 && a.keywords_missing.length === 0 && (
              <p className="text-xs text-slate-400">No major gaps identified.</p>
            )}
          </>
        )}

        {tab === "keywords" && (
          <>
            {a.keywords_applied.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-2">
                  Applied ({a.keywords_applied.length})
                </p>
                <div className="space-y-2">
                  {a.keywords_applied.map((k, i) => (
                    <div key={i} className="flex gap-2 items-start">
                      <KeywordPill text={k.keyword} variant="applied" />
                      <span className="text-xs text-slate-500 leading-snug"><Md>{k.placement}</Md></span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {a.keywords_missing.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-2">
                  Not Applied ({a.keywords_missing.length})
                </p>
                <div className="space-y-2">
                  {a.keywords_missing.map((k, i) => (
                    <div key={i} className="flex gap-2 items-start">
                      <KeywordPill text={k.keyword} variant="missing" />
                      <span className="text-xs text-slate-500 leading-snug"><Md>{k.reason}</Md></span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {tab === "decisions" && (
          <ul className="space-y-2">
            {a.key_decisions.map((d, i) => (
              <li key={i} className="flex gap-2 leading-snug">
                <span className="text-indigo-400 shrink-0 font-bold text-xs mt-0.5">{i + 1}.</span>
                <span className="text-xs text-slate-700"><Md>{d}</Md></span>
              </li>
            ))}
            {a.key_decisions.length === 0 && (
              <p className="text-xs text-slate-400">No decisions captured.</p>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function StepResult({ result, onReset }: Props) {
  const [isOpeningFolder, setIsOpeningFolder] = useState(false);
  const [folderError, setFolderError] = useState<string | null>(null);

  async function handleOpenFolder() {
    setIsOpeningFolder(true);
    setFolderError(null);
    try {
      await api.openFolder(result.output_folder);
    } catch (error) {
      setFolderError(error instanceof Error ? error.message : "Could not open folder.");
    } finally {
      setIsOpeningFolder(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Done header */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-green-100 flex items-center justify-center text-green-600 text-lg">
          ✓
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Done!</h2>
          <p className="text-xs text-slate-500">Your resume and cover letter have been generated.</p>
        </div>
      </div>

      <div className="space-y-4">

        {/* Saved to */}
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Saved to</p>
          <p className="text-sm font-mono text-slate-700 break-all">{result.output_folder}</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleOpenFolder}
              disabled={isOpeningFolder}
              className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-60"
            >
              {isOpeningFolder ? "Opening..." : "Open Folder"}
            </button>
            {folderError && <p className="text-sm text-red-600">{folderError}</p>}
          </div>
        </div>

        {/* Generated files */}
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">Generated Files</p>
          <FileRow label="Resume" docx={result.resume_docx} pdf={result.resume_pdf} />
          <FileRow label="Cover Letter" docx={result.cover_letter_docx} pdf={result.cover_letter_pdf} />
        </div>

        {/* AI Analysis — full width */}
        {result.analysis ? (
          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <AnalysisPanel raw={result.analysis} />
          </div>
        ) : null}

        {/* Notion */}
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Notion Tracking</p>
          {result.notion_page_url ? (
            <a
              href={result.notion_page_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-indigo-600 hover:underline break-all"
            >
              ↗ Open in Notion
            </a>
          ) : result.notion_error ? (
            <div className="space-y-1.5">
              <p className="text-xs text-red-600 font-medium">Notion logging failed</p>
              <p className="text-xs text-red-500 break-all font-mono bg-red-50 border border-red-100 rounded p-2 leading-relaxed">
                {result.notion_error}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Run <span className="font-mono bg-slate-100 px-1 rounded">GET /api/notion/test</span> to diagnose.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-400">
              Not logged — add NOTION_TOKEN and NOTION_DATABASE_ID to .env to enable.
            </p>
          )}
        </div>

        <button
          onClick={onReset}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700"
        >
          Generate Another
        </button>

      </div>
    </div>
  );
}
