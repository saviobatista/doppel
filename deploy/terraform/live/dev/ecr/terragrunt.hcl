include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/ecr"
}

inputs = {
  repos = ["kortes-api", "kortes-web"]
  tags  = merge(local.env.common_tags, { Component = "ecr" })
}
