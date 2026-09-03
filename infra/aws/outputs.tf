output "alb_dns_name" {
  value = aws_lb.main.dns_name
}
output "api_repository_url" {
  value = aws_ecr_repository.api.repository_url
}
output "web_repository_url" {
  value = aws_ecr_repository.web.repository_url
}
output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}
output "database_secret_arn" {
  value = aws_secretsmanager_secret.database_url.arn
}
output "redis_secret_arn" {
  value = aws_secretsmanager_secret.redis_url.arn
}
output "api_task_definition_arn" {
  value = aws_ecs_task_definition.api.arn
}
output "web_task_definition_arn" {
  value = aws_ecs_task_definition.web.arn
}
output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}
output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}
