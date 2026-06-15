# Valores do ambiente dev (conta mydatagent-dev, cluster mda-development).
locals {
  stage      = "dev"
  region     = "us-east-1"
  account_id = "523083723230"

  namespace   = "kortes-dev"
  github_repo = "saviobatista/doppel"

  # OIDC providers já existentes na conta (referenciados, não criados).
  eks_oidc_arn    = "arn:aws:iam::523083723230:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/5748E6CB55EBA636EBE4E134838EBD24"
  eks_oidc_url    = "oidc.eks.us-east-1.amazonaws.com/id/5748E6CB55EBA636EBE4E134838EBD24"
  github_oidc_arn = "arn:aws:iam::523083723230:oidc-provider/token.actions.githubusercontent.com"

  media_bucket = "kortes-media-dev-us-east-1"

  common_tags = {
    Environment = "dev"
  }
}
