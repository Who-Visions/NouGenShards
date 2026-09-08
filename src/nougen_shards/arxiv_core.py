"""Autonomous arXiv paper search, digest & ingestion module.

Enables agents and operators to:
1. Search arXiv API by query/topic
2. Ingest papers into NouGenShards with Matryoshka embeddings and content hash (sha:...)
3. Generate daily topic digests
"""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Optional

ARXIV_API_URL = "http://export.arxiv.org/api/query"


def search_arxiv(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Query arXiv API and return structured paper metadata."""
    encoded_query = urllib.parse.quote(query)
    url = f"{ARXIV_API_URL}?search_query=all:{encoded_query}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "NouGen-Arxiv-Client/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        xml_data = resp.read().decode("utf-8")

    root = ET.fromstring(xml_data)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    papers = []
    for entry in root.findall("atom:entry", ns):
        id_text = entry.find("atom:id", ns).text or ""
        title = (entry.find("atom:title", ns).text or "").strip().replace("\n", " ")
        summary = (entry.find("atom:summary", ns).text or "").strip().replace("\n", " ")
        published = entry.find("atom:published", ns).text or ""
        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns) if a.find("atom:name", ns) is not None]

        # Extract clean arXiv ID
        arxiv_id = id_text.split("/abs/")[-1] if "/abs/" in id_text else id_text

        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "summary": summary,
            "published": published,
            "authors": authors,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        })

    return papers


def ingest_paper_to_shard(paper: dict[str, Any], vault_dir: Optional[str] = None) -> dict[str, Any]:
    """Ingest arXiv paper metadata into NouGenShards substrate."""
    from nougen_shards import core as shards

    content = f"# {paper['title']}\n\n**Authors**: {', '.join(paper['authors'])}\n**Published**: {paper['published']}\n**arXiv ID**: {paper['arxiv_id']}\n**URL**: {paper['url']}\n\n## Abstract\n{paper['summary']}"
    tags = ["arxiv", f"arxiv:{paper['arxiv_id']}", "research", "paper"]

    result = shards.capture(
        title=f"arXiv: {paper['title']}",
        content=content,
        tags=tags,
        vault_dir=vault_dir
    )
    return {
        "status": "success",
        "shard_id": result.get("id"),
        "db": result.get("db_index"),
        "file_hash": result.get("file_hash"),
        "title": paper["title"]
    }
