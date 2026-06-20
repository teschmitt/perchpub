output "instance_public_ip" {
  description = "Public IP of the PerchPub instance (point DNS / SSH here)."
  value       = openstack_compute_instance_v2.app.access_ip_v4
}

output "s3_endpoint" {
  description = "OVH S3 endpoint the app uses (GARAGE_ENDPOINT)."
  value       = "s3.${lower(var.region)}.io.cloud.ovh.net"
}

output "s3_bucket" {
  description = "Object storage bucket name (GARAGE_BUCKET_NAME)."
  value       = ovh_cloud_project_storage.media.name
}

output "s3_access_key_id" {
  description = "Scoped S3 access key id."
  value       = ovh_cloud_project_user_s3_credential.media.access_key_id
}

output "s3_secret_access_key" {
  description = "Scoped S3 secret access key."
  value       = ovh_cloud_project_user_s3_credential.media.secret_access_key
  sensitive   = true
}
