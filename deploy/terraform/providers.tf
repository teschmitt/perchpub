terraform {
  required_version = ">= 1.6"

  required_providers {
    ovh = {
      source  = "ovh/ovh"
      version = "~> 2.0"
    }
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# OVH API credentials come from env vars (OVH_ENDPOINT, OVH_APPLICATION_KEY,
# OVH_APPLICATION_SECRET, OVH_CONSUMER_KEY) — see README bootstrap. Endpoint
# pinned to the EU region.
provider "ovh" {
  endpoint = "ovh-eu"
}

# OpenStack auth comes from a sourced openrc / clouds.yaml (OS_* env vars) —
# see README bootstrap.
provider "openstack" {}

provider "random" {}
