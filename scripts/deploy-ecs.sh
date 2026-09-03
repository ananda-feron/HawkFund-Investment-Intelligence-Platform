#!/usr/bin/env bash
set -euo pipefail

environment_name="${1:?environment name is required}"
cluster_name="$(terraform output -raw ecs_cluster_name)"
api_task_definition="$(terraform output -raw api_task_definition_arn)"
web_task_definition="$(terraform output -raw web_task_definition_arn)"
security_group="$(terraform output -raw ecs_security_group_id)"
subnets="$(terraform output -json private_subnet_ids | jq -r 'join(",")')"

network="awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_group],assignPublicIp=DISABLED}"
task_arn="$(aws ecs run-task \
  --cluster "$cluster_name" \
  --launch-type FARGATE \
  --task-definition "$api_task_definition" \
  --network-configuration "$network" \
  --overrides '{"containerOverrides":[{"name":"api","command":["alembic","-c","alembic.ini","upgrade","head"]}]}' \
  --query 'tasks[0].taskArn' \
  --output text)"

if [[ -z "$task_arn" || "$task_arn" == "None" ]]; then
  echo "Migration task failed to start" >&2
  exit 1
fi

aws ecs wait tasks-stopped --cluster "$cluster_name" --tasks "$task_arn"
exit_code="$(aws ecs describe-tasks \
  --cluster "$cluster_name" \
  --tasks "$task_arn" \
  --query 'tasks[0].containers[?name==`api`].exitCode | [0]' \
  --output text)"
if [[ "$exit_code" != "0" ]]; then
  echo "Migration task exited with code $exit_code" >&2
  exit 1
fi

aws ecs update-service \
  --cluster "$cluster_name" \
  --service api \
  --task-definition "$api_task_definition" \
  --force-new-deployment >/dev/null
aws ecs update-service \
  --cluster "$cluster_name" \
  --service web \
  --task-definition "$web_task_definition" \
  --force-new-deployment >/dev/null
aws ecs wait services-stable --cluster "$cluster_name" --services api web
echo "HawkFund ${environment_name} deployment is stable."
