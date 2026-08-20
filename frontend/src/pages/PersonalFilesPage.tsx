import { MarkdownFileEditor } from "../components/MarkdownFileEditor";
import type { ModelFilesStatus } from "../types";

const PERSONAL_FILE_IDS = [
  "design_resume",
  "dev_resume",
  "instructions_prompt",
  "school_transcript",
  "writing_examples",
] as const;

interface Props {
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (status: ModelFilesStatus) => void;
}

export function PersonalFilesPage({ onDirtyChange, onSaved }: Props) {
  return (
    <section className="editor-page" aria-labelledby="personal-files-heading">
      <div className="editor-page-heading">
        <p className="editor-eyebrow">Private source material</p>
        <h2 id="personal-files-heading">Edit personal files</h2>
        <p>
          Keep the facts, experience, and voice used to tailor each application accurate. These
          files stay in the local, gitignored personal directory.
        </p>
      </div>
      <MarkdownFileEditor
        group="personal"
        allowedFileIds={PERSONAL_FILE_IDS}
        onDirtyChange={onDirtyChange}
        onPersonalSave={onSaved}
      />
    </section>
  );
}
