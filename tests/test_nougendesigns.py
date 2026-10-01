import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location('nougendesigns', ROOT / 'tools/nougendesigns.py')
design = importlib.util.module_from_spec(loader)
loader.loader.exec_module(design)

class DesignTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / 'designs/nougen-core/design.json').read_text())

    def test_deterministic_generation_and_checked_in_outputs(self):
        shuffled = dict(reversed(list(self.spec.items())))
        self.assertEqual(design.render(self.spec), design.render(shuffled))
        for name, body in design.render(self.spec).items():
            self.assertEqual(body, (ROOT / 'designs/nougen-core' / name).read_text())

    def test_theme_contrast_failure(self):
        self.spec['themes']['light']['--text'] = '#f5f1e8'
        self.assertFalse(design.lint(self.spec)['passed'])

    def test_missing_section_and_css_injection(self):
        del self.spec['density']
        self.spec['tokens']['--bg'] = '#fff; } body { display:none'
        with self.assertRaises(ValueError):
            design.render(self.spec)

    def test_anti_slop_gate(self):
        for value in ('background:linear-gradient(red,blue)', 'backdrop-filter:blur(4px)', 'border-radius:999px', 'box-shadow:0 0 12px red'):
            result = design.lint(self.spec, 'a:focus-visible{} /* prefers-reduced-motion */ a{' + value + ';}')
            self.assertTrue(any('anti-slop' in error for error in result['errors']))

    def test_binary_reference_is_not_claimed_as_visual_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'reference.png'
            file.write_bytes(b'\x89PNG\r\n')
            record = design.inspect_source(file)[0]
            self.assertIn('interpretation', record['note'])
            self.assertEqual(len(record['sha256']), 64)
            self.assertNotIn('tokens', record)

    def test_real_ui_passes_measured_gate(self):
        self.assertTrue(design.lint(self.spec, (ROOT / 'ui/src/styles.css').read_text())['passed'])

    def test_analysis_draft_is_deterministic_and_reports_measured_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sample-ui'
            (root / 'src').mkdir(parents=True)
            (root / 'node_modules/pkg').mkdir(parents=True)
            css = root / 'src/styles.css'
            css.write_text('''
:root { --surface: #202020; }
a:focus-visible { outline: 2px solid orange; }
@media (prefers-reduced-motion: reduce) { * { animation: none; } }
.hero { background: linear-gradient(red, blue); }
''')
            app = root / 'src/App.tsx'
            app.write_text("export function Sample() { return <button aria-label='Run'>Run</button>; }")
            (root / 'node_modules/pkg/ignored.css').write_text('a{background:linear-gradient(red,blue)}')
            brief = Path(directory) / 'brief.md'
            brief.write_text('Keep the interface calm and easy to scan.\n')

            files, report, analysis = design.analyze_inputs(root, brief, self.spec)
            files_again, report_again, analysis_again = design.analyze_inputs(root, brief, self.spec)

            self.assertEqual(files, files_again)
            self.assertEqual(report, report_again)
            self.assertEqual(analysis, analysis_again)
            self.assertFalse(report['passed'])
            self.assertEqual(analysis['summary']['sourceFiles'], 2)
            self.assertEqual(analysis['summary']['componentFiles'], 1)
            self.assertEqual(analysis['tokenCandidates']['--surface'][0]['value'], '#202020')
            app_record = next(row for row in analysis['sourceEvidence'] if row['source'].endswith('App.tsx'))
            self.assertEqual(app_record['elements']['button'], 1)
            self.assertEqual(app_record['ariaAttributes'], 1)
            self.assertIn('Keep the interface calm', files['DESIGN.md'])
            self.assertIn('gradient', files['mutations.json'])
            self.assertIn('linear-gradient', css.read_text())

if __name__ == '__main__':
    unittest.main()
