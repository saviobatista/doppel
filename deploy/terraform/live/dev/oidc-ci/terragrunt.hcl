include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/oidc-ci"
}

dependency "ecr" {
  config_path = "../ecr"
  mock_outputs = {
    repository_arns = [
      "arn:aws:ecr:${local.env.region}:${local.env.account_id}:repository/kortes-api",
      "arn:aws:ecr:${local.env.region}:${local.env.account_id}:repository/kortes-web",
    ]
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  role_name       = "kortes-ci-dev"
  github_oidc_arn = local.env.github_oidc_arn
  # sub claims exatos (sem wildcard): só os branches que rodam o CI de deploy.
  subject_claims = [
    "repo:${local.env.github_repo}:ref:refs/heads/main",
    "repo:${local.env.github_repo}:ref:refs/heads/feature/v2beta",
  ]
  ecr_repo_arns = dependency.ecr.outputs.repository_arns
  tags          = merge(local.env.common_tags, { Component = "ci" })
}
