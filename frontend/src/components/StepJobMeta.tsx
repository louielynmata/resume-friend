interface Meta {
  position: string;
  company: string;
  location: string;
  salary_annual: string;
  salary_hourly: string;
  date_job_posted: string;
  contact_email: string;
}

interface Props {
  meta: Meta;
  onChange: (meta: Meta) => void;
  onBack: () => void;
  onGenerate: () => void;
  generating: boolean;
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

export function StepJobMeta({ meta, onChange, onBack, onGenerate, generating }: Props) {
  const set = (key: keyof Meta) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...meta, [key]: e.target.value });

  const canGenerate = meta.position.trim() && meta.company.trim();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Job Details</h2>
        <p className="text-sm text-slate-500">
          Used for file naming and Notion tracking. Required fields are marked with *.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Position" required>
          <input
            type="text"
            value={meta.position}
            onChange={set("position")}
            placeholder="e.g. Senior UX Designer"
            className={inputClass}
          />
        </Field>

        <Field label="Company" required>
          <input
            type="text"
            value={meta.company}
            onChange={set("company")}
            placeholder="e.g. Acme Corp"
            className={inputClass}
          />
        </Field>

        <Field label="Location">
          <input
            type="text"
            value={meta.location}
            onChange={set("location")}
            placeholder="e.g. Calgary, AB (Hybrid)"
            className={inputClass}
          />
        </Field>

        <Field label="Date of Job Posting">
          <input
            type="date"
            value={meta.date_job_posted}
            onChange={set("date_job_posted")}
            className={inputClass}
          />
        </Field>

        <Field label="Salary (Annual)">
          <input
            type="number"
            value={meta.salary_annual}
            onChange={set("salary_annual")}
            placeholder="e.g. 85000"
            className={inputClass}
          />
        </Field>

        <Field label="Salary (Hourly)">
          <input
            type="number"
            value={meta.salary_hourly}
            onChange={set("salary_hourly")}
            placeholder="e.g. 42.50"
            step="0.01"
            className={inputClass}
          />
        </Field>

        <Field label="Contact Email (optional)">
          <input
            type="email"
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
