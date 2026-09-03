# ADR 0019: AWS production topology

## Context

HawkFundOS needs a credible deployment model with isolation, recoverability, operational visibility,
and bounded cost. The application remains a modular monolith and does not benefit from Kubernetes or
independently deployed domain services.

## Decision

Deploy separate API and web containers as ECS Fargate services across two private subnets. Expose
them through one public HTTPS Application Load Balancer. Place PostgreSQL RDS and ElastiCache in
private subnets accessible only from the ECS security group. Use ECR immutable tags, Secrets Manager
runtime injection, CloudWatch logs/Container Insights/alarms, ECS circuit-breaker rollback, and CPU
target tracking for the API.

RDS uses encrypted storage, Multi-AZ in production, 35-day automated backups, deletion protection,
a final snapshot, and Performance Insights. ElastiCache uses two nodes, Multi-AZ failover, TLS,
at-rest encryption, authentication, and seven days of snapshots. Terraform state must use an
encrypted, versioned S3 backend with lockfile locking.

## Alternatives

- EKS: rejected because cluster and operational complexity do not benefit this workload.
- Public ECS tasks or public databases: rejected because only the ALB should accept internet traffic.
- Self-managed PostgreSQL/Redis on ECS: rejected because patching, failover, and recovery burdens are
  inappropriate.
- Lambda: deferred because the current web/API processes and database connection model fit containers.

## Consequences

The topology is reproducible and supports rolling deployments. A single NAT gateway controls cost
but is an availability tradeoff; a production budget can fund one NAT per availability zone later.
Infrastructure creates recurring AWS costs and must be applied only after a reviewed plan.
