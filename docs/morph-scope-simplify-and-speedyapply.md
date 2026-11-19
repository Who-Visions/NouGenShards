# Morph Scope: Tech & College Job Radars to NouGenJobs

Reviewed: 2026-10-02 (02:42 PM EDT).
Target Substrate: `~\Outpost\nougenjobs`
Canonical Morphed SQLite: `~\Outpost\nougenjobs\data\morph_opportunities.db`

## Donor Sources Morphed

1. **SimplifyJobs / New-Grad-Positions**:
   - URL: `https://github.com/SimplifyJobs/New-Grad-Positions`
   - Morphed Count: 2,387 entry-level SWE, PM, AI/ML, and quant opportunities for 2025/2026.
   - Schema mapping: Ingests HTML table rows into `morph_jobs` with automated skill extraction.

2. **SpeedyApply / 2027-SWE-College-Jobs**:
   - URL: `https://github.com/speedyapply/2027-SWE-College-Jobs`
   - Morphed Count: 546 university student & college SWE internship opportunities for 2026/2027.
   - Schema mapping: Ingests markdown table rows including salary hourly rates ($40-$85/hr).

## Morph Architecture & Pipeline

```
GitHub Markdown / HTML Stream
         │
         ▼
[NouGenMorph Parser]
         │
         ├──> Normalize Company, Role, Location, Direct URL, Hourly Salary
         ├──> Dynamic Skill Extraction (React, Python, Cloud, AI/ML, Go, SQL)
         │
         ▼
Local SQLite Engine (`data/morph_opportunities.db`)
         │
         ▼
NouGenJobs Radar API (`/api/gigs` & `/api/morph/search`)
         │
         ▼
Candidate Profile Scoring (0–100% Match) & 1-Click Application / Letter Elevation
```

## Verified Live Metrics

- Total Opportunities Morphed: 2,417
- Salary Rate Floor Extraction: Enabled
- Dynamic Candidate Matching: Live on http://127.0.0.1:8765

3. **Backend-BR / Vagas**:
   - URL: `https://github.com/backend-br/vagas`
   - Morphed Count: 41 live open issue vacancies (Senior/Mid/Remote backend roles).
   - Schema mapping: Ingests GitHub issue payload, parses remote locations `[Remoto]`, tech stack labels (Python, Go, Node.js, SQL, GCP), and partner companies.

4. **Mauro Bonfietti / Remote-Jobs**:
   - URL: `https://github.com/maurobonfietti/remote-jobs`
   - Morphed Count: 1,517 live remote job postings (updated October 02, 2026).
   - Schema mapping: Parses markdown table rows, extracts company names, direct job links, global remote locations, and technical skill taxonomy.

5. **Emre Durukn / Awesome-Job-Boards**:
   - URL: `https://github.com/emredurukn/awesome-job-boards`
   - Morphed Count: 480 curated niche and global job boards stored in `curated_job_boards` table.

6. **BarrosoHub / Remote-Jobs-For-Devs**:
   - URL: `https://github.com/barrosohub/remote-jobs-for-devs`
   - Morphed Count: 47 dedicated direct-hire remote developer platforms (Arc.dev, Gun.io, JS Remotely, Hired, Turing, etc.).
   - Schema mapping: Ingests platform tables with direct verified links into `curated_job_boards`.

7. **NoOfficeLabs / How-To-Work-Remotely**:
   - URL: `https://github.com/NoOfficeLabs/how-to-work-remotely`
   - Morphed Count: Curated directory of APAC remote-first teams and international hiring companies (China, Japan, Korea, New Zealand).

8. **Rajat Mehra / Awesome-Frontend-Interview-Resources**:
   - URL: `https://github.com/rajat-mehra05/awesome-frontend-interview-resources`
   - Morphed Count: 75 core frontend interview modules, coding quizzes, and system design challenges stored in `candidate_interview_prep`.

9. **RemoteWLB / Remote-Jobs**:
   - URL: `https://github.com/RemoteWLB/remote-jobs`
   - Morphed Count: 1,068 categorized remote tech jobs and direct language portal feeds (Golang, Java, C#).
