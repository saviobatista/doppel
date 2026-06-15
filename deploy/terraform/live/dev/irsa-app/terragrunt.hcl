include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/irsa-app"
}

dependency "media" {
  config_path = "../s3-media"
  mock_outputs = {
    bucket_arn = "arn:aws:s3:::${local.env.media_bucket}"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  role_name         = "kortes-app-dev"
  policy_name       = "kortes-s3-dev"
  oidc_provider_arn = local.env.eks_oidc_arn
  oidc_provider_url = local.env.eks_oidc_url
  namespace         = local.env.namespace
  service_account   = "kortes-app"
  media_bucket_arn  = dependency.media.outputs.bucket_arn
  tags              = merge(local.env.common_tags, { Component = "api" })
}
