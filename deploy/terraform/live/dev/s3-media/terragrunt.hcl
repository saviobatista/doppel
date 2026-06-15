include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "../../../modules/s3-media"
}

inputs = {
  bucket_name = local.env.media_bucket
  tags        = merge(local.env.common_tags, { Component = "media" })
}
