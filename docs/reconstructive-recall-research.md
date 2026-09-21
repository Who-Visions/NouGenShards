# Reconstructive Recall: Evidence and Engineering Boundaries

Research cross-reference for `reconstructive_recall_v2.py`, checked 2026-09-16. This is an engineering design note, not a claim that software retrieval reproduces neural memory.

## Talbot and Howard: process donor, not source of scientific fact

Talbot's *The Holographic Universe* and Chris Howard's lecture/archive are treated as prompts to test reconstruction, distributed cues, and source criticism. They are not factual authorities for neuroscience. Keep their metaphysical claims in an attributed claim layer; do not promote holographic/quantum consciousness, a universal memory field, or a 5%/95% conscious/unconscious split into NouGen's truth layer.

Historical source checks:

- Penfield's article on electrical stimulation and reactivation of past experience is from 1959, not 1913 ([PubMed record](https://pubmed.ncbi.nlm.nih.gov/13668523/)). Stimulation-evoked reports are not proof that a perfect, complete recording of life is stored and replayed.
- Lashley's 1925 lesion paper concerns cortical lesions in rat brightness-discrimination experiments. Its first series reports lesions involving 13-40% of cortex and no significant learning-rate difference; that paper does not support a brainstem-only maze claim or a simple monotonic law ([primary paper record and abstract](https://journals.sagepub.com/doi/10.3181/00379727-22-197)).
- Pribram's holonomic/holographic analogy is a later theoretical proposal, with cited work from the 1960s onward, not a 1913 discovery. Distributed representation is a useful design analogy; literal optical hologram storage is not established by that analogy ([Pribram-authored overview](https://karlpribram.com/wp-content/uploads/pdf/theory/T-095.pdf)).

## 2026 neuroscience: bounded analogies

- Senne et al. report time-compressed, context-specific dorsal CA1 astrocytic calcium-event sequences in mice during contextual fear learning and later recall ([Nature Neuroscience, 2026-09-16](https://www.nature.com/articles/s41593-026-02448-0)). **Engineering inference:** a separate control/index plane may shape retrieval order and salience while remaining unable to author facts. The animal result does not establish an "astrocytic memory store" in NouGen.
- Rozeske et al. report greater representational overlap in ventral than dorsal CA1 and faster/stronger threat-context reinstatement in vCA1 in a mouse fear-conditioning task ([Nature Neuroscience, 2026-09-14](https://www.nature.com/articles/s41593-026-02435-5)). **Engineering inference:** related records can share typed association cues, but false-overlap tests must ensure similar unrelated memories do not merge.
- Hu et al. report task-relevant neural-manifold separation after odor-discrimination training in zebrafish pDp, without obvious attractor-dynamics signatures ([Nature Neuroscience, 2026-09-10](https://www.nature.com/articles/s41593-026-02429-3)). **Engineering inference:** measure retrieval confusions and improve routing/disambiguation features without mutating source facts.

## Agent-memory donors and their status

- MRAgent proposes a Cue-Tag-Content graph with active, evidence-guided exploration and pruning; it is a design donor, not a NouGen benchmark result ([arXiv:2606.06036](https://arxiv.org/abs/2606.06036)).
- Agent Zero Memory describes parallel episodic, associative, and documentary stores with citation locks. Treat its reported benchmark numbers as the authors' preprint claims, not independently reproduced NouGen performance ([arXiv:2608.29606](https://arxiv.org/abs/2608.29606)).
- LongMemEval-V2 contributes useful environment-memory dimensions: static state, dynamic tracking, workflow, gotchas, and premise awareness, over long trajectories. Its reported accuracy/latency results are not transferable without running a fixed NouGen evaluation ([arXiv:2605.12493](https://arxiv.org/abs/2605.12493)).

## Implemented hardening and current limits

The v2 engine now applies separate valid-time (`as_of_ms`) and record-time (`known_as_of_ms`) filters; admits only directly validated same-branch supersessions; keeps unresolved conflicts in quarantine; reports configured source-lane coverage separately from required-node result coverage; and binds a canonical per-event manifest (including content, source, timestamps, and evidence pointer) to the envelope lock. `verify_evidence_lock` rejects unopened citations, modified evidence, and altered manifests.

This remains an in-memory deterministic prototype. `available_stores` is an explicit local lane configuration, not proof that remote fleet vaults were queried. It does not yet implement embedding search, recursive LLM-guided graph expansion, a learned manifold, or production federation. The next meaningful evaluation should add correction/retraction history semantics and fixed temporal-update/abstention questions before any accuracy or latency claim.
