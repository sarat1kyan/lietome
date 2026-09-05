# ADR-005 Project license: Apache-2.0

**Context.** Open-source project mixing code, pretrained models, and (later) trained artifacts;
we want wide adoption including by companies and researchers, and protection against patent
claims from contributors.

**Decision.** Apache License 2.0.

**Comparison.** MIT/BSD: simplest, but no explicit patent grant. Apache-2.0: permissive plus
patent grant and retaliation clause; used by TensorFlow, MediaPipe, PyTorch ecosystem tooling;
compatible with MIT/BSD dependencies and Apache-2.0 model weights. GPL-3/AGPL-3: copyleft would
require every downstream user to open their modifications (AGPL even for network use); this
deters adoption and complicates combining with permissive-but-GPL-incompatible components.
GPL-licensed components (parselmouth) therefore stay out of the core.

**Consequences.** Contributions are under Apache-2.0 (inbound = outbound). Attribution notices
for bundled third-party components go in `NOTICE` when we redistribute any.
