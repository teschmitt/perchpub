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
   `/mnt/perchpub-data`, bound into the `pgdata` / `redis` / `step-ca` volumes).

---

## 5. Notes & teardown

- **State**: local + gitignored (D5). Keep `terraform.tfstate` private and
  backed up — it holds every generated secret.
- **Region**: one knob, `var.region` (default `GRA`, uppercase OVH API casing).
  The S3 signature region is derived lowercase (`gra`) and rendered as
  `GARAGE_REGION`. Change `region` to `DE` / `SBG` / `WAW` to move regions.
- **SSH exposure**: `ssh_allowed_cidr` defaults to `0.0.0.0/0`. Narrow it to
  your address; the host `nftables` firewall (cloud-init) is the ingress
  enforcement mechanism — OVH security groups do **not** reliably filter
  `Ext-Net` ingress, so the attached security group is egress-intent only.

  ```bash
  terraform destroy
  ```

  tears down the instance, block volume, DNS records, and the S3 bucket.
  **Objects in the bucket are deleted — back up media first.** The OVH DNS
  zone itself and the registrar NS are left untouched (created manually).
