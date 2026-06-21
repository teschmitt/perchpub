resource "openstack_compute_keypair_v2" "deploy" {
  name       = "perchpub-deploy"
  public_key = var.ssh_pubkey
}

# Egress hygiene + intent only — NOT trusted for ingress (§5). Host nftables
# (cloud-init) is the ingress enforcement mechanism.
resource "openstack_networking_secgroup_v2" "egress" {
  name        = "perchpub-egress"
  description = "Egress hygiene/intent only; ingress enforced host-side via nftables."
}

resource "openstack_blockstorage_volume_v3" "data" {
  name = "perchpub-data"
  size = var.volume_size_gb
}

resource "openstack_compute_instance_v2" "app" {
  name            = "perchpub"
  image_name      = var.image_name
  flavor_name     = var.flavor_name
  key_pair        = openstack_compute_keypair_v2.deploy.name
  security_groups = [openstack_networking_secgroup_v2.egress.name]

  network {
    name = "Ext-Net"
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    domain                   = var.domain
    owner_email              = var.owner_email
    repo_url                 = var.repo_url
    ssh_allowed_cidr         = var.ssh_allowed_cidr
    secret_key               = random_password.secret_key.result
    postgres_password        = random_password.postgres_password.result
    first_superuser_password = random_password.first_superuser_password.result
    step_ca_admin_password   = random_password.step_ca_admin_password.result
    enrollment_hmac_hex      = random_id.enrollment_hmac.hex
    s3_endpoint              = "s3.${lower(var.region)}.io.cloud.ovh.net"
    s3_region                = lower(var.region)
    s3_bucket                = var.bucket_name
    s3_key_id                = ovh_cloud_project_user_s3_credential.media.access_key_id
    s3_secret                = ovh_cloud_project_user_s3_credential.media.secret_access_key
  })
}

resource "openstack_compute_volume_attach_v2" "data" {
  instance_id = openstack_compute_instance_v2.app.id
  volume_id   = openstack_blockstorage_volume_v3.data.id
}
