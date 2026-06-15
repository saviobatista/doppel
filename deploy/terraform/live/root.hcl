# Config raiz do Terragrunt: backend S3 remoto + provider AWS + tags padrão.
locals {
  region       = "us-east-1"
  profile      = "mydatagent-dev"
  state_bucket = "kortes-tfstate-dev-us-east-1"
}

remote_state {
  backend = "s3"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket  = local.state_bucket
    key     = "${path_relative_to_include()}/terraform.tfstate"
    region  = local.region
    profile = local.profile
    encrypt = true
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = "${local.region}"
  profile = "${local.profile}"
  default_tags {
    tags = {
      Project   = "kortes"
      ManagedBy = "terraform"
    }
  }
}
EOF
}
