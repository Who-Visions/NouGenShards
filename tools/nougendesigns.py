"""NouGenDesigns v0: evidence-bearing design package compiler and gates.

No network, inference or source mutations occur during compilation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

SECTIONS = ('referenceWorld antiPatterns materiality density motionGrammar '
            'interactionPhysics informationHierarchy responsiveBehavior accessibility '
            'brandVoice iconography dataViz stateGrammar provenance').split()
RULES = {
    'gradient': r'(?:linear|radial|conic)-gradient\(',
    'glass': r'(?:-webkit-)?backdrop-filter\s*:\s*blur\(',
    'pill': r'border-radius\s*:\s*(?:999\d*px|50%)',
    'glow': r'box-shadow\s*:\s*0\s+0\s+[1-9]\d*px',
}
SOURCE_SUFFIXES = {'.css', '.html', '.ts', '.tsx'}
EXCLUDED_DIRS = {'.git', 'node_modules', 'dist', 'build', '.next', 'coverage', 'out', 'target'}

def canonical(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n'

def validate(spec):
    errors = []
    if not isinstance(spec, dict):
        return ['specification must be an object']
    if spec.get('dialect') != 'nougendesigns/v0':
        errors.append('dialect must be nougendesigns/v0')
    for key in ['name', 'version', 'description', *SECTIONS]:
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            errors.append(f'{key}: non-empty prose required')
    tokens = spec.get('tokens', {})
    if not isinstance(tokens, dict) or len(tokens) < 26:
        errors.append('tokens: at least 26 declarations required')
        tokens = tokens if isinstance(tokens, dict) else {}
    for key, value in tokens.items():
        if not re.fullmatch(r'--[a-z][a-z0-9-]*', key):
            errors.append(f'invalid token name: {key}')
        if not isinstance(value, str) or not value or re.search(r'[;{}\n\r]', value):
            errors.append(f'invalid token value: {key}')
    for theme, values in spec.get('themes', {}).items():
        if theme not in ('light', 'dark') or not isinstance(values, dict):
            errors.append(f'invalid theme: {theme}')
            continue
        for key, value in values.items():
            if key not in tokens or not isinstance(value, str) or re.search(r'[;{}\n\r]', value):
                errors.append(f'invalid theme token: {theme}/{key}')
    evidence = spec.get('evidence', [])
    if not evidence:
        errors.append('evidence: source records required')
    for item in evidence:
        if not isinstance(item, dict) or item.get('kind') not in ('observed', 'inferred', 'invented') or not item.get('source'):
            errors.append('evidence requires kind and source')
    if not spec.get('contrastPairs'):
        errors.append('contrastPairs required')
    return errors

def declarations(tokens):
    return '\n'.join(f'  {key}: {value};' for key, value in sorted(tokens.items()))

def render(spec):
    errors = validate(spec)
    if errors:
        raise ValueError('\n'.join(errors))
    prose = ('---\n' + '\n'.join(f'{key}: {json.dumps(spec[key])}' for key in ('name', 'version', 'description'))
             + '\ncolors: ' + json.dumps({k: v for k, v in spec['tokens'].items() if re.fullmatch(r'#[0-9a-fA-F]{6}', v)})
             + '\n---\n\n# ' + spec['name'] + '\n\n')
    prose += '\n\n'.join(f'## {"Accessibility" if key == "accessibility" else key}\n\n{spec[key]}' for key in SECTIONS) + '\n'
    css = ':root {\n' + declarations(spec['tokens']) + '\n}\n'
    for theme, values in sorted(spec.get('themes', {}).items()):
        css += f':root[data-theme="{theme}"] {{\n{declarations(values)}\n}}\n'
    css += '\n:where(a, button, input, select, textarea, [tabindex]):focus-visible {\n  outline: 2px solid var(--focus);\n  outline-offset: 3px;\n}\n'
    css += '@media (prefers-reduced-motion: reduce) {\n  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }\n}\n'
    manifest = {'schemaVersion': 'od-design-system-project/v1', 'dialect': spec['dialect'],
                'name': spec['name'], 'version': spec['version'], 'description': spec['description'],
                'entry': {'prose': 'DESIGN.md', 'tokens': 'tokens.css'},
                'surfaces': {'ground': '--bg', 'ink': '--text'},
                'themes': sorted(spec.get('themes', {})), 'provenance': spec['evidence'],
                'sourceDigest': hashlib.sha256(canonical(spec).encode()).hexdigest()}
    return {'DESIGN.md': prose, 'tokens.css': css, 'manifest.json': canonical(manifest),
            'mutations.json': canonical(spec.get('componentMutations', []))}

def contrast(a, b):
    def lum(color):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('contrast colors must be six-digit hex')
        values = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return sum(v * w for v, w in zip(values, (.2126, .7152, .0722)))
    x, y = sorted((lum(a), lum(b)))
    return (y + .05) / (x + .05)

def lint(spec, css=''):
    errors = validate(spec)
    ratios = []
    for theme in ['default', *sorted(spec.get('themes', {}))]:
        tokens = {**spec.get('tokens', {}), **spec.get('themes', {}).get(theme, {})}
        for pair in spec.get('contrastPairs', []):
            try:
                ratio = contrast(tokens[pair['ink']], tokens[pair['ground']])
                floor = 3 if pair.get('role') == 'ui' else 4.5
                ratios.append({'theme': theme, **pair, 'ratio': round(ratio, 3)})
                if ratio < floor:
                    errors.append(f'{theme}: {pair["ink"]}/{pair["ground"]} below {floor}:1')
            except (KeyError, ValueError) as exc:
                errors.append(f'contrast pair invalid: {exc}')
    clean = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    for name, pattern in RULES.items():
        for match in re.finditer(pattern, clean, re.I):
            errors.append(f'anti-slop {name}: line {clean.count(chr(10), 0, match.start()) + 1}')
    if css and ':focus-visible' not in css:
        errors.append('visible keyboard focus missing')
    if css and 'prefers-reduced-motion' not in css:
        errors.append('reduced-motion policy missing')
    return {'passed': not errors, 'errors': errors, 'contrast': ratios}

def inspect_source(path):
    path = Path(path)
    files = (sorted(file for file in path.rglob('*')
                    if file.is_file() and file.suffix.lower() in SOURCE_SUFFIXES
                    and not any(part in EXCLUDED_DIRS for part in file.relative_to(path).parts))
             if path.is_dir() else [path])
    records = []
    for file in files:
        data = file.read_bytes()
        suffix = file.suffix.lower()
        record = {'source': file.name if path.is_file() else file.relative_to(path).as_posix(),
                  'kind': 'observed', 'sha256': hashlib.sha256(data).hexdigest(), 'extension': suffix}
        if suffix in SOURCE_SUFFIXES:
            text = data.decode('utf-8')
            if suffix == '.css':
                clean = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
                record['tokens'] = dict(re.findall(r'(--[\w-]+)\s*:\s*([^;{}]+);', clean))
                record['antiPatterns'] = {key: len(re.findall(pattern, clean, re.I)) for key, pattern in RULES.items()}
                record['hasFocusVisible'] = ':focus-visible' in clean
                record['hasReducedMotion'] = 'prefers-reduced-motion' in clean
            elif suffix in ('.ts', '.tsx'):
                record['components'] = sorted(set(re.findall(
                    r'(?:function|class|const)\s+([A-Z][A-Za-z0-9_]*)', text)))
                record['elements'] = {tag: len(re.findall(r'<\s*' + tag + r'(?=[\s/>])', text, re.I))
                                      for tag in ('button', 'a', 'input', 'select', 'textarea', 'form', 'h1', 'h2', 'h3')}
                record['ariaAttributes'] = len(re.findall(r'\baria-[\w-]+\s*=', text))
                record['inlineStyleAttributes'] = len(re.findall(r'\bstyle\s*=', text))
            else:
                record['elements'] = {tag: len(re.findall(r'<\s*' + tag + r'(?=[\s/>])', text, re.I))
                                      for tag in ('button', 'a', 'input', 'form', 'h1', 'h2', 'h3')}
        else:
            record['note'] = 'Binary reference registered; visual interpretation must be supplied as inferred prose.'
        records.append(record)
    return records

def analyze_inputs(source, brief, spec):
    """Measure a repository and preserve a brief as an input, without inference or mutation."""
    source = Path(source)
    brief = Path(brief)
    if not source.exists() or not brief.is_file():
        raise ValueError('source and brief must exist')
    brief_text = brief.read_text(encoding='utf-8').strip()
    if not brief_text or len(brief_text) > 20000:
        raise ValueError('brief must contain 1 to 20000 characters')
    records = inspect_source(source)
    if not records:
        raise ValueError('source contains no supported CSS, HTML, TS or TSX files')

    tokens = {}
    css_parts = []
    recommendations = []
    for record in records:
        if record.get('extension') == '.css':
            css_path = source / record['source'] if source.is_dir() else source
            css_parts.append(css_path.read_text(encoding='utf-8'))
            for name, value in record.get('tokens', {}).items():
                tokens.setdefault(name, []).append({'value': value.strip(), 'source': record['source']})
            for rule, count in record.get('antiPatterns', {}).items():
                if count:
                    recommendations.append({'id': 'review-' + rule, 'finding': rule, 'count': count,
                        'sources': [record['source']], 'guidance': 'Review the measured occurrences against the design brief; the compiler does not rewrite source CSS.'})
            if not record.get('hasFocusVisible'):
                recommendations.append({'id': 'add-visible-focus-' + record['source'], 'finding': 'missing-visible-focus',
                    'count': 1, 'sources': [record['source']], 'guidance': 'Add a visible :focus-visible treatment and verify it against the focus token.'})
            if not record.get('hasReducedMotion'):
                recommendations.append({'id': 'add-reduced-motion-' + record['source'], 'finding': 'missing-reduced-motion-policy',
                    'count': 1, 'sources': [record['source']], 'guidance': 'Add a prefers-reduced-motion policy for nonessential motion.'})

    brief_bytes = brief.read_bytes()
    spec_bytes = canonical(spec).encode('utf-8')
    analysis = {
        'schemaVersion': 'nougendesigns-analysis/v1',
        'mode': 'deterministic-review-draft',
        'inputs': {
            'source': source.name if source.is_dir() else source.name,
            'sourceDigest': hashlib.sha256(canonical(records).encode('utf-8')).hexdigest(),
            'brief': brief.name,
            'briefDigest': hashlib.sha256(brief_bytes).hexdigest(),
            'profile': spec.get('name', 'unnamed'),
            'profileDigest': hashlib.sha256(spec_bytes).hexdigest(),
        },
        'summary': {
            'sourceFiles': len(records),
            'cssFiles': sum(record.get('extension') == '.css' for record in records),
            'componentFiles': sum(record.get('extension') in ('.ts', '.tsx') for record in records),
            'tokenNames': len(tokens),
            'antiPatternOccurrences': {rule: sum(record.get('antiPatterns', {}).get(rule, 0) for record in records)
                                       for rule in RULES},
        },
        'brief': brief_text,
        'tokenCandidates': {name: sorted(values, key=lambda item: (item['source'], item['value']))
                            for name, values in sorted(tokens.items())},
        'sourceEvidence': records,
        'reviewGuidance': recommendations,
        'limitations': [
            'The brief is preserved verbatim; it is not interpreted or used to invent design decisions.',
            'CSS and component evidence is static and deterministic; screenshots are only hashed, never visually interpreted.',
            'No source files are changed. Review the draft and guidance before adopting them.',
        ],
    }
    css = '\n'.join(css_parts)
    report = lint(spec, css)
    files = render(spec)
    brief_quote = '\n'.join('> ' + line for line in brief_text.splitlines())
    guidance = '\n'.join(f"- `{item['finding']}` ({item['count']}; {', '.join(item['sources'])}): {item['guidance']}"
                         for item in recommendations) or '- No static review guidance was triggered.'
    files['DESIGN.md'] += (
        '\n\n## Repository analysis draft\n\n'
        'This section combines the reviewed profile above with measured source evidence. '
        'The brief is preserved verbatim; no visual intent is inferred by this deterministic pass.\n\n'
        '### Design brief (verbatim)\n\n' + brief_quote + '\n\n'
        '### Measured source\n\n'
        f"- Files: {analysis['summary']['sourceFiles']} ({analysis['summary']['cssFiles']} CSS; "
        f"{analysis['summary']['componentFiles']} TS/TSX).\n"
        f"- Distinct CSS custom-property names: {analysis['summary']['tokenNames']}.\n"
        f"- Source digest: `{analysis['inputs']['sourceDigest']}`.\n\n"
        '### Review before adoption\n\n' + guidance + '\n'
    )
    mutations = list(spec.get('componentMutations', []))
    mutations.extend({'selector': '*', 'change': f"Review measured {item['finding']} in {', '.join(item['sources'])}: {item['guidance']}"}
                     for item in recommendations)
    files['mutations.json'] = canonical(mutations)
    manifest = json.loads(files['manifest.json'])
    manifest['analysisInputs'] = {key: analysis['inputs'][key] for key in ('sourceDigest', 'briefDigest', 'profileDigest')}
    files['manifest.json'] = canonical(manifest)
    files['analysis.json'] = canonical(analysis)
    files['lint.json'] = canonical(report)
    return files, report, analysis

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('compile', 'lint', 'check'):
        p = sub.add_parser(command)
        p.add_argument('spec', type=Path)
        if command in ('compile', 'check'):
            p.add_argument('output', type=Path)
        else:
            p.add_argument('--css', type=Path)
    p = sub.add_parser('inspect'); p.add_argument('source', type=Path)
    p = sub.add_parser('analyze', help='build a deterministic review draft from source, brief and a reviewed profile')
    p.add_argument('source', type=Path); p.add_argument('brief', type=Path)
    p.add_argument('spec', type=Path); p.add_argument('output', type=Path)
    p = sub.add_parser('diff'); p.add_argument('before', type=Path); p.add_argument('after', type=Path)
    p = sub.add_parser('discover', help='find bounded arXiv design candidates; does not mutate a design package')
    p.add_argument('seeds', nargs='+')
    p.add_argument('--depth', type=int, choices=range(4), default=1)
    p.add_argument('--max-papers', type=int, default=8)
    p.add_argument('--cache', type=Path, default=Path('.cache/design-discovery'))
    p.add_argument('--output', type=Path, default=Path('designs/discovery.json'))
    args = parser.parse_args()
    if args.command == 'discover':
        from nougendesign_discover import discover, Fetcher
        if not 1 <= args.max_papers <= 100:
            raise ValueError('max-papers must be 1..100')
        result = discover(args.seeds, Fetcher(args.cache), args.depth, args.max_papers)
        result['adoption'] = 'candidate references only; review full source and applicability before editing design.json'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(canonical(result), encoding='utf-8')
        print(canonical({'papers': len(result['papers']), 'output': str(args.output), 'designMutated': False}))
        return 0

    if args.command == 'inspect':
        print(canonical(inspect_source(args.source))); return 0
    if args.command == 'analyze':
        spec = json.loads(args.spec.read_text(encoding='utf-8'))
        files, report, analysis = analyze_inputs(args.source, args.brief, spec)
        output = args.output.resolve()
        source = args.source.resolve()
        protected_inputs = {source, args.brief.resolve(), args.spec.resolve()}
        if ((args.source.is_dir() and (output == source or source in output.parents))
                or any((output / name).resolve() in protected_inputs for name in files)):
            raise ValueError('output must be outside the source tree')
        args.output.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (args.output / name).write_text(body, encoding='utf-8', newline='\n')
        print(canonical({'passed': report['passed'], 'sourceFiles': analysis['summary']['sourceFiles'],
                         'artifacts': sorted(files), 'lintErrors': report['errors']}))
        return int(not report['passed'])
    if args.command == 'diff':
        a, b = [json.loads(p.read_text()) for p in (args.before, args.after)]
        print(canonical({k: {'before': a.get(k), 'after': b.get(k)} for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k)})); return 0
    spec = json.loads(args.spec.read_text(encoding='utf-8'))
    if args.command == 'lint':
        result = lint(spec, args.css.read_text() if args.css else render(spec)['tokens.css'])
        print(canonical(result)); return int(not result['passed'])
    files = render(spec)
    if args.command == 'check':
        stale = [name for name, body in files.items() if not (args.output / name).exists() or (args.output / name).read_text() != body]
        print(canonical({'passed': not stale, 'stale': stale})); return int(bool(stale))
    args.output.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (args.output / name).write_text(body, encoding='utf-8', newline='\n')
    print(f'compiled {len(files)} artifacts'); return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'NouGenDesigns input error: {exc}', file=__import__('sys').stderr)
        raise SystemExit(2)
