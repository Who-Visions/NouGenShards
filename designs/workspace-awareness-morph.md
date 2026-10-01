# Workspace awareness: arXiv 1910.03380v1

Source: [Negative Space: Workspace Awareness in 3D Face-to-Face Remote Collaboration](https://arxiv.org/pdf/1910.03380v1), Sousa et al. Read evaluation, results, discussion and conclusions on 2026-10-01.

## Observed evidence

The paper compares four combinations of workspace orientation and participant representation in a 3D instructor/assembler task with 16 participants in eight pairs. No significant differences were found in completion time, wrong selections or wrong placements. Some instructor preference responses favored consistent task frames over reflected workspaces. Participants informally calibrated their frames. The proposed Negative Space joins two physical rooms through a virtual task volume; unresolved depth mismatch and larger-group support remain future work.

This is not research on page margins, memory browsers or agent messaging. It supplies an analogy for collaboration, not proof of dashboard performance gains.

## NouGen adaptations

1. Identify the shared object independently of where it appears. A memory reference needs vault/source scope, database and record ID; a relay needs its full leg ID. A row index, screenshot position or bare memory ID can be ambiguous.
2. Show the task frame: observed machine, selected vault, filter, selected object and snapshot time where available. Two online machines do not prove identical memory coverage or synchronized views.
3. Keep identity across responsive reflow. Moving a card cannot redefine its target. Selections and copies should identify the same scoped record.
4. Distinguish observer, origin, owner and recipient. A machine displaying a shard does not establish which machine produced it.
5. Distinguish message transport acceptance, acknowledgement, ownership and verified completion. An acknowledgement loop does not transfer source bodies or finish the work.
6. Use participant presence to support the task. Preserve legible object content and state before adding avatars, mirrored presentation or decorative presence cues.

These are original NouGen requirements inferred from workspace consistency. They are compiled into the existing informationHierarchy, interactionPhysics, responsiveBehavior, stateGrammar and provenance dialect sections.

## Reassessment and acceptance checks

- The local-memory count and observed-vault metadata introduced in b0a2b42 are consistent with explicit scope.
- A future evidence-packet implementation must resolve stable vault identity; hostname plus DB number is not sufficient when one host mounts multiple vaults.
- Inspector origin and ancestry remain unresolved. No synchronization or origin inference is made from machine-online badges.
- Verify the same scoped record survives filtering, resize and inspection; compare two independently filtered views without implying they match.
- Verify a recipient can locate the exact relay/object from its reference without asking which card or row was intended.
- Audit delivery receipts separately from recipient acknowledgements and completion evidence.

This change updates design authority and review criteria. It does not implement a synchronized collaborative viewer or change peer-owned search/time files.
