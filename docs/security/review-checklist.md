# Production security review checklist

- [ ] Domain endpoints require validated institutional identity and enforce fund scope server-side.
- [ ] Production GitHub environment requires reviewers and a protected source branch.
- [ ] AWS OIDC trust checks the exact repository/environment subject and `sts.amazonaws.com` audience.
- [ ] Deployment and ECS roles pass least-privilege review; ECS Exec remains disabled by default.
- [ ] Terraform state is encrypted, versioned, private, access-logged, and recoverable.
- [ ] Secrets are absent from source, logs, images, plans shared as artifacts, and support tickets.
- [ ] ALB uses the expected certificate/TLS policy; databases and cache have no public route.
- [ ] RDS/ElastiCache encryption, backups, deletion protection, alarms, and restore drill are verified.
- [ ] High/critical dependency and container findings are resolved or formally risk-accepted.
- [ ] CloudTrail, GuardDuty, log retention, alert ownership, and incident contacts are configured.
- [ ] WAF/rate limiting and authenticated performance tests meet the documented service objectives.
- [ ] Threat model and data-retention/privacy review have named owners and review dates.
