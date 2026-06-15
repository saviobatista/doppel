# Cert ACM cross-account: emitido na conta do ALB (mydatagent-dev, provider
# default) e validado por DNS na zone que vive em mydatagent-shared (aws.shared).
variable "domain_name" {
  type        = string
  description = "Domínio principal (ex.: kortes.ai)."
}
variable "subject_alternative_names" {
  type        = list(string)
  description = "SANs (ex.: www.kortes.ai, api.kortes.ai)."
}
variable "zone_id" {
  type        = string
  description = "ID da hosted zone kortes.ai (conta mydatagent-shared)."
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_acm_certificate" "this" {
  domain_name               = var.domain_name
  subject_alternative_names = var.subject_alternative_names
  validation_method         = "DNS"
  tags                      = var.tags
  lifecycle {
    create_before_destroy = true
  }
}

# Registros de validação na zone (conta mydatagent-shared, provider aliased).
resource "aws_route53_record" "validation" {
  for_each = {
    for dvo in aws_acm_certificate.this.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }
  provider        = aws.shared
  zone_id         = var.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for r in aws_route53_record.validation : r.fqdn]
}

output "certificate_arn" {
  value = aws_acm_certificate_validation.this.certificate_arn
}
