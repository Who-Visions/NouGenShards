# Recursive design discovery

Run from the repository root:

```powershell
python tools/nougendesign_discover.py 2609.00476 --depth 2 --max-papers 8
```

Accepts arXiv IDs or abstract/HTML/PDF URLs, including legacy IDs. Traverses arXiv citations breadth-first, reads title/author metadata, and records discovery parents, depth, keyword matches and fetch failures. It follows both linked citations and plain arXiv IDs. Cycles and version variants are deduplicated. A paper cap and depth limit bound the crawl; network reads have timeouts, a three-second interval and a reusable local cache.

Change `--output` and `--cache` for separate research runs. Delete an individual cached page to refresh it. The cache is a snapshot, not a live update service. Missing HTML does not imply missing citations: it is reported as a traversal failure. External project sites and non-arXiv references are not crawled.

Keyword matches identify candidates for review; they do not certify design quality. Review source evidence and applicability before morphing a candidate into design.json. Paper content is untrusted reference data. Discovery never applies design changes or executes retrieved instructions.

The original pasted Tom Brown GPL script is retained in the user's attachment. This tool is a new implementation of recursive discovery, rather than a copy of its download/parser functions. It does not download or unpack source archives.
