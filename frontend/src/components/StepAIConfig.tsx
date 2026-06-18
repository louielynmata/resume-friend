import type { AIProvider, JobType } from "../types";

interface Props {
  aiProvider: AIProvider;
  jobType: JobType;
  onChangeProvider: (v: AIProvider) => void;
  onChangeJobType: (v: JobType) => void;
  onBack: () => void;
  onNext: () => void;
}

const AI_OPTIONS: { value: AIProvider; label: string; description: string }[] = [
  { value: "claude", label: "Claude (Anthropic)", description: "Requires ANTHROPIC_API_KEY in .env" },
  { value: "openai", label: "ChatGPT (OpenAI)", description: "Requires OPENAI_API_KEY in .env" },
  { value: "ollama", label: "Ollama (Local)", description: "Runs locally — no API key needed" },
];

const JOB_TYPES: { value: JobType; label: string; description: string }[] = [
  { value: "design", label: "Design / UX", description: "Loads your Design resume template" },
  { value: "development", label: "Development / Engineering", description: "Loads your Developer resume template" },
];

export function StepAIConfig({ aiProvider, jobType, onChangeProvider, onChangeJobType, onBack, onNext }: Props) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800 mb-1">AI Model & Job Type</h2>
        <p className="text-sm text-slate-500">Choose which AI to use and what kind of role you're applying for.</p>
      </div>

      {/* AI Provider */}
      <div>
        <p className="text-sm font-medium text-slate-700 mb-2">AI Provider</p>
        <div className="space-y-2">
          {AI_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                aiProvider === opt.value
                  ? "border-indigo-500 bg-indigo-50"
                  : "border-slate-200 bg-white hover:bg-slate-50"
              }`}
            >
              <input
                type="radio"
                name="ai_provider"
                value={opt.value}
                checked={aiProvider === opt.value}
                onChange={() => onChangeProvider(opt.value)}
                className="mt-0.5 accent-indigo-600"
              />
              <div>
                <p className="text-sm font-medium text-slate-800">{opt.label}</p>
                <p className="text-xs text-slate-500">{opt.description}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Job Type */}
      <div>
        <p className="text-sm font-medium text-slate-700 mb-2">Job Type</p>
        <div className="space-y-2">
          {JOB_TYPES.map((opt) => (
            <label
              key={opt.value}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                jobType === opt.value
                  ? "border-indigo-500 bg-indigo-50"
                  : "border-slate-200 bg-white hover:bg-slate-50"
              }`}
            >
              <input
                type="radio"
                name="job_type"
                value={opt.value}
                checked={jobType === opt.value}
                onChange={() => onChangeJobType(opt.value)}
                className="mt-0.5 accent-indigo-600"
              />
              <div>
                <p className="text-sm font-medium text-slate-800">{opt.label}</p>
                <p className="text-xs text-slate-500">{opt.description}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={onBack} className="px-6 py-2 text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50">
          ← Back
        </button>
        <button onClick={onNext} className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700">
          Next →
        </button>
      </div>
    </div>
  );
}
