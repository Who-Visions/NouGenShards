# Morph Scope: SpeedyApply / JobSpy to NouGenJobs

Reviewed: 2026-10-02 (02:43 PM EDT).
Source Repository: `https://github.com/speedyapply/JobSpy`
Canonical Target: `C:\Users\super\Outpost\nougenjobs`
Status: Architecture Morphed & Native Ingestion Bridge Designed.

## Observed Donor Capabilities

| Donor Feature | JobSpy Implementation | NouGenJobs Native Morph |
|---|---|---|
| **Multi-Board Aggregation** | Scrapes LinkedIn, Indeed, Glassdoor, ZipRecruiter concurrently (`concurrent.futures.ThreadPoolExecutor`) | Dynamic radar feeder with zero-browser overhead (`app/jobspy_feeder.py`) |
| **Normalized Job Model** | `JobPost` dataclass (title, company_name, job_url, location, compensation, skills, is_remote) | Directly maps into `app.domain.normalize_job` and `data/morph_opportunities.db` |
| **Salary Normalization** | Parses hourly vs annual into unified min/max amounts (`extract_salary`, `convert_to_annual`) | Auto-populates candidate pay floor checking (`match_opportunity_against_candidate`) |
| **Direct Application URLs** | Extracts `job_url_direct` bypassing third-party redirects | Feeds 1-click application & tailored cover letter generation in Resume Studio |

## Integration Pipeline

```
[SpeedyApply JobSpy Engine]
       │
       ├── LinkedIn, Indeed, ZipRecruiter, Glassdoor API/HTML
       │
       ▼
[NouGenMorph Normalizer]
       │
       ├── Map to Job schema: title, company, location, compensation, direct_url
       ├── Extract hard skills & taxonomy
       │
       ▼
[Local SQLite Radar (`morph_opportunities.db`)]
       │
       ▼
Live Dynamic Matching against Candidate Profiles on http://127.0.0.1:8765
```
