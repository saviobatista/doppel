# Role assumida pelo GitHub Actions (OIDC) para push no ECR. Sem chave estática.
variable "role_name" {
  type        = string
  description = "Nome da role de CI (ex.: kortes-ci-dev)."
}
variable "github_oidc_arn" {
  type        = string
  description = "ARN do OIDC provider do GitHub (já existente na conta)."
}
variable "subject_claims" {
  type        = list(string)
  description = "sub claims OIDC exatos autorizados (refs/environments; sem wildcard)."
}
variable "ecr_repo_arns" {
  type        = list(string)
  description = "ARNs dos repositórios ECR onde o CI pode dar push."
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
      identifiers = [var.github_oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = var.subject_claims
    }
  }
}

resource "aws_iam_role" "ci" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "ecr" {
  statement {
    sid       = "Auth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid    = "Push"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = var.ecr_repo_arns
  }
}

resource "aws_iam_role_policy" "ecr" {
  name   = "${var.role_name}-ecr"
  role   = aws_iam_role.ci.id
  policy = data.aws_iam_policy_document.ecr.json
}

output "role_arn" {
  value = aws_iam_role.ci.arn
}
