# Backup and recovery strategy

## Policy

RDS retains automated backups for 35 days and supports point-in-time recovery. Production enables
Multi-AZ, deletion protection, encrypted storage, and a mandatory final snapshot. ElastiCache keeps
seven daily snapshots, but PostgreSQL remains the authoritative record; cache loss must not cause
portfolio or governance data loss.

Take a manual RDS snapshot before high-risk schema changes. Retain monthly snapshots according to
the fund's approved retention policy and account-level backup controls. AWS Backup cross-account or
cross-region copies are the next control when the project's recovery classification requires them.

## Restore drill

Quarterly, restore RDS to a new isolated instance at a selected timestamp, run migrations only if
required by the tested release, and verify fixture-independent invariants: ledger counts and hashes,
snapshot reproducibility, governance/audit immutability, and representative valuations. Record the
actual recovery-point and recovery-time results. Never overwrite the source database during a drill.

The initial objectives are RPO of 15 minutes and RTO of four hours. They are targets requiring
measured restore drills, not guarantees. A production incident lead decides cutover after integrity,
security, and application smoke checks pass.
