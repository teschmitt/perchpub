# PerchPub — Terraform / OVH deployment

Provisions the whole PerchPub stack on a single OVH Public Cloud instance:
instance + attached block volume + S3 object storage (media + the TF-Lite
model) + OVH-managed DNS + Terraform-generated app secrets. `cloud-init`
installs Docker, mounts the block volume, clones the repo, renders
`/opt/perchpub/.env.prod`, and brings the existing Compose stack up with the
in-stack Traefik edge (`docker-compose.prod.yml`): HTTPS via Let's Encrypt on
`:443` and station mTLS on `:8443`.

> **State is local and gitignored** (`*.tfstate*`, `*.tfvars`, `.terraform/`).
> The generated secrets live only in that local state and on the instance —
> back the state file up somewhere safe and private.

---

## 1. Prerequisites

- **Terraform** `>= 1.6`.
- An **OVH account** with a **Public Cloud project** and billing enabled.
- An **OVH API credential** (application key / secret / consumer key) with
  rights on the project — create at <https://api.ovh.com/createToken/> or via
  the OVH Control Panel.
- OpenStack credentials for the project: a downloaded `openrc` file **or** a
  `clouds.yaml` (OVH Control Panel → Public Cloud → Users → *Download OpenStack
  RC / config*).
- An SSH keypair (the public key goes into `terraform.tfvars`).

---

## 2. One-time manual bootstrap (D2 / §11)

These steps are **not** managed by Terraform and must be done once before the
first `apply`.

1. **OVH API credentials** — create them, then export into your shell:

   ```bash
   export OVH_ENDPOINT=ovh-eu
   export OVH_APPLICATION_KEY=...
   export OVH_APPLICATION_SECRET=...
   export OVH_CONSUMER_KEY=...
   ```

2. **OpenStack auth** — source the openrc (or place `clouds.yaml` where the
   provider finds it). This sets the `OS_*` env vars the `openstack` provider
   uses:

   ```bash
   source ~/Downloads/openrc.sh        # prompts for the OpenStack user password
   ```

   **`OS_REGION_NAME` decides where the instance + block volume land** — it is
   *not* `var.region`. Pick the region matching `var.region`'s geo when you
   download the openrc (Frankfurt compute = `DE1`, paired with object-storage
   `var.region = DE`). Mismatching them puts the VM and the bucket in different
   datacenters. Verify with `echo "$OS_REGION_NAME"` after sourcing.

3. **Public Cloud project id** — copy the project's `service_name` (a 32-char
   hex id) into `ovh_cloud_project_id` in `terraform.tfvars`.

4. **DNS zone + registrar NS repoint** — create the OVH **DNS zone** for
   `perchpub.net` (Control Panel → Web Cloud → Domain names, or the OVH API),
   then **repoint the registrar's nameservers** (Namecheap) to OVH's
   (`ns##.ovh.net` / `dns##.ovh.net`). Wait for propagation:

   ```bash
   dig NS perchpub.net +short
   ```

   Terraform manages **records inside** the zone (`dns.tf`); it does **not**
   create the zone or touch registrar NS.

5. **tfvars** — copy the example and fill it in:

   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # set ovh_cloud_project_id, owner_email, ssh_pubkey
   # strongly recommended: set ssh_allowed_cidr to your IP/32
   ```

---

## 3. Apply

```bash
cd deploy/terraform
terraform init
terraform plan
terraform apply
```

`apply` creates: the generated secrets (`secrets.tf`), the S3 bucket + scoped
user/credential/policy (`storage.tf`), the keypair + egress security group +
block volume + instance + volume attachment (`compute.tf`), and the DNS A
records `@` / `api` / `dashboard` / `adminer` (`dns.tf`). cloud-init then brings
the stack up on the box (first boot also builds images, so allow a few
minutes).

> **No `apply` runs in CI.** It needs real OVH credentials + billing; the IaC
> is gated in CI on `terraform fmt -check` + `terraform validate` + `shellcheck`
> only.

Useful outputs after apply:

```bash
terraform output instance_public_ip
terraform output s3_endpoint
terraform output s3_bucket
terraform output -raw s3_secret_access_key   # sensitive
```

---

## 4. Post-apply smoke test (§13)

1. **HTTPS + valid certs** — both resolve with a valid Let's Encrypt cert:

   ```bash
   curl -sSf https://api.perchpub.net/docs >/dev/null && echo "api ok"
   curl -sSf https://dashboard.perchpub.net >/dev/null && echo "dashboard ok"
   ```

2. **First-superuser login** — seeded by `prestart`. The password is the
   Terraform-generated one rendered into the box's `/opt/perchpub/.env.prod`
   (read it there, or from `terraform output`):

   ```bash
   curl -sSf -X POST https://api.perchpub.net/api/v1/login/access-token \
     -d "username=<owner_email>&password=<FIRST_SUPERUSER_PASSWORD>"
   ```

3. **Station mTLS upload** — enroll a station, then `POST` to the mTLS
   entrypoint on `:8443` with the device client cert; confirm a classification
   task runs (worker) and the object lands in the OVH bucket:

   ```bash
   curl -sSf https://api.perchpub.net:8443/api/v1/upload/ \
     --cert device.crt --key device.key -F "file=@clip.mp4"
   ```

   - **caFiles note (from `deploy/traefik/dynamic/dynamic.yml`):** if the
     upload fails the TLS handshake with `tls: unknown certificate authority`,
     the device leaf chains differently than assumed — inspect the `step-ca`
     volume's `certs/` and adjust the `caFiles` list in `dynamic.yml`.

4. **Persistence** — reboot or replace the instance and confirm Postgres data
   and the step-ca root survive (they live on the block volume at
   `/mnt/perchpub-data`, bound into the `pgdata` / `redis` / `step-ca` /
   `traefik-certificates` volumes).

---

## 5. Notes & teardown

- **State**: local + gitignored (D5). Keep `terraform.tfstate` private and
  backed up — it holds every generated secret.
- **Region** — there are **two** region namespaces, and they use different
  codes for the same datacenter:
  - `var.region` (default `DE` / Frankfurt, uppercase geo code) sets **object
    storage only** — the S3 bucket (`storage.tf`) and the
    `s3.<region>.io.cloud.ovh.net` endpoint + lowercase SigV4 region (`de`)
    rendered as `GARAGE_REGION`. Move it with `GRA` / `SBG` / `WAW`.
  - `OS_REGION_NAME` (from your sourced openrc, §2.2) sets the **instance +
    block volume** region — Frankfurt is `DE1`, not `DE`. The `compute.tf`
    OpenStack resources take no explicit `region`, so they follow this.

  To move the whole stack to a new datacenter you must change **both**, keeping
  them in the same geo (e.g. `var.region = DE` with `OS_REGION_NAME = DE1`).
- **SSH exposure**: `ssh_allowed_cidr` defaults to `0.0.0.0/0`. Narrow it to
  your address; the host `nftables` firewall (cloud-init) is the ingress
  enforcement mechanism — OVH security groups do **not** reliably filter
  `Ext-Net` ingress, so the attached security group is egress-intent only.

- **Redeploy / replace the instance** — the supported "deploy anew" path,
  and it **preserves data**. The block volume (Postgres + step-ca device CA +
  acme.json) survives an instance rebuild because it lives on
  `/mnt/perchpub-data`. Replace only the box:

  ```bash
  terraform apply -replace=openstack_compute_instance_v2.app
  ```

  cloud-init re-mounts the existing volume (it reformats *only* a blank disk,
  `cloud-init.yaml.tftpl`), re-renders `.env.prod` from the **same** secrets in
  state, checks out `var.repo_ref` (default `main` — pin to a tag/SHA for a
  reproducible rebuild), and brings the stack back up against the existing DB +
  CA. The public IP changes; `dns.tf` updates the A records, so allow for DNS
  TTL before the smoke test passes.

  > **Secrets live in Terraform state; data lives on the volume — they must
  > stay in sync.** If you lose or restore-stale the local state, the
  > regenerated `POSTGRES_PASSWORD` / `STEP_CA_ADMIN_PASSWORD` no longer match
  > the surviving volume and the backend will refuse to boot (prestart and
  > `step-ca-provisioner-init` fail auth). Back up `terraform.tfstate`.

- **Teardown** — the block volume and the S3 bucket carry `prevent_destroy`
  (`compute.tf` / `storage.tf`), so `terraform destroy` **refuses by design**,
  protecting the DB, the device CA, and all media from an accidental wipe. To
  intentionally tear everything down, remove those two `lifecycle` blocks
  first, then run `terraform destroy`. **Back up media + a `pg_dump` first** —
  the bucket objects and the volume are then deleted for good. The OVH DNS zone
  itself and the registrar NS are left untouched (created manually).
