# IRSA: role assumida pelo ServiceAccount kortes-app (namespace kortes-dev)
# via o OIDC provider do cluster EKS. Dá acesso S3 ao bucket de mídia.
variable "role_name" {
  type        = string
  description = "Nome da role IRSA (ex.: kortes-app-dev)."
}
variable "policy_name" {
  type        = string
  description = "Nome da policy de S3 (ex.: kortes-s3-dev)."
}
variable "oidc_provider_arn" {
  type        = string
  description = "ARN do OIDC provider do EKS."
}
variable "oidc_provider_url" {
  type        = string
  description = "URL do OIDC do EKS, sem https:// (host/id...)."
}
variable "namespace" {
  type    = string
  default = "kortes-dev"
}
variable "service_account" {
  type    = string
  default = "kortes-app"
}
variable "media_bucket_arn" {
  type        = string
  description = "ARN do bucket de mídia."
}
variable "tags" {
  type    = map(string)
  default = {}
}

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "s3" {
  statement {
    sid       = "ObjectRW"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.media_bucket_arn}/*"]
  }
  statement {
    sid       = "BucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.media_bucket_arn]
  }
}

resource "aws_iam_policy" "s3" {
  name   = var.policy_name
  policy = data.aws_iam_policy_document.s3.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "s3" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.s3.arn
}

output "role_arn" {
  value = aws_iam_role.app.arn
}
