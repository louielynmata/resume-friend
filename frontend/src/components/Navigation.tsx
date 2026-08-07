import { hashForPage, type AppPage } from "../utils/app-routing";

interface Props {
  activePage: AppPage;
  onNavigate: (page: AppPage) => boolean;
}

const destinations: Array<{ page: AppPage; label: string }> = [
  { page: "generate", label: "Generate" },
  { page: "personal", label: "Edit Personal Files" },
  { page: "prompts", label: "Edit Prompts" },
];

export function Navigation({ activePage, onNavigate }: Props) {
  return (
    <nav aria-label="Primary" className="app-tabs">
      {destinations.map(({ page, label }) => (
        <a
          key={page}
          href={hashForPage(page)}
          aria-current={activePage === page ? "page" : undefined}
          onClick={(event) => {
            if (!onNavigate(page)) event.preventDefault();
          }}
          className="app-tab"
        >
          {label}
        </a>
      ))}
    </nav>
  );
}
