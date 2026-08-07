import type { EditorFileMetadata, EditorGroup } from "../types";

interface Props {
  group: EditorGroup;
  files: EditorFileMetadata[];
  selectedId: string;
  disabled: boolean;
  onSelect: (fileId: string) => void;
}

export function MarkdownFileTabs({
  group,
  files,
  selectedId,
  disabled,
  onSelect,
}: Props) {
  const groupLabel = group === "personal" ? "Personal" : "Prompt";

  return (
    <div className="editor-file-navigation">
      <span className="editor-label">Markdown files</span>
      <div
        className="editor-file-tabs"
        role="tablist"
        aria-label={`${groupLabel} Markdown files`}
      >
        {files.length === 0 ? (
          <span className="editor-tabs-loading">Loading file list…</span>
        ) : (
          files.map((file) => {
            const active = file.file_id === selectedId;
            return (
              <button
                key={file.file_id}
                type="button"
                id={`${group}-file-tab-${file.file_id}`}
                role="tab"
                aria-selected={active}
                aria-controls={`${group}-markdown-panel`}
                disabled={disabled}
                className={`editor-file-tab${active ? " is-active" : ""}`}
                onClick={() => onSelect(file.file_id)}
              >
                <span className="editor-file-tab-name">{file.display_name}</span>
                <span className="editor-file-tab-filename">{file.filename}</span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
