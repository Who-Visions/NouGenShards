/**
 * NouGen Intelligent UI: assistant-ui Deterministic Boundary Adapter
 *
 * Implements: UI = Render(State, Contract, Permissions)
 *
 * Provides:
 * 1. Sanitized component visibility (bounded DOM metadata projection, no raw script injection)
 * 2. Scoped agent instructions mapped to AUTHORITY.md
 * 3. Typed toolkit definitions requiring explicit Dave GM approval for mutations
 * 4. Context registration binding live FTS5 shards and engine status
 */

export interface ShardProjection {
  id: number;
  db_index?: number;
  title: string;
  tags: string[];
  era?: string;
  provenance: string;
  summary: string;
  supportedActions: Array<{
    id: string;
    label: string;
    requiresApproval: boolean;
    gate: 'read' | 'mutation' | 'remote';
  }>;
}

export interface IntelligentComponentContract<T> {
  componentId: string;
  version: string;
  kind: 'shard_card' | 'shard_explorer' | 'engine_status' | 'relay_baton';
  projection: T;
  permissions: {
    canView: boolean;
    canProposeAction: boolean;
    canMutateDirectly: false; // Invariant: agents never mutate directly without GM approval
  };
}

/** Remove tag syntax with a bounded scanner; never pass HTML delimiters downstream. */
function plainTextSummary(input: string): string {
  const text = input.slice(0, 400);
  let output = '';
  let inTag = false;
  let quote = '';

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (!inTag && char === '<') {
      const next = text[i + 1] || '';
      if (/[A-Za-z/!?]/.test(next)) {
        inTag = true;
        quote = '';
      } else {
        output += '‹';
      }
      continue;
    }
    if (inTag) {
      if (quote) {
        if (char === quote) quote = '';
      } else if (char === '"' || char === "'") {
        quote = char;
      } else if (char === '>') {
        inTag = false;
      }
      continue;
    }
    output += char === '>' ? '›' : char;
  }

  return output.trim();
}

/**
 * Sanitizes a raw Shard into a bounded, model-safe projection.
 * Removes bounded tag syntax and truncates text to protect agent context.
 */
export function projectShardForAssistant(rawShard: {
  id: number;
  title: string;
  content: string;
  tags?: string[] | string;
  _db_index?: number;
  timestamp?: string;
}): ShardProjection {
  let tagsList: string[] = [];
  if (Array.isArray(rawShard.tags)) {
    tagsList = rawShard.tags;
  } else if (typeof rawShard.tags === 'string') {
    try {
      const parsed = JSON.parse(rawShard.tags);
      if (Array.isArray(parsed)) tagsList = parsed;
    } catch {
      tagsList = rawShard.tags.split(',').map((t) => t.trim().replace(/^["'\[\]]+|["'\[\]]+$/g, ''));
    }
  }

  const provenance = tagsList.find((t) => t.startsWith('provenance:'))?.replace('provenance:', '') || 'unknown';
  const cleanSummary = plainTextSummary(rawShard.content || '');

  return {
    id: rawShard.id,
    db_index: rawShard._db_index,
    title: rawShard.title,
    tags: tagsList,
    era: rawShard.timestamp,
    provenance,
    summary: cleanSummary,
    supportedActions: [
      { id: 'inspect_content', label: 'Inspect Full Text', requiresApproval: false, gate: 'read' },
      { id: 'propose_morph', label: 'Propose Morph', requiresApproval: true, gate: 'mutation' },
      { id: 'mark_utility', label: 'Mark Worked/Failed', requiresApproval: false, gate: 'read' },
      { id: 'publish_relay', label: 'Publish to Relay Fleet', requiresApproval: true, gate: 'remote' },
    ],
  };
}

/**
 * Deterministic Policy Gateway evaluator
 */
export function evaluateActionGate(actionId: string, isDryRun: boolean = true): {
  allowed: boolean;
  needsApproval: boolean;
  reason: string;
} {
  const readActions = ['inspect_content', 'search_memory', 'engine_status', 'mark_utility'];
  if (readActions.includes(actionId)) {
    return { allowed: true, needsApproval: false, reason: 'Read-only operation permitted by local policy' };
  }

  if (isDryRun) {
    return { allowed: true, needsApproval: false, reason: 'Dry-run preview permitted' };
  }

  return {
    allowed: false,
    needsApproval: true,
    reason: 'Mutation gate engaged: requires explicit GM approval before executing live on grid/relay',
  };
}
