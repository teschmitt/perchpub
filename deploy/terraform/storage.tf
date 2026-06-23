# Object storage for media + the TF-Lite model (D8: type "standard"; the
# high_performance class uses EXPRESS_ONEZONE which breaks Minio's default
# upload path). Pattern mirrors mastodon/terraform-ovh-s3.

# A dedicated Public Cloud user holding the S3 credential.
resource "ovh_cloud_project_user" "s3" {
  service_name = var.ovh_cloud_project_id
  description  = "perchpub-s3-${lower(var.region)}"
  role_names   = ["objectstore_operator"]
}

# S3-compatible access key / secret for the user above.
resource "ovh_cloud_project_user_s3_credential" "media" {
  service_name = var.ovh_cloud_project_id
  user_id      = ovh_cloud_project_user.s3.id
}

# The bucket itself. Schema confirmed against ovh/ovh v2.14.0
# (`terraform providers schema -json`): required args are `region_name`
# (uppercase OVH region) + `name`; `service_name` is the project id. This
# resource exposes NO performance-class/`high_performance` selector — it
# provisions a Standard S3 bucket, so the D8 concern (avoid EXPRESS_ONEZONE,
# which breaks Minio's default upload path) is satisfied by construction.
# `versioning` is an optional+computed nested attribute (status enum is the
# S3 standard enabled/suspended — there is no "disabled"); omitting it leaves
# the bucket un-versioned, the intended default.
resource "ovh_cloud_project_storage" "media" {
  service_name = var.ovh_cloud_project_id
  region_name  = var.region
  name         = var.bucket_name

  # Media objects are user data; guard against an accidental `terraform
  # destroy` deleting the bucket. Intentional teardown means removing this
  # block first (README §5).
  lifecycle {
    prevent_destroy = true
  }
}

# Least-privilege policy scoping the user to this one bucket.
#
# OVH expects the AWS-IAM-style schema with CAPITALIZED keys
# (Statement/Sid/Effect/Action/Resource) and Effect "Allow". Lowercase keys
# (statements/effect/action/resource) are silently dropped as unknown, leaving
# an EMPTY policy ({"Statement":[]} in state) — which denies every S3 action
# and surfaces as AccessDenied on upload. No Version field on OVH.
resource "ovh_cloud_project_user_s3_policy" "media" {
  service_name = var.ovh_cloud_project_id
  user_id      = ovh_cloud_project_user.s3.id
  policy = jsonencode({
    Statement = [
      {
        Sid    = "perchpub-bucket-rw"
        Effect = "Allow"
        Action = ["s3:*"]
        Resource = [
          "arn:aws:s3:::${var.bucket_name}",
          "arn:aws:s3:::${var.bucket_name}/*",
        ]
      }
    ]
  })
}
