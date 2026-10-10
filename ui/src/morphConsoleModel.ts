/**
 * NouGen Intelligent UI: Morph SpecParity & Verified State Views
 *
 * Implements: UI = Render(VerifiedState, TypedContract, Permissions)
 * Authority: Shards 31407@db5, 31406@db5 | Relay 20261009T225042Z
 *
 * Provides strongly-typed verified-state models and deterministic render contracts for:
 * 1. SPEC: Immutable SpecIR explicit requirements, inferred hypotheses, unknowns, tradeoffs
 * 2. AGENTS: Provider/lane comparison cards (branch, model, budget, runtime, latency)
 * 3. RESULTS: Deterministic E2E outcomes separated from subjective review
 * 4. PROVENANCE: Source URLs, timestamps, shard IDs, peer replication coverage
 * 5. DECISIONS: Explicit approval gates (accept/revise/quarantine) with actor/permission check
 * 6. TASKS: Explicit dependency DAGs, leases, and blocked states
 */

export type ViewTab = 'SPEC' | 'AGENTS' | 'RESULTS' | 'PROVENANCE' | 'DECISIONS' | 'TASKS';

export type StateBadge = 'verified' | 'pending' | 'conflict' | 'simulation';

export interface SpecRequirement {
  id: string;
  kind: 'explicit' | 'inferred' | 'unknown' | 'tradeoff';
  description: string;
  source: string;
  verified: boolean;
}

export interface SpecModel {
  briefId: string;
  title: string;
  requirements: SpecRequirement[];
  acceptanceCriteria: string[];
}

export interface AgentLaneModel {
  laneId: string;
  provider: string; // Generic provider identifier
  modelName: string;
  branch: string;
  commitSha: string;
  budgetTokens: number;
  runtimeMs: number;
  status: 'online' | 'busy' | 'offline';
}

export interface TestOutcome {
  testId: string;
  name: string;
  passed: boolean;
  durationMs: number;
  evidenceStrength: 'conclusive' | 'partial' | 'inconclusive';
  evidenceRef: string;
}

export interface ProvenanceRecord {
  shardId: number;
  dbIndex: number;
  relayLegId: string;
  timestampUtc: string;
  sourceUrl?: string;
  sha256Digest: string;
  peerReplicationCount: number;
}

export interface DecisionRecord {
  decisionId: string;
  targetArtifact: string;
  verdict: 'accept' | 'revise' | 'quarantine';
  requiresOperatorApproval: boolean;
  approvedBy?: string;
  blockingRisk: number;
  criticalIssue?: string;
}

export interface TaskDagNode {
  taskId: string;
  title: string;
  owner: string;
  dependsOn: string[];
  status: 'unblocked' | 'in_progress' | 'blocked' | 'complete';
  evidenceGate: string;
}

export interface MorphConsoleState {
  activeTab: ViewTab;
  spec: SpecModel;
  agents: AgentLaneModel[];
  results: TestOutcome[];
  provenance: ProvenanceRecord[];
  decisions: DecisionRecord[];
  tasks: TaskDagNode[];
}

/**
 * Deterministic color token mapping per Shard 31407@db5 invariant:
 * - Purple: identity accent
 * - Green: ONLY verified
 * - Amber: pending / incomplete
 * - Red: conflicts / critical blocks
 * - Grey: simulation / unverified
 */
export function getStatusBadgeStyle(status: StateBadge): { color: string; background: string; border: string } {
  switch (status) {
    case 'verified':
      return { color: '#4ade80', background: 'rgba(34, 197, 94, 0.1)', border: '#22c55e' };
    case 'pending':
      return { color: '#fbbf24', background: 'rgba(245, 158, 11, 0.1)', border: '#f59e0b' };
    case 'conflict':
      return { color: '#f87171', background: 'rgba(239, 68, 68, 0.1)', border: '#ef4444' };
    case 'simulation':
    default:
      return { color: '#9ca3af', background: 'rgba(156, 163, 175, 0.1)', border: '#6b7280' };
  }
}

/**
 * Validates that an action against a decision or task honors the mutation gate.
 */
export function evaluateOperatorGate(
  action: 'approve' | 'quarantine' | 'inspect' | 'replay',
  hasOperatorToken: boolean
): { allowed: boolean; reason: string } {
  if (action === 'inspect' || action === 'replay') {
    return { allowed: true, reason: 'Read-only telemetry access permitted.' };
  }
  if (!hasOperatorToken) {
    return {
      allowed: false,
      reason: 'Mutation gate engaged: Explicit operator/GM credentials required for state change.',
    };
  }
  return { allowed: true, reason: 'Operator authority verified.' };
}
