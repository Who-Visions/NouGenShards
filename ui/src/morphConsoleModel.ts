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

export type StateBadge = 'verified' | 'pending' | 'conflict' | 'noted_offline' | 'simulation';

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
  status: 'online' | 'busy' | 'noted_offline' | 'offline';
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
      return {
        color: 'var(--status-verified-text, #a9c79b)',
        background: 'var(--status-verified-bg, rgba(169, 199, 155, 0.12))',
        border: 'var(--status-verified-border, #a9c79b)',
      };
    case 'pending':
      return {
        color: 'var(--status-pending-text, #e8b86d)',
        background: 'var(--status-pending-bg, rgba(232, 184, 109, 0.12))',
        border: 'var(--status-pending-border, #e8b86d)',
      };
    case 'conflict':
      return {
        color: 'var(--status-conflict-text, #ffb4ab)',
        background: 'var(--status-conflict-bg, rgba(255, 180, 171, 0.12))',
        border: 'var(--status-conflict-border, #ffb4ab)',
      };
    case 'noted_offline':
      // Shard 31409@db5: NOTED OFFLINE for portable peers is informational, NOT failed/red alarm
      return {
        color: 'var(--status-offline-text, #bdb8ad)',
        background: 'var(--status-offline-bg, rgba(189, 184, 173, 0.10))',
        border: 'var(--status-offline-border, #777777)',
      };
    case 'simulation':
    default:
      return {
        color: 'var(--status-sim-text, #bdb8ad)',
        background: 'var(--status-sim-bg, rgba(189, 184, 173, 0.10))',
        border: 'var(--status-sim-border, #777777)',
      };
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
