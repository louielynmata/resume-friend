import { MarkdownFileEditor } from "../components/MarkdownFileEditor";

const PROMPT_FILE_IDS = ["system_prompt", "qa_prompt", "visual_qa_prompt"] as const;

interface Props {
  onDirtyChange: (dirty: boolean) => void;
}

export function PromptsPage({ onDirtyChange }: Props) {
  return (
    <section className="editor-page" aria-labelledby="prompts-heading">
      <div className="editor-page-heading">
        <p className="editor-eyebrow">Application behavior</p>
        <h2 id="prompts-heading">Edit prompts</h2>
        <p>
          Adjust how Resume Friend writes and reviews documents. Prompt changes can materially
          affect generation and QA, so review them before saving.
        </p>
      </div>
      <MarkdownFileEditor
        group="prompts"
        allowedFileIds={PROMPT_FILE_IDS}
        onDirtyChange={onDirtyChange}
      />
    </section>
  );
}
