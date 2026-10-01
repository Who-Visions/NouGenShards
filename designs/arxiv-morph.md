# arXiv to NouGenDesigns

Donor: https://github.com/arXiv/design-system/tree/53df82bb48548438e31a00261e958bf009f63d33

Reviewed canonical sources: docs/DESIGN-POLICIES.md, docs/STYLE.md,
docs/design-system.css, docs/internal-tools.css. Mockups were excluded.
The donor is MIT licensed, copyright 2026 arXiv, Inc. This adaptation
paraphrases principles and implements native NouGen selectors; no donor
stylesheet, font, icon, logo or component source is vendored.

| Observed donor pattern | NouGen adaptation | Verification |
| --- | --- | --- |
| Shared foundation and context-specific semantic tokens | Core tokens stay separate from workbench selectors; graphite/amber identifies this surface | Compiler drift and contrast gates |
| Sustained reading near 65ch | Memory prose and inspector text use a reading-measure token | Browser computed width |
| Explicit disclosure of truncated content | Long memories preview 360 characters; native disclosure offers the complete record with a character count | Keyboard open and close |
| Rem typography and spacing | Existing type sizes and shared spacing scale converted to rem | Browser text-size growth |
| Accessible labels and target sizes | Search and clear-search names; 24px controls and 44px coarse-pointer targets | DOM names and dimensions |
| No viewport-width bands | Full-width workbench regions use their container | 320px overflow check |
| Plain recovery copy and stable vocabulary | Brand voice adds consistent task names and direct error recovery guidance | Package provenance |

The donor's blue/lime palette, typography assets, Cornell branding and
public-paper metrics restrictions do not transfer to this private workbench.
No arXiv policy is treated as authority over NouGen's own rules.

NouGenOpen reviewed the extracted principles. Its draft suggested 8px-only
spacing and a universal 65-character cap; those suggestions were rejected.
The observed donor has a 4px spacing unit and distinguishes sustained reading
from wide reference or tabular content. Codex reviewed and implemented the
adaptation. Local inference was not started because the coach load check
reported less than 4GB free RAM.
