# Release validation

This checkpoint freezes product scope. A release candidate is ready only when every automated gate
passes and the environment-dependent exercises have dated evidence. Architecture or operational
fixes discovered by these checks are allowed; new portfolio features are not.

## Automated acceptance

| Gate | Command | Evidence |
| --- | --- | --- |
| Backend lint, formatting, types, unit tests | `make check-api` | Command log and CI backend job |
| Frontend lint, types, tests | `make check-web` | Command log and CI frontend job |
| Terraform formatting and validation | `make check-infra` | Command log and CI infrastructure job |
| Full deterministic business chain | `make golden-path` | `test_release_golden_path.py` |
| Production image build and vulnerability scan | CI containers job | Build and Trivy logs |
| Local stack, health, idempotent fixtures, persistence, non-root images | `make docker-acceptance` | Dated terminal log |
| Isolated backup and restore comparison | `make recovery-drill` | Dated terminal log |

The golden path covers transaction posting, reproducible snapshot reconstruction, provenanced market
price ingestion, historical valuation, analytics and risk, scenario analysis, a policy breach,
role-separated proposal review/rejection, a grounded AI explanation, citations, and audit events.

## AI adversarial matrix

| Threat | Enforced behavior | Automated evidence |
| --- | --- | --- |
| Mutation request or invented tool | Reject and audit as `INVALID` | `test_unknown_mutation_tool_is_audited_and_answer_is_refused` |
| Cross-fund or caller-supplied scope | Reject extra `fund_id`; bind scope to authorized context | `test_registry_rejects_scope_override_and_mutation_tool` |
| Actor without a fund role | Deny before domain data access | `test_registry_denies_actor_without_fund_role` |
| Instructions embedded in retrieved data | Treat evidence as untrusted data | `test_grounded_answer_has_application_sources_and_immutable_history` |
| Missing point-in-time evidence | Refuse even when the model invents an answer | `test_unavailable_data_forces_refusal_even_if_model_invents_an_answer` |
| Unsupported or malformed tool arguments | Strict JSON schemas; reject additional properties | `test_tool_schemas_are_strict` and registry tests |
| Uncited answer | Require at least one successful application source | AI service tests and golden path |

## Controlled AWS exercise

Do not apply Terraform merely to claim deployment. On an approved AWS account with a reviewed cost
budget, capture these artifacts in the release record:

1. `terraform plan` output reviewed for public endpoints, encryption, backups, deletion protection,
   security groups, secret injection, log retention, and alarms.
2. A version-tagged API and web image in ECR with scan results.
3. One successful deployment via `scripts/deploy-ecs.sh`, ALB health evidence, an authenticated
   golden-path smoke test, and CloudWatch correlation by request ID.
4. One failed deployment or deliberately unhealthy task proving the ECS deployment circuit breaker
   rolls back to the prior task definition.
5. Destruction of the temporary environment after evidence capture, unless it is the approved
   production environment.

## Recovery exercise

First run the isolated local drill. Then perform the quarterly RDS restore drill described in
`docs/operations/backup-and-recovery.md`. Record timestamps for backup cutoff, restore start,
integrity verification, and application readiness. RPO and RTO remain targets until measured.

## Current sign-off

- Full golden path: implemented and executable in the backend test suite.
- AI boundary: automated adversarial coverage exists and is included in normal CI.
- Docker acceptance: scripted; must be run on a Docker-enabled host.
- Local recovery drill: scripted; must be run on a Docker-enabled host.
- AWS deploy/rollback and RDS restore: documented but intentionally require an approved account,
  budget, credentials, and an evidence-capture window.

The release is not signed off until the final three environment-dependent items have dated evidence.
