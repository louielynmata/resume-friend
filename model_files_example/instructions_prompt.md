(instructions_prompt.md)

Create a tailored 1-page resume and a tailored cover letter for the target role.

The output must stay truthful to the provided source resume. Do not invent experience, tools, responsibilities, metrics, awards, or education details.

I want the resume to mirror the exact visual structure and formatting style of my PDF resumes, adapted into a clean ATS-friendly single-column format. No columns, tables, text boxes, icons, or decorative characters that may break parsing.

---

HEADER BLOCK FORMATTING:

Render the header in this exact sequence:

  LOUIELYN MATA
  ────────────────────────────────────────────────────────────────
  [PRIMARY ROLE TITLE IN ALL CAPS AND BOLD — line 2]
  [Optional secondary tagline — regular case, line 3 only if it adds positioning value]
  louielynmata@gmail.com | +1 825 558 0107  Calgary, AB
  LinkedIn: http://www.linkedin.com/in/louielynmata/  Github: http://github.com/louielynmata

Rules:
- The horizontal rule (---) goes DIRECTLY UNDER THE NAME LINE — not after the contact block.
- Name is on its own line, ALL CAPS.
- Primary role title is ALL CAPS on the next line, immediately after the rule.
- Contact info and links follow below the title lines. All header lines are centered.
- For design roles only, add this line last: DESIGNER PORTFOLIO LINK  https://drive.google.com/drive/folders/1FKDM7u_vB0jY8S5zofdT4a4ziH7MD-g4?usp=sharing
  CRITICAL: Copy this URL character-for-character — including the underscore in "1FKDM7u_vB0jY8S5". Do NOT alter, shorten, or reformat the URL in any way.
- After the last header line (links or portfolio), leave one blank line before the body begins.
- Do NOT add another horizontal rule between the header and PROFESSIONAL SUMMARY.

---

HORIZONTAL RULE PLACEMENT:

Horizontal rules (---) appear only in these positions:
1. Directly under the name in the header (see above).
2. BETWEEN major section groups — placed before the next section header, not after the current one.

Sections that are part of the same group share a block with no rule between them. Examples:
- CERTIFICATIONS and ACHIEVEMENTS flow together without a rule between them.
- DESIGN & PRODUCT SKILLS, CREATIVE LEADERSHIP & STRATEGY, and BUSINESS & CLIENT MANAGEMENT flow together as one skills group (no rules between them).
- A rule appears before TOOLKIT (after the skills group ends).
- A rule appears before WORK EXPERIENCES (after ACHIEVEMENTS ends).
- On the software engineering resume, a rule appears between every major named section (after PROFESSIONAL SUMMARY, after TOOLKIT AND TECHNICAL SKILLS, after EDUCATIONAL ATTAINMENT, after PROJECTS, before RELATED WORK EXPERIENCES, before CERTIFICATIONS).

When in doubt: use a rule before any section that starts a new thematic group. Never put a rule directly after a section header label.

---

SECTION HEADER FORMATTING:

- Section headers are ALL CAPS, bold, left-aligned.
- Content starts on the very next line after the section header — no blank line between the header label and its content. Only a blank line before the next entry within the section.
- Do NOT add a horizontal rule or underline directly below a section header.
- Use these exact section names (match the role type):

  For design / creative roles:
  PROFESSIONAL SUMMARY
  DESIGN & PRODUCT SKILLS
  CREATIVE LEADERSHIP & STRATEGY
  BUSINESS & CLIENT MANAGEMENT
  TOOLKIT
  WORK EXPERIENCES
  EDUCATIONAL ATTAINMENT
  CERTIFICATIONS
  ACHIEVEMENTS

  For software engineering / development roles:
  PROFESSIONAL SUMMARY
  TOOLKIT and TECHNICAL SKILLS
  EDUCATIONAL ATTAINMENT
  PROJECTS
  RELATED WORK EXPERIENCES
  OTHER EXPERIENCES
  CERTIFICATIONS
  ACHIEVEMENTS

---

PROFESSIONAL SUMMARY RULES:

- Prose paragraph only — no bullets.
- 3 to 5 sentences maximum.
- Lead with the most relevant positioning for this specific role.
- Do not start with "I" as the first word — open with a role descriptor.
- Preserve my voice: direct, thoughtful, confident, grounded, human — not corporate.
- Avoid all generic filler: "results-driven", "dynamic team player", "passionate self-starter", and similar phrases.
- No em dashes.

---

TOOLKIT / SKILLS SECTION FORMATTING:

For SOFTWARE ENGINEERING roles — format each skill category like this:

  **Languages** - Javascript, Typescript, Python, Java, C++, HTML5

  **Database** - PostgreSQL, Google Firestore, NoSQL, MySQL, Redis

  **Frameworks** - Node.JS, React, Next.JS, NestJS, Vite, Django, React Native, Expo, Prisma ORM, Firebase, Wordpress CMS, .NET Maui

  **Styling** - Design Systems, Tailwind, CSS, Bootstrap

  **Testing** Unit tests - Jest, Vitest, Django Test Suite
  E2E tests - Playwright, Storybook

  **UI/UX, DevOps, and Tools** - Figma, Github (Version & CI), Docker, AWS, Azure, Google Cloud Platform, Vercel, Railway, Swagger OpenAPI, SonarQube, Postman, ESLint, Datadog, Nginx, Gunicorn, JWT, Auth, VS Code, PyCharm and IntelliJ, Linux, MacOS, Analytic Tools, Notion, Jira

  **AI Tools** - ChatGPT and Codex, Github Copilot, Claude Code, Cursor IDE, MCP, Stable Diffusion, Ollama

  **Business and Design Tools** - Adobe Creative Suite, Blender (3D), Google's G Suites, Microsoft Office.

  **Currently Learning:** Go, Terraform, React Native - Native features, Maestro

Rules:
- Bold category label and the values are on THE SAME LINE — not the label on its own line followed by a new line.
- One blank line between each category.
- Values wrap naturally to the next line if long — that is fine.
- Only include categories relevant to the target role. Trim or omit low-relevance categories.

For DESIGN roles — TOOLKIT uses bold sub-category labels on their own lines, with values listed below each (not inline). Example:

  **Design & Multimedia Tools**
  Adobe Creative Suite (Photoshop, Illustrator, Premiere Pro, After Effects, Audition, XD)
  Blender (3D)
  Figma

  **Collaboration & Business Tools**
  Google Workspace
  Microsoft Office
  Notion, Jira, Trello
  Miro and Figjam

  **Digital & Web Exposure**
  HTML5, CSS3, JavaScript, TypeScript
  React, Next.js, React Native
  Node.js, Django REST Framework
  REST APIs, JWT Auth
  WordPress CMS
  Responsive & Design Systems
  Vite, Tailwind CSS, Bootstrap
  Cloud & Deployment (Vercel, Railway, AWS, Azure, Google Cloud Platform)

Rules:
- Sub-category label is bold and on its own line.
- Values listed below it, one tool or tool group per line.
- One blank line between each sub-category group.

---

WORK EXPERIENCE ENTRY FORMATTING — TWO PATTERNS:

Pattern A — Role leads (use when the role title or position is the primary point of interest):

  ROLE TITLE IN ALL CAPS
  **Company Name** - Context or date descriptor / Start Date - End Date

  ● Bullet with **bold key phrase** and impact
  ● Bullet
  ● Bullet

Example:
  SOFTWARE ENGINEERING INTERN
  **Newton Crypto Canada** - Summer 2025 Co-op / May 2025 - Aug 2025

Pattern B — Company leads (use when the company name is the primary point of interest, or when multiple roles at the same company are listed):

  **Company Name,** (industry descriptor in parentheses)
  ROLE TITLE - Start Date – End Date (employment type)
  SECOND ROLE TITLE - Start Date – End Date (employment type)

  ● Bullet with **bold key phrase** and impact
  ● Bullet
  ● Bullet

Example:
  **Ant Savvy Creatives & Entertainment Inc.,** (360 Entertainment & Advertising Agency)
  CREATIVE DIRECTOR - April 2021 – Oct 2024 (Fulltime) Oct 2024 - 2025 (Present Freelance)
  SENIOR ART DIRECTOR - April 2017 – April 2018 (Fulltime) 2019 - 2020 (Freelance)

General rules for work entries:
- Role titles are ALL CAPS — this is the primary visual weight, not bold separately.
- Company names are bold.
- Dates are on the same line as the role or company — compact and inline.
- One blank line between separate job entries.
- Notable Clients or Notable Clients & Works is a bold sub-label (not a section header) followed by bullet items. Only include if it materially helps the application.
- No blank line between the section header (e.g., RELATED WORK EXPERIENCES) and the first job entry beneath it.

---

EDUCATION ENTRY FORMATTING:

Format:

  EDUCATIONAL ATTAINMENT
  Institution Name                                                Year – Year
  Degree or Program (note: Graduated with Honors / GPA if relevant)

  Institution Name
  Degree or Program (note: Graduated with Honors / GPA)

Rules:
- Section header: EDUCATIONAL ATTAINMENT (exact name).
- Institution name left-aligned; year right-aligned or placed at the far end of the same line.
- Degree/program on the next line, directly under the institution name (no extra indent needed).
- Blank line between each education entry.
- On the design resume format, the year goes on the LEFT with the school/degree indented to the right.

---

PROJECTS SECTION FORMATTING (dev roles only):

  **Project Name** - Client or Context (duration)
  Brief description as 1–3 line prose. Mention tech stack, scope, and outcome.

  **Project Name** - Description
  ...

Rules:
- Project name is bold, followed by a dash and context/client on the same line.
- Description is prose, not bullets.
- One blank line between project entries.
- No blank line between section header PROJECTS and the first entry.

---

BULLET RULES:

- Use ● for all bullets.
- Bold key phrases, metrics, and standout terms inline — not the entire bullet.
- Start each bullet with a strong action verb.
- Keep bullets tight: 1 line preferred, 2 lines max.
- Lead with impact, scale, ownership, or outcome.
- Include metrics only from source material — do not invent.
- Reorder bullets so the most relevant to the target role appears first.
- No repeated ideas across bullets.

---

LAYOUT RULES:

- 1 page target. Only exceed if the role genuinely requires it.
- Single vertical flow — no columns, no sidebars, no tables.
- If content must be cut, remove lower-priority or less-relevant items first rather than compressing everything.
- Avoid dense paragraph blocks anywhere except the PROFESSIONAL SUMMARY.

---

ATS SAFETY RULES:

- No columns, tables, sidebars, graphics, icons.
- Bullet character ● only — no other special symbols.
- No fake ratings or progress bars.
- No critical info in headers/footers only.

---

COVER LETTER FORMATTING AND RULES:

Structure:

  Cover Letter

  **To the [Hiring Team / Hiring Manager Name],**

  [Opening paragraph — specific, not generic]

  [Body paragraph — 2 to 3 concrete examples from my background matching the role]

  [Closing paragraph — why this company or team, forward-looking]

  Cheers and all the best!


  Sincerely and thankfully,
  **Louielyn Mata**
  louielynmata@gmail.com
  http://www.linkedin.com/in/louielynmata

Rules:
- "Cover Letter" is the document heading — bold, left-aligned.
- Greeting "To the [Team]," is bold.
- 3 to 4 short paragraphs total.
- Do NOT open with "I am excited to apply for...", "I am writing to express my interest...", or any generic opener.
- Sound like I am writing to a real person — warm, direct, sincere.
- Be specific about why this company, role, or product matters to me.
- Preserve warmth and confidence without sounding needy.
- Sign-off is always "Cheers and all the best!" — this is my signature sign-off.
- Closing is always "Sincerely and thankfully," followed by my name bold, email, and LinkedIn.
- Cover letter must fit on ONE PAGE. Keep every paragraph to 3–5 sentences maximum.
- Do NOT add blank lines between body paragraphs. Write them one after another — the document renderer handles spacing.

---

FINAL QUALITY BAR:

- The output must feel like content was intentionally arranged, not poured into a template.
- The name in ALL CAPS, the single rule under the name, the section headers in ALL CAPS, the bold key phrases in bullets, and the horizontal rules between major section groups are non-negotiable style markers — preserve them in every output.
- It should look clean, deliberate, and structured while remaining fully ATS-friendly.
- Tone must always sound like me: direct, thoughtful, confident, human, and not corporate.
