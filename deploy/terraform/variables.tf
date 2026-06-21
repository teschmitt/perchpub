variable "ovh_cloud_project_id" {
  description = "OVH Public Cloud project ID (service_name)."
  type        = string
}

variable "region" {
  # NOTE: this sets ONLY the object-storage region — the S3 bucket (storage.tf)
  # and the s3.<region>.io.cloud.ovh.net endpoint + SigV4 region (compute.tf).
  # It does NOT place the instance/volume: those inherit the OpenStack region
  # from OS_REGION_NAME in your sourced openrc. The two namespaces differ —
  # Frankfurt object storage is "DE" but its compute region is "DE1". Keep them
  # in the same geo (var.region=DE  ⇔  OS_REGION_NAME=DE1).
  description = "OVH object-storage region (uppercase geo code). EU default DE (Frankfurt)."
  type        = string
  default     = "DE"
}

variable "flavor_name" {
  description = "OpenStack flavor for the instance."
  type        = string
  default     = "b3-8"
}

variable "image_name" {
  description = "OpenStack image name."
  type        = string
  default     = "Debian 13"
}

variable "domain" {
  description = "Root domain hosted in the OVH DNS zone."
  type        = string
  default     = "perchpub.net"
}

variable "owner_email" {
  description = "Owner email: FIRST_SUPERUSER and Let's Encrypt ACME address."
  type        = string
}

variable "ssh_pubkey" {
  description = "SSH public key authorized on the instance."
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to reach SSH (22). WARNING: 0.0.0.0/0 exposes SSH to the world — narrow to your IP/32 in production."
  type        = string
  default     = "0.0.0.0/0"
}

variable "create_egress_secgroup" {
  # OVH provisions a tiny default security_group quota on fresh projects (often
  # just 1, already consumed by the mandatory "default" group), so creating this
  # one fails with OverQuota. It's egress-intent-only anyway — real ingress
  # filtering is done by host nftables (cloud-init) — so it defaults OFF and the
  # instance falls back to the "default" group. Flip to true only after raising
  # the security_group quota (OVH Control Panel → Quota and Regions → Increase).
  description = "Create the dedicated egress security group (needs security_group quota > 1)."
  type        = bool
  default     = false
}

variable "repo_url" {
  description = "Public git URL cloned on the box and built with compose."
  type        = string
  default     = "https://codeberg.org/perchpub/perchpub.git"
}

variable "repo_ref" {
  description = "Git ref (branch, tag, or commit SHA) checked out on the box. Pin to a tag/SHA for a reproducible instance replacement; a branch name tracks its HEAD."
  type        = string
  default     = "main"
}

variable "volume_size_gb" {
  description = "Block volume size (GB) mounted at /mnt/perchpub-data."
  type        = number
  default     = 40
}

variable "bucket_name" {
  description = "OVH Object Storage (S3) bucket for media + the TF-Lite model."
  type        = string
  default     = "perchpub-bucket"
}
