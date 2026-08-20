export function Footer() {
  return (
    <footer className="px-6 py-5 text-center text-xs leading-5 text-slate-500">
      <p>Resume Friend · use Ollama for fully local generation</p>
      <p>
        Resume Friend by{" "}
        <a
          href="https://louielyn.com"
          target="_blank"
          rel="noopener noreferrer"
          className="underline transition-colors hover:text-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
        >
          Louielyn Mata
        </a>{" "}
        © {new Date().getFullYear()}
      </p>
    </footer>
  );
}
