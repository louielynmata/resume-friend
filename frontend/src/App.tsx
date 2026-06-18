import { useState } from "react";
import { api } from "./api/client";
import { StepJobInput } from "./components/StepJobInput";
import { StepAIConfig } from "./components/StepAIConfig";
import { StepJobMeta } from "./components/StepJobMeta";
import { StepResult } from "./components/StepResult";
import type { AIProvider, JobType, GenerateResult } from "./types";

const STEPS = ["Job Description", "AI & Job Type", "Details", "Result"];

interface Meta {
  position: string;
  company: string;
  location: string;
  salary_annual: string;
  salary_hourly: string;
  date_job_posted: string;
  contact_email: string;
}

const DEFAULT_META: Meta = {
  position: "",
  company: "",
  location: "",
  salary_annual: "",
  salary_hourly: "",
  date_job_posted: "",
  contact_email: "",
};

export default function App() {
  const [step, setStep] = useState(0);
  const [jd, setJd] = useState("");
  const [aiProvider, setAiProvider] = useState<AIProvider>("claude");
  const [jobType, setJobType] = useState<JobType>("development");
  const [meta, setMeta] = useState<Meta>(DEFAULT_META);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<GenerateResult | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const res = await api.generate({
        job_description: jd,
        ai_provider: aiProvider,
        job_type: jobType,
        position: meta.position,
        company: meta.company,
        location: meta.location || undefined,
        salary_annual: meta.salary_annual ? Number.parseFloat(meta.salary_annual) : undefined,
        salary_hourly: meta.salary_hourly ? Number.parseFloat(meta.salary_hourly) : undefined,
        date_job_posted: meta.date_job_posted || undefined,
        contact_email: meta.contact_email || undefined,
      });
      setResult(res);
      setStep(3);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed. Check backend logs.");
    } finally {
      setGenerating(false);
    }
  }

  function handleReset() {
    setStep(0);
    setJd("");
    setMeta(DEFAULT_META);
    setResult(null);
    setError("");
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-900">Resume Friend</h1>
            <p className="text-xs text-slate-400">AI-powered resume & cover letter generator</p>
          </div>
          <span className="text-xs text-slate-400 bg-slate-100 px-2 py-1 rounded">Local</span>
        </div>
      </header>

      {/* Step indicator */}
      <div className="bg-white border-b border-slate-200 px-6 py-3">
        <div className="max-w-2xl mx-auto flex gap-1">
          {STEPS.map((label, i) => {
            const isActive = i === step;
            const isDone = i < step;
            let textColor = "text-slate-400";
            if (isActive) textColor = "text-indigo-600";
            else if (isDone) textColor = "text-green-600";
            let circleColor = "bg-slate-200 text-slate-500";
            if (isActive) circleColor = "bg-indigo-600 text-white";
            else if (isDone) circleColor = "bg-green-500 text-white";
            return (
              <div key={label} className="flex items-center gap-1 flex-1">
                <div className={`flex items-center gap-1.5 text-xs font-medium transition-colors ${textColor}`}>
                  <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs shrink-0 ${circleColor}`}>
                    {isDone ? "✓" : i + 1}
                  </span>
                  <span className="hidden sm:inline">{label}</span>
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`flex-1 h-px mx-1 ${isDone ? "bg-green-300" : "bg-slate-200"}`} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 px-6 py-8">
        <div className="max-w-2xl mx-auto bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <strong>Error:</strong> {error}
            </div>
          )}

          {step === 0 && (
            <StepJobInput value={jd} onChange={setJd} onNext={() => setStep(1)} />
          )}
          {step === 1 && (
            <StepAIConfig
              aiProvider={aiProvider}
              jobType={jobType}
              onChangeProvider={setAiProvider}
              onChangeJobType={setJobType}
              onBack={() => setStep(0)}
              onNext={() => setStep(2)}
            />
          )}
          {step === 2 && (
            <StepJobMeta
              meta={meta}
              onChange={setMeta}
              onBack={() => setStep(1)}
              onGenerate={handleGenerate}
              generating={generating}
            />
          )}
          {step === 3 && result && (
            <StepResult result={result} onReset={handleReset} />
          )}
        </div>
      </main>

      <footer className="text-center text-xs text-slate-400 py-4">
        Resume Friend — local only · no data leaves your machine
      </footer>
    </div>
  );
}
