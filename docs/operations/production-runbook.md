# Production runbook

## Deployment prerequisites

Configure each protected GitHub environment with:

- secret `AWS_DEPLOY_ROLE_ARN` for a repository/environment-scoped OIDC role;
- variables `AWS_ACCOUNT_ID`, `AWS_REGION`, `CERTIFICATE_ARN`, `WEB_ORIGIN`, `ALLOWED_HOSTS`, and
  `TERRAFORM_STATE_BUCKET`;
- required reviewers for production and a rule allowing deployments only from the protected branch.

The role should have only the ECR, ECS, ELB, RDS, ElastiCache, CloudWatch, Secrets Manager, IAM
pass-role, and Terraform-state permissions needed by this root. Restrict its trust policy by OIDC
audience and repository/environment subject. Never configure static AWS access keys.

## Release

1. Confirm CI, CodeQL, dependency review, image scans, and migration tests are green.
2. Dispatch `Deploy`, select the environment, and review the environment approval.
3. The workflow pushes `sha-<commit>` images, applies reviewed infrastructure, runs Alembic in a
   one-off private task, and updates services only after migration succeeds.
4. ECS waits for both services to stabilize. Verify `/health/live`, `/health/ready`, key user paths,
   logs, 5xx rate, latency, and database connections.

## Rollback

If the migration did not start, no service rollout occurs. If a container rollout fails, ECS circuit
breaker rollback is enabled. For a manual application rollback, identify the prior healthy task
definition revisions, update both services, and wait for stability. Database migrations must be
backward compatible (expand, migrate, contract); do not automatically downgrade a production
database. Escalate any data rollback to the incident lead and recovery runbook.

## Incident response

1. Acknowledge the SNS alarm and record incident start time, environment, release, and request IDs.
2. Check ALB target health, ECS events/task exits, CloudWatch structured logs, RDS metrics, and cache
   health. Never paste secret values into tickets or chat.
3. Stop further deployments. Roll back the application if safe; isolate compromised credentials or
   identities immediately.
4. Preserve audit evidence and CloudTrail/CloudWatch records. Notify fund leadership for suspected
   data-integrity or authorization incidents.
5. Document impact, timeline, corrective actions, and a tested prevention item.

## Service objectives

Initial targets are 99.9% monthly API availability and p95 API latency below 500 ms for ordinary
reads, excluding third-party market-data/model latency. Alert on sustained target 5xx responses,
unhealthy targets, high database CPU, task restart loops, storage pressure, and backup failures.
Revisit thresholds using observed traffic rather than weakening alerts to silence noise.
