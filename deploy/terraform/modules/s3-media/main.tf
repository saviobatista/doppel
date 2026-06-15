# Bucket de mídia (real, AWS). Acesso via IRSA; presigned URLs no browser.
variable "bucket_name" {
  type        = string
  description = "Nome global do bucket (ex.: kortes-media-dev-us-east-1)."
}
variable "cors_origins" {
  type        = list(string)
  description = "Origens permitidas para presigned URLs no browser."
  default     = ["https://kortes.ai", "https://www.kortes.ai"]
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_s3_bucket" "media" {
  bucket = var.bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.cors_origins
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}

output "bucket_arn" {
  value = aws_s3_bucket.media.arn
}
output "bucket_name" {
  value = aws_s3_bucket.media.bucket
}
