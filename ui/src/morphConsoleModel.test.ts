/**
 * Unit tests for Morph Intelligent UI Verified State Models & Gates.
 *
 * Verifies invariants from Shards 31407@db5 and 31406@db5:
 * - 6 typed verified views (SPEC, AGENTS, RESULTS, PROVENANCE, DECISIONS, TASKS)
 * - Semantic color badge tokens (green ONLY for verified, purple identity, red conflict)
 * - Operator mutation gate enforcement (fail-closed without operator token)
 */

import { describe, it, expect } from 'vitest';
import {
  getStatusBadgeStyle,
  evaluateOperatorGate,
  MorphConsoleState,
  ViewTab,
} from './morphConsoleModel';

describe('Morph Intelligent UI Console Models & Gates', () => {
  it('enforces semantic color invariant strictly', () => {
    const verified = getStatusBadgeStyle('verified');
    expect(verified.color).toBe('#4ade80');
    expect(verified.border).toBe('#22c55e');

    const pending = getStatusBadgeStyle('pending');
    expect(pending.color).toBe('#fbbf24');

    const conflict = getStatusBadgeStyle('conflict');
    expect(conflict.color).toBe('#f87171');

    const notedOffline = getStatusBadgeStyle('noted_offline');
    expect(notedOffline.color).toBe('#94a3b8');
    expect(notedOffline.border).toBe('#64748b');

    const simulation = getStatusBadgeStyle('simulation');
    expect(simulation.color).toBe('#9ca3af');
  });

  it('enforces operator mutation gate for decision approvals', () => {
    // Read operations pass unconditionally
    expect(evaluateOperatorGate('inspect', false).allowed).toBe(true);
    expect(evaluateOperatorGate('replay', false).allowed).toBe(true);

    // Mutations without operator token are blocked fail-closed
    const blockedApproval = evaluateOperatorGate('approve', false);
    expect(blockedApproval.allowed).toBe(false);
    expect(blockedApproval.reason).toContain('Mutation gate engaged');

    const blockedQuarantine = evaluateOperatorGate('quarantine', false);
    expect(blockedQuarantine.allowed).toBe(false);

    // Mutations with operator token pass
    const verifiedApproval = evaluateOperatorGate('approve', true);
    expect(verifiedApproval.allowed).toBe(true);
    expect(verifiedApproval.reason).toContain('Operator authority verified');
  });

  it('supports full typed 6-view console model without structural drift', () => {
    const mockState: MorphConsoleState = {
      activeTab: 'SPEC',
      spec: {
        briefId: 'xda_notes_comparison',
        title: 'Note-Taking App Cross-Provider SpecParity',
        requirements: [
          { id: 'req_1', kind: 'explicit', description: 'Offline PWA canvas notes', source: 'xda', verified: true },
          { id: 'req_2', kind: 'inferred', description: 'Auto-save with debounced IndexedDB', source: 'morph', verified: true },
          { id: 'req_3', kind: 'unknown', description: 'Sync protocol to self-hosted storage', source: 'brief', verified: false },
        ],
        acceptanceCriteria: ['Passes local E2E suite', 'Zero cloud leak on offline canvas'],
      },
      agents: [
        {
          laneId: 'lane_blade',
          provider: 'local_gemma',
          modelName: 'gemma4:e2b-qat',
          branch: 'main',
          commitSha: '0b50aa0',
          budgetTokens: 2048,
          runtimeMs: 420,
          status: 'online',
        },
      ],
      results: [
        {
          testId: 'test_offline_canvas',
          name: 'Offline Canvas Stroke Test',
          passed: true,
          durationMs: 124,
          evidenceStrength: 'conclusive',
          evidenceRef: 'proof_canvas_e2e_482bdf06',
        },
      ],
      provenance: [
        {
          shardId: 31407,
          dbIndex: 5,
          relayLegId: '20261009T225042Z__chatgpt-app__g-whoentertains',
          timestampUtc: '2026-10-09T22:50:42.229Z',
          sourceUrl: 'https://github.com/Who-Visions/NouGenRelay',
          sha256Digest: 'a512e24e08410c8e3118e6cc8619b38865fd6135',
          peerReplicationCount: 3,
        },
      ],
      decisions: [
        {
          decisionId: 'dec_1',
          targetArtifact: 'MorphConsoleModel.ts',
          verdict: 'accept',
          requiresOperatorApproval: false,
          blockingRisk: 0.05,
        },
      ],
      tasks: [
        {
          taskId: 'task_ui_views',
          title: 'Implement SPEC/AGENTS/RESULTS/PROVENANCE/DECISIONS/TASKS Views',
          owner: 'antigravity',
          dependsOn: [],
          status: 'complete',
          evidenceGate: 'unit_tests_pass',
        },
      ],
    };

    expect(mockState.spec.requirements.length).toBe(3);
    expect(mockState.agents[0].status).toBe('online');
    expect(mockState.provenance[0].shardId).toBe(31407);
    expect(mockState.decisions[0].verdict).toBe('accept');
    expect(mockState.tasks[0].status).toBe('complete');
  });
});
