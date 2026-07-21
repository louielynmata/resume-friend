import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api/client";
import { StepJobInput } from "./components/StepJobInput";
import { StepAIConfig } from "./components/StepAIConfig";
import { StepJobMeta } from "./components/StepJobMeta";
import { StepResult } from "./components/StepResult";
import type {
  AIProvider,
  GenerateResult,
  GenerationFeedItem,
  GenerationStageId,
  JobMeta,
  JobType,
  ModelFilesStatus,
} from "./types";

const MODEL_FILE_LABELS: Record<keyof ModelFilesStatus, string> = {
  design_resume: "design_resume.md",
  dev_resume: "dev_resume.md",
  instructions_prompt: "instructions_prompt.md",
  writing_examples: "writing_examples.md",
  school_transcript: "school_transcript.md",
};

const STEPS = ["Job Description", "AI & Job Type", "Details", "Result"];

const DEFAULT_META: JobMeta = {
  position: "",
  company: "",
  location: "",
  salary_annual: "",
  salary_hourly: "",
  date_job_posted: "",
  contact_email: "",
};

const DEFAULT_META_TOUCHED: Record<keyof JobMeta, boolean> = {
  position: false,
  company: false,
  location: false,
  salary_annual: false,
  salary_hourly: false,
  date_job_posted: false,
  contact_email: false,
};

const GENERATION_STAGES: Array<
  Pick<GenerationFeedItem, "id" | "label" | "description">
> = [
  {
    id: "validate_request",
    label: "Validate Request",
    description: "Check required fields and generation settings.",
  },
  {
    id: "load_model_files",
    label: "Load Model Files",
    description: "Load your resume, prompt instructions, and writing samples.",
  },
  {
    id: "call_ai_provider",
    label: "Call AI Provider",
    description: "Send the prompt to Claude, OpenAI, or Ollama.",
  },
  {
    id: "qa_review",
    label: "Review and Fix",
    description: "Run an independent grammar, truthfulness, and format review.",
  },
  {
    id: "build_documents",
    label: "Build Documents",
    description:
      "Parse the AI output and create the resume and cover letter files.",
  },
  {
    id: "artifact_validation",
    label: "Validate Files",
    description: "Inspect the rendered DOCX/PDF files and repair blocking issues.",
  },
  {
    id: "log_notion",
    label: "Log to Notion",
    description: "Attempt tracking in Notion if it is configured.",
  },
  {
    id: "complete",
    label: "Complete",
    description: "Finalize output paths and return the result.",
  },
];

function buildGenerationFeed(
  activeStage?: GenerationStageId,
): GenerationFeedItem[] {
  return GENERATION_STAGES.map((stage) => ({
    ...stage,
    status: stage.id === activeStage ? "active" : "pending",
  }));
}

export default function App() {
  const [step, setStep] = useState(0);
  const [jd, setJd] = useState("");
  const [companyContext, setCompanyContext] = useState("");
  const [aiProvider, setAiProvider] = useState<AIProvider>("claude");
  const [jobType, setJobType] = useState<JobType>("development");
  const [meta, setMeta] = useState<JobMeta>(DEFAULT_META);
  const [metaTouched, setMetaTouched] =
    useState<Record<keyof JobMeta, boolean>>(DEFAULT_META_TOUCHED);
  const [generating, setGenerating] = useState(false);
  const [extractingMeta, setExtractingMeta] = useState(false);
  const [error, setError] = useState("");
  const [errorCode, setErrorCode] = useState("");
  const [errorStatus, setErrorStatus] = useState<number | undefined>(undefined);
  const [errorHint, setErrorHint] = useState("");
  const [generationFeed, setGenerationFeed] = useState<GenerationFeedItem[]>(
    [],
  );
  const [result, setResult] = useState<GenerateResult | null>(null);
  const generationIntervalRef = useRef<number | null>(null);
  const [modelFilesStatus, setModelFilesStatus] = useState<ModelFilesStatus | null>(null);
  const [modelFilesChecked, setModelFilesChecked] = useState(false);
  const [modelFilesBannerDismissed, setModelFilesBannerDismissed] = useState(false);

  function stopGenerationTicker() {
    if (generationIntervalRef.current !== null) {
      window.clearInterval(generationIntervalRef.current);
      generationIntervalRef.current = null;
    }
  }

  function startGenerationTicker() {
    stopGenerationTicker();
    const stageIds = GENERATION_STAGES.map((stage) => stage.id);
    let index = 0;

    setGenerationFeed(buildGenerationFeed(stageIds[index]));

    generationIntervalRef.current = window.setInterval(() => {
      index = Math.min(index + 1, stageIds.length - 2);
      setGenerationFeed((current) => {
        const hasTerminalState = current.some(
          (item) => item.status === "failed" || item.status === "done",
        );
        return hasTerminalState
          ? current
          : buildGenerationFeed(stageIds[index]);
      });
    }, 1400);
  }

  function markGenerationFailed(
    stage: GenerationStageId | undefined,
    detail: string,
  ) {
    setGenerationFeed((current) => {
      const fallback = current.length > 0 ? current : buildGenerationFeed();
      return fallback.map((item) => {
        if (stage && item.id === stage) {
          return { ...item, status: "failed", detail };
        }
        if (!stage && item.status === "active") {
          return { ...item, status: "failed", detail };
        }
        if (stage) {
          const stageIndex = GENERATION_STAGES.findIndex(
            (entry) => entry.id === stage,
          );
          const itemIndex = GENERATION_STAGES.findIndex(
            (entry) => entry.id === item.id,
          );
          if (itemIndex < stageIndex) return { ...item, status: "done" };
          if (itemIndex > stageIndex && item.status !== "failed")
            return { ...item, status: "pending" };
        }
        return item;
      });
    });
  }

  function markGenerationComplete() {
    setGenerationFeed(
      GENERATION_STAGES.map((stage) => ({
        ...stage,
        status: "done",
      })),
    );
  }

  useEffect(() => () => stopGenerationTicker(), []);

  useEffect(() => {
    api.modelFiles()
      .then(setModelFilesStatus)
      .catch(() => setModelFilesStatus(null))
      .finally(() => setModelFilesChecked(true));
  }, []);

  function handleMetaChange(next: JobMeta) {
    setMetaTouched((currentTouched) => {
      const nextTouched = { ...currentTouched };
      (Object.keys(next) as Array<keyof JobMeta>).forEach((key) => {
        if (next[key] !== meta[key]) nextTouched[key] = true;
      });
      return nextTouched;
    });
    setMeta(next);
  }

  async function prefillJobMeta() {
    if (!jd.trim()) return;
    setExtractingMeta(true);
    try {
      const extracted = await api.extractJobMeta(jd);
      setMeta((current) => {
        const pick = (key: keyof JobMeta, incoming: string) =>
          metaTouched[key] ? current[key] : incoming;

        return {
          position: pick(
            "position",
            extracted.position || current.position || "",
          ),
          company: pick("company", extracted.company || current.company || ""),
          location: pick(
            "location",
            extracted.location || current.location || "",
          ),
          salary_annual: pick(
            "salary_annual",
            extracted.salary_annual != null
              ? String(extracted.salary_annual)
              : current.salary_annual || "",
          ),
          salary_hourly: pick(
            "salary_hourly",
            extracted.salary_hourly != null
              ? String(extracted.salary_hourly)
              : current.salary_hourly || "",
          ),
          date_job_posted: pick(
            "date_job_posted",
            extracted.date_job_posted || current.date_job_posted || "",
          ),
          contact_email: pick(
            "contact_email",
            extracted.contact_email || current.contact_email || "",
          ),
        };
      });
    } catch {
      // Extraction is best-effort and should never block generation.
    } finally {
      setExtractingMeta(false);
    }
  }

  async function handleOpenJobMetaStep() {
    setStep(2);
    await prefillJobMeta();
  }

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    setErrorCode("");
    setErrorStatus(undefined);
    setErrorHint("");
    startGenerationTicker();
    try {
      const res = await api.generate({
        job_description: jd,
        ai_provider: aiProvider,
        job_type: jobType,
        position: meta.position,
        company: meta.company,
        location: meta.location || undefined,
        salary_annual: meta.salary_annual
          ? Number.parseFloat(meta.salary_annual)
          : undefined,
        salary_hourly: meta.salary_hourly
          ? Number.parseFloat(meta.salary_hourly)
          : undefined,
        date_job_posted: meta.date_job_posted || undefined,
        contact_email: meta.contact_email || undefined,
        company_context: companyContext || undefined,
      });
      stopGenerationTicker();
      markGenerationComplete();
      setResult(res);
      setStep(3);
    } catch (e: unknown) {
      stopGenerationTicker();
      if (e instanceof ApiError) {
        const message = e.payload.message || e.payload.detail || e.message;
        const detail = e.payload.detail
          ? `${message} ${e.payload.detail}`
          : message;
        setError(message);
        setErrorCode(e.payload.code || "");
        setErrorStatus(e.status);
        setErrorHint(e.payload.hint || "");
        markGenerationFailed(e.payload.stage, detail);
      } else {
        const message =
          e instanceof Error
            ? e.message
            : "Generation failed. Check backend logs.";
        setError(message);
        setErrorStatus(undefined);
        setErrorCode("");
        setErrorHint("");
        markGenerationFailed(undefined, message);
      }
    } finally {
      setGenerating(false);
    }
  }

  function handleReset() {
    setStep(0);
    setJd("");
    setCompanyContext("");
    setMeta(DEFAULT_META);
    setMetaTouched(DEFAULT_META_TOUCHED);
    setResult(null);
    setError("");
    setErrorCode("");
    setErrorStatus(undefined);
    setErrorHint("");
    setGenerationFeed([]);
    stopGenerationTicker();
  }

  const missingFiles = modelFilesStatus
    ? (Object.keys(modelFilesStatus) as Array<keyof ModelFilesStatus>)
        .filter((key) => !modelFilesStatus[key])
        .map((key) => MODEL_FILE_LABELS[key])
    : null;

  const showSetupBanner =
    modelFilesChecked &&
    !modelFilesBannerDismissed &&
    (modelFilesStatus === null || (missingFiles && missingFiles.length > 0));

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-900">Resume Friend</h1>
            <p className="text-xs text-slate-400">
              AI-powered resume & cover letter generator
            </p>
          </div>
          <span className="text-xs text-slate-400 bg-slate-100 px-2 py-1 rounded">
            Local
          </span>
        </div>
      </header>

      {/* Model files setup banner */}
      {showSetupBanner && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-3">
          <div className="max-w-2xl mx-auto flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-amber-800">Setup required — model files not found</p>
              {modelFilesStatus === null ? (
                <p className="text-xs text-amber-700 mt-0.5">
                  The <code className="font-mono">models_personal/</code> directory is missing. Copy{" "}
                  <code className="font-mono">models_personal_example/</code> to{" "}
                  <code className="font-mono">models_personal/</code> and fill in your resume and writing samples.
                </p>
              ) : (
                <p className="text-xs text-amber-700 mt-0.5">
                  Missing: <span className="font-mono">{missingFiles!.join(", ")}</span>. Copy the matching files
                  from <code className="font-mono">models_personal_example/</code> and fill in your content.
                </p>
              )}
            </div>
            <button
              onClick={() => setModelFilesBannerDismissed(true)}
              className="text-amber-600 hover:text-amber-900 text-lg leading-none shrink-0 mt-0.5"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        </div>
      )}

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
                <div
                  className={`flex items-center gap-1.5 text-xs font-medium transition-colors ${textColor}`}
                >
                  <span
                    className={`w-5 h-5 rounded-full flex items-center justify-center text-xs shrink-0 ${circleColor}`}
                  >
                    {isDone ? "✓" : i + 1}
                  </span>
                  <span className="hidden sm:inline">{label}</span>
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={`flex-1 h-px mx-1 ${isDone ? "bg-green-300" : "bg-slate-200"}`}
                  />
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
            <StepJobInput
              value={jd}
              onChange={setJd}
              companyContext={companyContext}
              onCompanyContextChange={setCompanyContext}
              onNext={() => setStep(1)}
            />
          )}
          {step === 1 && (
            <StepAIConfig
              aiProvider={aiProvider}
              jobType={jobType}
              onChangeProvider={setAiProvider}
              onChangeJobType={setJobType}
              onBack={() => setStep(0)}
              onNext={handleOpenJobMetaStep}
            />
          )}
          {step === 2 && (
            <StepJobMeta
              meta={meta}
              onChange={handleMetaChange}
              onBack={() => setStep(1)}
              onGenerate={handleGenerate}
              generating={generating}
              extracting={extractingMeta}
              generationFeed={generationFeed}
              generationErrorCode={errorCode}
              generationErrorStatus={errorStatus}
              generationErrorHint={errorHint}
            />
          )}
          {step === 3 && result && (
            <StepResult result={result} onReset={handleReset} />
          )}
        </div>
      </main>

      <footer className="text-center text-xs text-slate-400 py-4">
        Resume Friend — use Ollama for fully local generation
        <br />
        Resume Friend contributors © {new Date().getFullYear()}
      </footer>
    </div>
  );
}
