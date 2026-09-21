# Retrieval v2: arXiv Donor Notes

These papers are design inputs, not evidence that NouGen implements their full
algorithms or reproduces their reported benchmark results. The current donor
cascade is a deterministic text-only baseline.

| Paper | Transferable idea | Fit in this cascade | Not implemented here |
| --- | --- | --- | --- |
| [ColBERTv2, arXiv:2112.01488](https://arxiv.org/abs/2112.01488) | Token-level multi-vector late interaction; residual compression reduces index footprint. | Candidate for a future embedding lane. | Token embeddings, MaxSim, and residual quantization. Exact lexical overlap is not a substitute. |
| [G-Retriever, arXiv:2402.07630](https://arxiv.org/abs/2402.07630) | Retrieve a relevant subgraph, formulated as prize-collecting Steiner tree optimization. | Relevant only where evidence is a scored textual graph. | Graph edge scores, PCST optimization, and graph answer generation. |
| [ColGraphRAG, arXiv:2607.16208](https://arxiv.org/abs/2607.16208) | Late-interaction ranking for graph-linked visual evidence. | Not applicable to this text-only input schema. | Image nodes, visual token representations, and multimodal retrieval. |
| [MRAgent, arXiv:2606.06036](https://arxiv.org/abs/2606.06036) | Cue-tag-content associative paths with evidence-guided, bounded reconstruction. | Aligns with the separate bounded `reconstruction.py` prototype. | This module does not perform graph expansion or LLM-guided pruning. |
| [Agent Zero Memory, arXiv:2608.29606](https://arxiv.org/abs/2608.29606) | Multiple complementary memory views, provenance-aware retrieval, and a citation lock limited to evidence actually opened. | Supports keeping lane provenance and content hashes with returned evidence. | The donor cascade is not a multi-store agent or a reproduction of its benchmark results. |

The implemented baseline ranks exact-token lexical overlap, character trigrams,
and explicit entity overlap independently, fuses those ranked lists with
Retrieval v2's existing deterministic RRF, and abstains on weak or tied evidence.
The optional fast path is accepted only when its caller marks the artifact
opened and supplies a SHA-256 matching the supplied content. Returned evidence
hashes bind the answer packet to the exact text read by this function.

No applicability or latency percentages are asserted. Those require a
NouGen-specific benchmark with a fixed corpus, queries, relevance labels, and
hardware measurements.
