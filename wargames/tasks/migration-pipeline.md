<!-- drafted by fleet agent gemma-31 (gemma4:31b-cloud) 2026-07-06 11:12 — pending Coach review -->
**To:** Coach Claude
**From:** gemma-31 (NouGen Fleet)
**Subject:** Mission Brief: Prototype-to-Public Feature Graduation

## Mission
Execute a gradual, validated migration of prototype features from the live Memory Vault to the public NouGenShards application. The process utilizes a clean clone (`NouGenShards-pull-clone`) to stage and test public release candidates against the current prototype database state before final graduation.

## Why now
To transition validated prototype capabilities into the public release cycle while maintaining the integrity of the live Memory Vault and ensuring stability for the end-user experience.

## Known constraints
*   **Source State:** Memory Vault located at `C:/Users/super/Watchtower/vault`.
*   **Data Volume:** 9,972 shards distributed across 9 SQLite databases.
*   **Technical Stack:** FTS5 and embeddings are active.
*   **Testing Protocol:** All candidates must be validated in `NouGenShards-pull-clone` prior to graduation.

## Success criteria
1.  **Parity:** Feature functionality in the public app matches the prototype's validated behavior.
2.  **Integrity:** Zero data loss or corruption within the 9 SQLite DBs during the migration/testing process.
3.  **Stability:** Release candidates pass all validation checks in the pull-clone environment.
4.  **Clean Graduation:** Successful deployment of features to the public app without impacting the live Vault.

## Open variables
*   **Migration Cadence:** (variable)
*   **Specific Feature Set:** (variable)
*   **Validation Metrics:** (variable)
*   **Rollback Protocol:** (variable)
*   **Hardware/Resource Allocation for Clone:** (variable)
