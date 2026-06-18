import { useState } from "react";

import { api } from "../api/client";
import type { GenerateResult } from "../types";

interface Props {
  result: GenerateResult;
  onReset: () => void;
}

function FileRow({ label, docx, pdf }: { label: string; docx?: string; pdf?: string | null }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 py-2 border-b border-slate-100 last:border-0">
      <span className="text-sm font-medium text-slate-700 sm:w-48 shrink-0">{label}</span>
      <div className="flex gap-2 text-sm">
        {docx && (
          <span className="px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200 rounded text-xs font-mono break-all">
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
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center text-green-600 text-xl">
          ✓
        </div>
        <div>
          <h2 className="text-xl font-semibold text-slate-800">Done!</h2>
          <p className="text-sm text-slate-500">Your resume and cover letter have been generated.</p>
        </div>
      </div>

      {/* Output folder */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Saved to</p>
        <p className="text-sm font-mono text-slate-700 break-all">{result.output_folder}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleOpenFolder}
            disabled={isOpeningFolder}
            className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isOpeningFolder ? "Opening..." : "Open Folder"}
          </button>
          {folderError ? <p className="text-sm text-red-600">{folderError}</p> : null}
        </div>
      </div>

      {/* Files */}
      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">Generated Files</p>
        <FileRow label="Resume" docx={result.resume_docx} pdf={result.resume_pdf} />
        <FileRow label="Cover Letter" docx={result.cover_letter_docx} pdf={result.cover_letter_pdf} />
      </div>

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
        ) : (
          <p className="text-sm text-slate-400">
            Not logged — add NOTION_TOKEN and NOTION_DATABASE_ID to .env to enable.
          </p>
        )}
      </div>

      <div className="flex justify-between">
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
