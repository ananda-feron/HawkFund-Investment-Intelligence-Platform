# HawkFundOS threat model

## Scope and assets

This model covers the public ALB, web/API containers, CI/CD identity, Secrets Manager, RDS,
ElastiCache, logs, and Terraform state. Primary assets are transaction and portfolio integrity,
governance/audit evidence, identities and permissions, market-data provenance, provider credentials,
deployment authority, and service availability.

Trust boundaries are internet-to-ALB, ALB-to-private ECS, ECS-to-data services, GitHub-to-AWS OIDC,
model-to-typed AI tools, and operator-to-Terraform state. Authentication remains a required product
integration before exposing domain endpoints to real users.

| Threat | Control | Residual action |
| --- | --- | --- |
| Spoofed caller or cross-fund access | Fund-scoped service authorization, explicit hosts, TLS | Add institutional SSO, token validation, session revocation, and authorization integration tests before real users |
| Tampered financial or approval evidence | Append-only ledger/evidence, hashes, PostgreSQL triggers, backups | Monitor privileged DB activity and separate migration from application credentials |
| Repudiated proposal or AI action | Actor IDs, immutable transitions, conversation/tool audit, request IDs | Centralize CloudTrail and logs in a restricted audit account |
| Secret or data disclosure | Private subnets, security groups, TLS, encrypted storage, Secrets Manager, masked errors | Add automated rotation and data-classification/retention enforcement |
| Denial of service | WAF managed rules/rate limit, ALB health checks, ECS scaling, resource limits, timeouts, alarms | Tune limits and load-test authenticated domain endpoints |
| Privilege escalation through CI | OIDC short-lived credentials, protected environment, concurrency gate, no static keys | Bootstrap a least-privilege role and pin third-party actions to reviewed commit SHAs |
| Supply-chain compromise | Lockfiles, dependency audit/review, CodeQL, Trivy, immutable ECR tags | Generate/attest SBOMs and adopt signed-image admission verification |
| Prompt/tool injection | Strict read-only schemas, application-bound fund, evidence-required answers | Maintain adversarial evaluation corpus as tools expand |
| Destructive migration | Tested migrations, migration-before-rollout, expand/migrate/contract, backups | Require database-owner review and a successful restore drill for high-risk changes |

## Security release gate

Before internet exposure, close the authentication/SSO residual action, confirm CloudTrail and
GuardDuty account controls, test backup restoration, tune WAF rules, verify least-privilege IAM
with Access Analyzer, and conduct an independent application/infrastructure review. Phase 7 provides
the deployment foundation; it does not claim those organization-level controls are already active.
