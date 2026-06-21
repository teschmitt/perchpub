resource "openstack_compute_keypair_v2" "deploy" {
  name       = "perchpub-deploy"
  public_key = var.ssh_pubkey
}

# Egress hygiene + intent only — NOT trusted for ingress (§5). Host nftables
# (cloud-init) is the ingress enforcement mechanism. Gated OFF by default: OVH's
# fresh-project security_group quota is typically 1 (consumed by the mandatory
# "default" group), so creating this 409s with OverQuota. See
# var.create_egress_secgroup.
resource "openstack_networking_secgroup_v2" "egress" {
  count       = var.create_egress_secgroup ? 1 : 0
  name        = "perchpub-egress"
  description = "Egress hygiene/intent only; ingress enforced host-side via nftables."
}

resource "openstack_blockstorage_volume_v3" "data" {
  name = "perchpub-data"
  size = var.volume_size_gb

  # Holds Postgres + the step-ca device CA + acme.json (bind-mounted via
  # docker-compose.prod.yml). Guard against an accidental `terraform destroy`
  # wiping it; intentional teardown means removing this block first (README §5).
  lifecycle {
    prevent_destroy = true
  }
}

resource "openstack_compute_instance_v2" "app" {
  name            = "perchpub"
  image_name      = var.image_name
  flavor_name     = var.flavor_name
  key_pair        = openstack_compute_keypair_v2.deploy.name
  # Splat is empty (not an index error) when the secgroup is gated off, so the
  # ternary safely falls back to the project's "default" group.
  security_groups = var.create_egress_secgroup ? openstack_networking_secgroup_v2.egress[*].name : ["default"]

  network {
    name = "Ext-Net"
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    domain                   = var.domain
    owner_email              = var.owner_email
    repo_url                 = var.repo_url
    repo_ref                 = var.repo_ref
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
