# TBench Runner Terraform Variables

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "tbench-runner"
}

variable "environment" {
  description = "Environment (development, staging, production)"
  type        = string
  default     = "production"
}

# VPC
variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}

# Database
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.small"
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "tbench"
  sensitive   = true
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

# Redis
variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.small"
}

# ECS
variable "api_cpu" {
  description = "API task CPU units"
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "API task memory (MiB)"
  type        = number
  default     = 512
}

variable "api_desired_count" {
  description = "Number of API tasks"
  type        = number
  default     = 2
}

variable "worker_cpu" {
  description = "Worker task CPU units"
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Worker task memory (MiB)"
  type        = number
  default     = 2048
}

variable "worker_desired_count" {
  description = "Number of worker tasks"
  type        = number
  default     = 4
}

# Secrets
variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

