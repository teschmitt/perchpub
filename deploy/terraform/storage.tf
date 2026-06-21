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
}

# Least-privilege policy scoping the user to this one bucket.
resource "ovh_cloud_project_user_s3_policy" "media" {
  service_name = var.ovh_cloud_project_id
  user_id      = ovh_cloud_project_user.s3.id
  policy = jsonencode({
    statements = [
      {
        sid    = "perchpub-bucket-rw"
        effect = "allow"
        action = ["s3:*"]
        resource = [
          "arn:aws:s3:::${var.bucket_name}",
          "arn:aws:s3:::${var.bucket_name}/*",
        ]
      }
    ]
  })
}
