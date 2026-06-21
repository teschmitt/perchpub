variable "ovh_cloud_project_id" {
  description = "OVH Public Cloud project ID (service_name)."
  type        = string
}

variable "region" {
  description = "OVH region (API casing, uppercase). EU default GRA."
  type        = string
  default     = "GRA"
}

variable "flavor_name" {
  description = "OpenStack flavor for the instance."
  type        = string
  default     = "b3-8"
}

variable "image_name" {
  description = "OpenStack image name."
  type        = string
  default     = "Debian 12"
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

variable "repo_url" {
  description = "Public git URL cloned on the box and built with compose."
  type        = string
  default     = "https://codeberg.org/perchpub/perchpub.git"
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
