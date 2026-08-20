import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import { MarkdownFileTabs } from "./MarkdownFileTabs";
import type {
  EditorFileMetadata,
  EditorFileResult,
  EditorGroup,
  ModelFilesStatus,
} from "../types";

interface Props {
  group: EditorGroup;
  allowedFileIds: readonly string[];
  onDirtyChange: (dirty: boolean) => void;
  onPersonalSave?: (status: ModelFilesStatus) => void;
}

function sourceLabel(file: EditorFileResult): string {
  if (file.source === "example") return "Example fallback · save creates your personal file";
  if (file.source === "personal") return "Private personal file";
  return "Public application prompt";
}

export function MarkdownFileEditor({
  group,
  allowedFileIds,
  onDirtyChange,
  onPersonalSave,
}: Props) {
  const [files, setFiles] = useState<EditorFileMetadata[]>([]);
  const [selectedId, setSelectedId] = useState(allowedFileIds[0] ?? "");
  const [document, setDocument] = useState<EditorFileResult | null>(null);
  const [content, setContent] = useState("");
  const [baseline, setBaseline] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingFile, setLoadingFile] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [feedbackKind, setFeedbackKind] = useState<"status" | "error">("status");
  const feedbackRef = useRef<HTMLDivElement>(null);

  const dirty = document !== null && content !== baseline;
  const allowed = useMemo(() => new Set(allowedFileIds), [allowedFileIds]);

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    let active = true;
    api
      .editorFiles()
      .then((result) => {
        if (!active) return;
        const groupFiles = result.groups[group].filter((file) => allowed.has(file.file_id));
        setFiles(groupFiles);
        setSelectedId((current) =>
          groupFiles.some((file) => file.file_id === current)
            ? current
            : (groupFiles[0]?.file_id ?? ""),
        );
      })
      .catch((error: unknown) => {
        if (!active) return;
        setFeedbackKind("error");
        setFeedback(error instanceof Error ? error.message : "Could not list Markdown files.");
      })
      .finally(() => active && setLoadingList(false));
    return () => {
      active = false;
    };
  }, [allowed, group]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    api
      .editorFile(group, selectedId)
      .then((loaded) => {
        if (!active) return;
        setDocument(loaded);
        setContent(loaded.content);
        setBaseline(loaded.content);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setDocument(null);
        setContent("");
        setBaseline("");
        setFeedbackKind("error");
        setFeedback(error instanceof Error ? error.message : "Could not load the Markdown file.");
      })
      .finally(() => active && setLoadingFile(false));
    return () => {
      active = false;
    };
  }, [group, selectedId]);

  useEffect(() => {
    if (feedback && feedbackKind === "error") feedbackRef.current?.focus();
  }, [feedback, feedbackKind]);

  function selectFile(nextId: string) {
    if (nextId === selectedId) return;
    if (dirty && !window.confirm("Discard unsaved changes and open another file?")) return;
    setLoadingFile(true);
    setFeedback("");
    setSelectedId(nextId);
  }

  function resetChanges() {
    setContent(baseline);
    setFeedbackKind("status");
    setFeedback("Unsaved changes reset.");
  }

  async function saveChanges() {
    if (!document || !dirty || saving) return;
    setSaving(true);
    setFeedback("");
    try {
      const saved = await api.saveEditorFile(group, document.file_id, content, document.revision);
      setDocument(saved);
      setContent(saved.content);
      setBaseline(saved.content);
      setFeedbackKind("status");
      setFeedback(`${saved.filename} saved.`);
      if (group === "personal") onPersonalSave?.(saved.personal_file_status);
    } catch (error: unknown) {
      setFeedbackKind("error");
      if (error instanceof ApiError && error.status === 409) {
        setFeedback("This file changed outside Resume Friend. Reload it before saving your edits.");
      } else {
        setFeedback(error instanceof Error ? error.message : "Could not save the Markdown file.");
      }
    } finally {
      setSaving(false);
    }
  }

  const busy = loadingList || loadingFile || saving;
  const activeTabId = files.some((file) => file.file_id === selectedId)
    ? `${group}-file-tab-${selectedId}`
    : undefined;

  return (
    <div className="editor-dossier">
      <div className="editor-toolbar">
        <MarkdownFileTabs
          group={group}
          files={files}
          selectedId={selectedId}
          disabled={loadingList || saving}
          onSelect={selectFile}
        />
        <div className="editor-status-stack" aria-live="polite">
          <span className={`editor-state ${dirty ? "is-dirty" : ""}`}>
            {dirty ? "Unsaved changes" : "Up to date"}
          </span>
          {document && <span className="editor-source">{sourceLabel(document)}</span>}
        </div>
      </div>

      <div
        id={`${group}-markdown-panel`}
        role="tabpanel"
        aria-labelledby={activeTabId}
        aria-busy={loadingFile}
        className="editor-tab-panel"
      >
        {document?.source === "example" && (
          <div className="editor-fallback-note" role="note">
            Your personal file is missing. This example is an editable starting point; Save changes
            creates <code>models_personal/{document.filename}</code> and leaves the example untouched.
          </div>
        )}

        <label htmlFor={`${group}-markdown-content`} className="sr-only">
          Markdown content for {document?.display_name ?? "selected file"}
        </label>
        <textarea
          id={`${group}-markdown-content`}
          value={content}
          onChange={(event) => setContent(event.target.value)}
          disabled={loadingFile || !document || saving}
          spellCheck
          className="markdown-sheet"
          placeholder={loadingFile ? "Loading Markdown…" : "This file is empty. Start writing here."}
        />

        <div className="editor-actions">
          <div
            ref={feedbackRef}
            tabIndex={-1}
            role={feedbackKind === "error" ? "alert" : "status"}
            className={feedbackKind === "error" ? "editor-feedback is-error" : "editor-feedback"}
          >
            {feedback || (busy ? "Working…" : "")}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={resetChanges}
              disabled={!dirty || busy}
              className="editor-button secondary"
            >
              Reset changes
            </button>
            <button
              type="button"
              onClick={saveChanges}
              disabled={!dirty || busy}
              className="editor-button primary"
            >
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
