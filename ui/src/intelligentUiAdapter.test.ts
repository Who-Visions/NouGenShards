import { describe, it, expect } from 'vitest';
import { projectShardForAssistant, evaluateActionGate } from './intelligentUiAdapter';

describe('Intelligent UI Adapter Deterministic Boundary', () => {
  it('sanitizes and bounds raw shard projections for assistant visibility', () => {
    const rawShard = {
      id: 30377,
      title: 'Test Intelligent Shard',
      content: '<script>alert("hack")</script><p>Clean content text that should be bounded.</p>',
      tags: '["provenance:dav3", "architecture", "ui"]',
      _db_index: 7,
      timestamp: '2026-10-08T16:40:00Z',
    };

    const projection = projectShardForAssistant(rawShard);

    expect(projection.id).toBe(30377);
    expect(projection.db_index).toBe(7);
    expect(projection.provenance).toBe('dav3');
    expect(projection.summary).not.toContain('<script>');
    expect(projection.summary).toContain('Clean content text');
    expect(projection.supportedActions.length).toBeGreaterThan(0);
  });

  it('removes malformed and quoted markup without leaving HTML delimiters', () => {
    const projection = projectShardForAssistant({
      id: 1,
      title: 'untrusted',
      content: '<script src="x>y">alert(1)</script><img src=x onerror=alert(1)><script',
    });

    expect(projection.summary).not.toMatch(/[<>]/);
    expect(projection.summary).toContain('alert(1)');
  });

  it('enforces mutation gates deterministically', () => {
    // Read action passes without approval
    const readGate = evaluateActionGate('inspect_content', false);
    expect(readGate.allowed).toBe(true);
    expect(readGate.needsApproval).toBe(false);

    // Mutation action under dry-run passes preview
    const dryRunGate = evaluateActionGate('propose_morph', true);
    expect(dryRunGate.allowed).toBe(true);
    expect(dryRunGate.needsApproval).toBe(false);

    // Live mutation requires GM approval
    const liveMutationGate = evaluateActionGate('propose_morph', false);
    expect(liveMutationGate.allowed).toBe(false);
    expect(liveMutationGate.needsApproval).toBe(true);
    expect(liveMutationGate.reason).toContain('Mutation gate engaged');
  });
});
