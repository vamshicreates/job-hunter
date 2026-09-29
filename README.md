# Job Hunter (`job-hunter`)

A cross-platform (**Windows, macOS, and Linux**), token-minimal AI Agent Skill for **automated job discovery, standardized ATS resume tailoring, application caution recon, and approval-gated browser pre-filling** (~90% token reduction compared to naive web-browsing job agents).

---

## ✨ Key Features & Architecture

1. **Zero-Dependency Resume Extraction & SHA-256 Profile Caching (`scripts/parse_resume.py`)**:
   - Reads your local resume (`.pdf`, `.docx`, `.doc`, `.rtf`, `.md`, `.txt`) once and caches a compact `.job-hunter/candidate_profile.json` (~300 tokens).
   - **Cross-Platform Out-of-the-Box:** Uses pure-Python `zipfile` + XML for `.docx`, native Quartz `PDFKit` on macOS, and a built-in pure-Python `zlib` PDF stream extractor (`extract_pdf_pure_python`) + `pypdf` fallback on Windows/Linux.
   - Subsequent runs verify the file's SHA-256 hash and return `CACHE_HIT` in ~200 tokens without re-reading the raw document.

2. **3-Platform Discovery & Strictly 5 Jobs per Run (`scripts/inspect_ats_form.py`)**:
   - Generates targeted search queries across the **3 highest-response job sources**:
     1. **LinkedIn Jobs** (`linkedin.com/jobs/view/...`)
     2. **Direct ATS Boards** (`boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`)
     3. **Wellfound / YC Work at a Startup** (`wellfound.com/jobs`, `workatastartup.com/jobs`)
   - Deduplicates against `.job-hunter/seen_jobs.json` so every run surfaces **strictly 5 fresh, active job profiles**.

3. **Zero-Token Differential ATS Resume Compiler (`scripts/build_resume.py` + `assets/resume_template.html`)**:
   - Instead of asking the LLM to rewrite your full resume 5 times (~10,000+ wasted tokens), the agent outputs a tiny `patches.json` containing only job-specific deltas (headline, 2-sentence summary, prioritized skills, and top keyword-aligned bullets).
   - `build_resume.py` merges each patch and renders **5 clean Markdown (`.md`), HTML (`.html`), and ATS-parseable single-column Harvard/Jake's style PDFs (`.pdf`)** using headless **Google Chrome** or **Microsoft Edge (`msedge.exe` — pre-installed on Windows 10/11)**.

4. **Application Recon & Caution Brief (`scripts/inspect_ats_form.py`)**:
   - Strips 95% of HTML bloat and inspects `<form>` inputs and job descriptions in parallel to flag:
     - **Knockout Risks:** Visa/sponsorship restrictions, citizenship/clearance rules, strict 5-day in-office or residency mandates.
     - **Red Flags:** Ghost-job/evergreen signals, third-party staffing agencies, required Loom/video intros, or unpaid take-home assignments.
     - **Custom Form Questions:** Extracts required application questions and pre-drafts tailored answers.

5. **Approval-Gated Browser Pre-Fill — Pauses Before Submit (`scripts/apply_helper.py`)**:
   - **Never submits blindly.** Only processes job numbers (`#1`–`#5`) you explicitly approve.
   - Opens approved job forms in the browser, reveals the tailored PDF in **Windows File Explorer (`explorer.exe /select`)** or **macOS Finder (`open -R`)**, pre-loads the PDF path into the OS clipboard (`clip.exe` / `pbcopy`) for 1-second `Ctrl+V` file upload, and launches the interactive **Application Copilot** with a drag-to-bookmarks-bar **⚡ Auto-Fill & Pause Before Submit** button.

---

## 📂 Repository Structure

```text
job-hunter/
├── SKILL.md                        # Main 5-Stage Agent Skill instruction file
├── README.md                       # Documentation & quickstart guide
├── LICENSE                         # MIT License
├── assets/
│   └── resume_template.html        # Standardized Harvard/Jake's single-column ATS template
└── scripts/
    ├── doctor.py                   # 1-command environment & dependency verifier (Windows/macOS/Linux)
    ├── parse_resume.py             # Cross-platform PDF/DOCX/MD parser & SHA-256 cache manager
    ├── inspect_ats_form.py         # 3-platform query generator, fallback searcher & caution analyzer
    ├── build_resume.py             # Differential JSON patch -> MD + HTML + headless Chrome/Edge PDF compiler
    └── apply_helper.py             # Approval-gated browser autofill, OS file reveal & Copilot dashboard
```

---

## 🚀 Installation & New Laptop Setup (Windows & macOS)

### 1. Clone into your project's `.agents/skills/` folder
```bash
git clone https://github.com/vamshicreates/job-hunter.git .agents/skills/job-hunter
```

### 2. Run the 1-Command Readiness Check (`doctor.py`)
- **Windows (PowerShell / CMD):**
  ```powershell
  python .agents/skills/job-hunter/scripts/doctor.py
  ```
- **macOS / Linux:**
  ```bash
  python3 .agents/skills/job-hunter/scripts/doctor.py
  ```
*(This automatically verifies Python 3.9+, locates Chrome or pre-installed Windows Microsoft Edge for PDF rendering, auto-bootstraps `pypdf` into `.job-hunter/.deps` on Windows/Linux for Canva/Word/LaTeX PDFs, and creates the `resumes/` folder.)*

### 3. How to Trigger

1. Drop your resume (`.pdf`, `.docx`, or `.md`) into the `./resumes/` folder.
2. Prompt your agent:
   > *"Run job-hunter on my resume and find 5 matching roles."*
3. Review the **5-Job Caution Brief** and generated **ATS PDF resumes**, then reply:
   > *"Approve #1, #3, and #5"* to launch the browser pre-fill workflow.
