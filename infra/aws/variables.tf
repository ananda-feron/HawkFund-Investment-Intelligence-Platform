variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "project_name" {
  type    = string
  default = "hawkfund"
}
variable "environment" {
  type    = string
  default = "production"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "certificate_arn" { type = string }
variable "web_origin" { type = string }
variable "allowed_hosts" { type = string }
variable "api_image" { type = string }
variable "web_image" { type = string }
variable "desired_count" {
  type    = number
  default = 2
}
variable "api_cpu" {
  type    = number
  default = 512
}
variable "api_memory" {
  type    = number
  default = 1024
}
variable "web_cpu" {
  type    = number
  default = 256
}
variable "web_memory" {
  type    = number
  default = 512
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}
variable "cache_node_type" {
  type    = string
  default = "cache.t4g.micro"
}
variable "alarm_email" {
  type    = string
  default = ""
}
variable "log_retention_days" {
  type    = number
  default = 90
}
