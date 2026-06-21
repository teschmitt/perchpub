data "ovh_domain_zone" "root" {
  name = var.domain
}

locals {
  # "" subdomain == apex (@).
  a_records = {
    apex      = ""
    api       = "api"
    dashboard = "dashboard"
    adminer   = "adminer"
  }
}

resource "ovh_domain_zone_record" "a" {
  for_each = local.a_records

  zone      = data.ovh_domain_zone.root.name
  subdomain = each.value
  fieldtype = "A"
  ttl       = 600
  target    = openstack_compute_instance_v2.app.access_ip_v4
}
