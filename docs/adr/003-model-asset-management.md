# ADR-003 Model asset management

**Context.** Weights must not live in Git; downloads are a supply-chain risk; installs must
work offline.

**Decision.** A JSON manifest inside the package lists each asset with URL, SHA-256, size,
license, task, runtime, I/O description. `ModelRegistry` downloads to a per-user cache
(platformdirs, overridable), streams with a byte cap, verifies size and hash, writes via temp
file + atomic rename, deletes and re-fetches corrupt cache entries, and supports offline import.
`allow_download=false` disables all network access.

**Consequences.** Upstream "latest" URLs that change will fail verification (desired). Every
model addition requires a manifest row and a licensing.md row.
