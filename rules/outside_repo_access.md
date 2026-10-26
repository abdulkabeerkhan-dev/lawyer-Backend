---
trigger: always_on
description: Prohibits reads outside repository workspace and unauthorized credential usage.
---

# OUTSIDE-REPO ACCESS & CREDENTIAL PRIVACY INVARIANT

1. Zero reads outside the repository workspace: Never inspect, read, or traverse files, directories, configuration paths, or transcripts outside the target repository without explicit, advance approval from the user.
2. Zero unauthorized use of credentials found on disk: Never access, read, or use tokens, API keys, CLI configs (e.g. .railway, .env, auth profiles), or secrets located on disk or environment files without explicit user consent.
3. Hermetic boundary enforcement: All operations, audits, and verifications must execute strictly within the active repository workspace.
