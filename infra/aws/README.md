# AWS deployment

This Terraform root creates the Phase 7 reference topology. It does not own DNS records or the ACM
certificate, and it must not be run with local state for a shared environment.

## Prerequisites

- Terraform 1.16.x and an AWS account with a reviewed provisioning role.
- A versioned, encrypted S3 state bucket. Enable bucket policy controls that require TLS and block
  public access. The workflow enables native S3 lockfile locking.
- An ACM certificate in the deployment region and DNS pointing at the `alb_dns_name` output.
- GitHub environments named `staging` and `production`; production should require reviewers.
- GitHub variables and secrets documented in the production runbook.

## First apply

Copy `terraform.tfvars.example` outside version control, replace every placeholder, and initialize
the partial S3 backend. For a new environment, first apply only the two ECR repositories, push the
initial API and web images, replace the image placeholders with those immutable image references,
and then inspect and apply the complete plan. This avoids creating ECS services with nonexistent
images. Use an authorized operator identity for bootstrap; normal releases use CI/CD.

The generated database and cache credentials are sensitive Terraform values stored in encrypted
remote state and copied to Secrets Manager. Restrict both state and secret access.

After the bootstrap apply, configure the GitHub environment with the deployment role and Terraform
values. Normal releases run `.github/workflows/deploy.yml`; do not run ad-hoc service updates.

Terraform intentionally ignores service `task_definition` changes. It registers new revisions, then
the deployment script runs Alembic as a one-off private Fargate task. Only a successful migration
allows the API and web services to roll forward.
