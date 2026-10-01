"""Bounded arXiv citation discovery for NouGenDesigns (stdlib only).

Original implementation inspired by the user's single-reference arXiv CLI.
Paper text is reference data, never executable instructions.
"""
import argparse
import collections
import datetime
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ID = re.compile(r'(?:\d{4}\.\d{4,5}|[a-zA-Z][\w.-]+/\d{7})(?:v\d+)?')
TOPICS = ('design', 'negative space', 'visual', 'composition', 'layout', 'typography', 'interface', 'interaction', 'infographic', 'vector', 'perception', 'accessibility', 'chart', 'graphic')


def reference(value):
    value = re.sub(r'^https?://(?:export\.)?arxiv\.org/(?:abs|html|pdf)/', '', value.strip())
    value = re.sub(r'^arxiv:', '', value, flags=re.I).removesuffix('.pdf')
    if not ID.fullmatch(value):
        raise ValueError(f'Invalid arXiv reference: {value}')
    return re.sub(r'v\d+$', '', value)


class PaperParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}; self.links = []; self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name', '').startswith('citation_'):
            self.meta.setdefault(attrs['name'], []).append(attrs.get('content', ''))
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])

    def handle_data(self, data):
        self.text.append(data)


def citations(html):
    parser = PaperParser(); parser.feed(html)
    found = []
    for link in parser.links:
        if re.match(r'https?://(?:export\.)?arxiv\.org/(?:abs|html|pdf)/', link):
            try:
                item = reference(link)
                if item not in found: found.append(item)
            except ValueError: pass
    for match in re.finditer(r'arXiv:\s*(' + ID.pattern + r')', ' '.join(parser.text), re.I):
        item = reference(match.group(1))
        if item not in found: found.append(item)
    return found


class Fetcher:
    def __init__(self, cache, delay=3):
        self.cache = Path(cache); self.cache.mkdir(parents=True, exist_ok=True)
        self.delay = delay; self.last = 0

    def __call__(self, ref, kind):
        path = self.cache / (ref.replace('/', '_') + '-' + kind + '.html')
        if path.exists(): return path.read_text(encoding='utf-8')
        time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        request = urllib.request.Request(f'https://arxiv.org/{kind}/{ref}', headers={'User-Agent': 'NouGenDesignDiscovery/0.1 (bounded research crawler)'})
        with urllib.request.urlopen(request, timeout=25) as response:
            html = response.read(8 * 1024 * 1024).decode('utf-8')
        path.write_text(html, encoding='utf-8'); return html


def discover(seeds, fetch, depth=1, max_papers=8):
    queue = collections.deque((reference(s), 0, None) for s in seeds)
    seen = set(); records = []
    while queue and len(records) < max_papers:
        ref, level, parent = queue.popleft()
        if ref in seen: continue
        seen.add(ref)
        row = {'id': ref, 'url': f'https://arxiv.org/abs/{ref}', 'depth': level, 'discovered_from': parent}
        try:
            html = fetch(ref, 'abs'); parser = PaperParser(); parser.feed(html)
            title = parser.meta.get('citation_title', [''])[0]
            row.update(title=title, authors=parser.meta.get('citation_author', []), matched_topics=[t for t in TOPICS if t in title.lower()], status='metadata_read')
            if level < depth:
                try:
                    links = citations(fetch(ref, 'html'))
                    row['references'] = [c for c in links if c != ref]
                    queue.extend((c, level + 1, ref) for c in links if c not in seen)
                except Exception as exc: row['reference_error'] = str(exc)
        except Exception as exc: row.update(status='unavailable', error=str(exc))
        records.append(row)
    return {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'seeds': seeds, 'depth_limit': depth, 'paper_limit': max_papers, 'pending_references': len(queue), 'papers': records}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('seeds', nargs='+'); cli.add_argument('--depth', type=int, choices=range(4), default=1)
    cli.add_argument('--max-papers', type=int, default=8); cli.add_argument('--cache', default='.cache/design-discovery')
    cli.add_argument('--output', default='designs/discovery.json')
    args = cli.parse_args()
    if not 1 <= args.max_papers <= 100: cli.error('--max-papers must be 1..100')
    result = discover(args.seeds, Fetcher(args.cache), args.depth, args.max_papers)
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'{len(result["papers"])} papers; {sum(p["status"] == "unavailable" for p in result["papers"])} unavailable; {path}')


if __name__ == '__main__': main()
