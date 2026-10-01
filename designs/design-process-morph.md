# Design process: arXiv 2507.05601, 2609.05364, 2508.12726

Source depth, stated first: 2507.05601 was read from extracted full text (abstract,
introduction, related work, conclusions). 2609.05364 and 2508.12726 were read only
as alphaXiv-generated reports; figures below are the reports'. Review the full
papers before treating any item here as authority.

## 2507.05601 Accordion (Adobe Research, HKUST)

Observed: converts a whole reference design into background, object and text
layers top-down, rather than generating elements one by one, which the authors
say causes conflicts such as text taking space a later element needs. Stated
limits: SAM IoU 68.4%, text assumed above objects, 2,000 predefined text styles.

Adopted (inferred, in `informationHierarchy`): settle composition before
components; keep text as live text. Not adopted: the VLM pipeline.

## 2609.05364 SMART

Observed (report): natural-language design docs are the durable artifact and code
is regenerated from them; worked examples and a small reconciliation preset with
exact expected outputs are enforced by tests. Domain: ML performance modelling.

Adopted: nothing new. `design.json` is already the source, and `check` fails on
drift in generated artifacts. A possible extension is a worked example with
exact computed contrast values that `check` re-verifies; not implemented.

## 2508.12726 DESIGNER

Observed (report): reusable "design logics" extracted from expert exemplars are
retrieved by similarity and followed to generate questions; removing them hurt in
the authors' ablation. Quality figures are LLM-judged; the question bank is
proprietary; the task is exam questions.

Candidate, untested for interfaces: keep short construction recipes per recurring
pattern and select one by similarity instead of copying a sample page.
Needs an experiment before it becomes a rule.
