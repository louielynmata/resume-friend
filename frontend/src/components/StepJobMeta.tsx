import type { GenerationFeedItem, JobMeta } from "../types";

interface Props {
  meta: JobMeta;
  onChange: (meta: JobMeta) => void;
  onBack: () => void;
  onGenerate: () => void;
  generating: boolean;
  extracting: boolean;
  generationFeed: GenerationFeedItem[];
  generationErrorCode?: string;
  generationErrorStatus?: number;
  generationErrorHint?: string;
  generationElapsedSeconds: number;
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

const inputClass =
  "w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400";

function statusClass(status: GenerationFeedItem["status"]) {
  if (status === "done") return "bg-green-100 text-green-700 border-green-200";
  if (status === "active") return "bg-blue-100 text-blue-700 border-blue-200";
  if (status === "failed") return "bg-red-100 text-red-700 border-red-200";
  return "bg-slate-100 text-slate-500 border-slate-200";
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)} sec`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes} min ${remaining} sec`;
}

export function StepJobMeta({
  meta,
  onChange,
  onBack,
  onGenerate,
  generating,
  extracting,
  generationFeed,
  generationErrorCode,
  generationErrorStatus,
  generationErrorHint,
  generationElapsedSeconds,
}: Props) {
  const set = (key: keyof JobMeta) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...meta, [key]: e.target.value });

  const HOURS_PER_YEAR = 2080;

  function handleAnnualChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value;
    const num = parseFloat(raw);
    const hourly = raw && !isNaN(num) ? (num / HOURS_PER_YEAR).toFixed(2) : "";
    onChange({ ...meta, salary_annual: raw, salary_hourly: hourly });
  }

  function handleHourlyChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value;
    const num = parseFloat(raw);
    const annual = raw && !isNaN(num) ? String(Math.round(num * HOURS_PER_YEAR)) : "";
    onChange({ ...meta, salary_hourly: raw, salary_annual: annual });
  }

  const canGenerate = meta.position.trim() && meta.company.trim();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Job Details</h2>
        <p className="text-sm text-slate-500">
          Used for file naming and Notion tracking. Required fields are marked with *.
        </p>
        {extracting && (
          <p className="text-sm text-indigo-600 mt-2">Extracting job details from the description…</p>
        )}
      </div>

      {generationFeed.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-800">Generation Feed</h3>
              <p className="text-xs text-slate-500">Tracks the current pipeline and where failures occur.</p>
            </div>
            <p className="text-xs font-mono text-slate-600 whitespace-nowrap">
              {generating ? "Elapsed" : "Duration"}: {formatElapsed(generationElapsedSeconds)}
            </p>
          </div>

          <div className="space-y-2">
            {generationFeed.map((item, index) => (
              <div key={item.id} className="flex items-start gap-3">
                <div className={`mt-0.5 w-7 h-7 rounded-full border text-xs flex items-center justify-center ${statusClass(item.status)}`}>
                  {item.status === "done" ? "OK" : item.status === "failed" ? "!" : index + 1}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800">{item.label}</p>
                  <p className="text-xs text-slate-500">{item.description}</p>
                  {item.detail && <p className="text-xs text-slate-700 mt-1 break-words">{item.detail}</p>}
                </div>
              </div>
            ))}
          </div>

          {(generationErrorCode || generationErrorStatus || generationErrorHint) && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800 space-y-1">
              {generationErrorStatus && <p>HTTP Status: {generationErrorStatus}</p>}
              {generationErrorCode && <p>Error Code: {generationErrorCode}</p>}
              {generationErrorHint && <p>Hint: {generationErrorHint}</p>}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Position" required>
          <input
            type="text"
            name="position"
            autoComplete="organization-title"
            value={meta.position}
            onChange={set("position")}
            placeholder="e.g. Senior UX Designer"
            className={inputClass}
          />
        </Field>

        <Field label="Company" required>
          <input
            type="text"
            name="company"
            autoComplete="organization"
            value={meta.company}
            onChange={set("company")}
            placeholder="e.g. Acme Corp"
            className={inputClass}
          />
        </Field>

        <Field label="Location">
          <input
            type="text"
            name="location"
            autoComplete="address-level2"
            value={meta.location}
            onChange={set("location")}
            placeholder="e.g. Calgary, AB (Hybrid)"
            className={inputClass}
          />
        </Field>

        <Field label="Date of Job Posting">
          <input
            type="date"
            name="date_job_posted"
            autoComplete="on"
            value={meta.date_job_posted}
            onChange={set("date_job_posted")}
            className={inputClass}
          />
        </Field>

        <Field label="Salary (Annual)">
          <input
            type="number"
            name="salary_annual"
            autoComplete="on"
            value={meta.salary_annual}
            onChange={handleAnnualChange}
            placeholder="e.g. 85000"
            className={inputClass}
          />
        </Field>

        <Field label="Salary (Hourly)">
          <input
            type="number"
            name="salary_hourly"
            autoComplete="on"
            value={meta.salary_hourly}
            onChange={handleHourlyChange}
            placeholder="e.g. 42.50"
            step="0.01"
            className={inputClass}
          />
        </Field>

        <Field label="Contact Email (optional)">
          <input
            type="email"
            name="contact_email"
            autoComplete="email"
            value={meta.contact_email}
            onChange={set("contact_email")}
            placeholder="hiring@acmecorp.com"
            className={`${inputClass} sm:col-span-2`}
          />
        </Field>
      </div>

      <div className="flex justify-between pt-2">
        <button
          onClick={onBack}
          disabled={generating}
          className="px-6 py-2 text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
        >
          ← Back
        </button>
        <button
          onClick={onGenerate}
          disabled={!canGenerate || generating}
          className="px-8 py-2 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {generating ? (
            <>
              <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Generating…
            </>
          ) : (
            "Generate Resume & Cover Letter"
          )}
        </button>
      </div>
    </div>
  );
}
