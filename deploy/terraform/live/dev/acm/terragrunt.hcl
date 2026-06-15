include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/acm"
}

# Provider adicional para a conta mydatagent-shared (onde vive a zone DNS).
generate "provider_shared" {
  path      = "provider_shared.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  alias   = "shared"
  region  = "us-east-1"
  profile = "mydatagent-shared"
}
EOF
}

inputs = {
  domain_name               = "kortes.ai"
  subject_alternative_names = ["www.kortes.ai", "api.kortes.ai"]
  zone_id                   = "Z03503271ZKI1BVQSV1CZ"
  tags                      = merge(local.env.common_tags, { Component = "acm" })
}
