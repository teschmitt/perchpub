# PerchPub - Deployment

You can deploy the project using Docker Compose to a remote server.

This project expects you to have a Traefik proxy handling communication to the outside world and HTTPS certificates.

You can use CI/CD (continuous integration and continuous deployment) systems to deploy automatically, there are already configurations to do it with GitHub Actions.

But you have to configure a couple things first. 🤓

## Preparation

* Have a remote server ready and available.
* Configure the DNS records of your domain to point to the IP of the server you just created.
* Configure a wildcard subdomain for your domain, so that you can have multiple subdomains for different services, e.g. `*.perchpub.net`. This will be useful for accessing different components, like `dashboard.perchpub.net`, `api.perchpub.net`, `traefik.perchpub.net`, `adminer.perchpub.net`, etc. And also for `staging`, like `dashboard.staging.perchpub.net`, `adminer.staging.perchpub.net`, etc.
* Install and configure [Docker](https://docs.docker.com/engine/install/) on the remote server (Docker Engine, not Docker Desktop).

## Public Traefik

We need a Traefik proxy to handle incoming connections and HTTPS certificates.

You need to do these next steps only once.

### Traefik Docker Compose

* Create a remote directory to store your Traefik Docker Compose file:

```bash
mkdir -p /srv/traefik-public/
```

Copy the Traefik Docker Compose file to your server. You could do it by running the command `rsync` in your local terminal:

```bash
rsync -a docker-compose.traefik.yml perchpub.net:/root/code/traefik-public/
```

### Traefik Public Network

This Traefik will expect a Docker "public network" named `traefik-public` to communicate with your stack(s).

This way, there will be a single public Traefik proxy that handles the communication (HTTP and HTTPS) with the outside world, and then behind that, you could have one or more stacks with different domains, even if they are on the same single server.

To create a Docker "public network" named `traefik-public` run the following command in your remote server:

```bash
docker network create traefik-public
```

### Traefik Environment Variables

Create an `.env` file in the same directory as the compose file with the following env variables set:

```
DOMAIN=perchpub.net
USERNAME=thomas
HASHED_PASSWORD='$apr1$....'
EMAIL=your-email-for-lets-encrypt@...
```

Hash your password with `openssl passwd -apr1 $PASSWORD`


### Start the Traefik Docker Compose

Go to the directory where you copied the Traefik Docker Compose file in your remote server:

```bash
cd /srv/traefik-public/
mv docker-compose.traefik.yml docker-compose.yml
```

Now with the environment variables set and the `docker-compose.yml` in place, you can start the Traefik Docker Compose running the following command:

```bash
docker compose up -d
```

## Deploy the FastAPI Project

Now that you have Traefik in place you can deploy your FastAPI project with Docker Compose.

**Note**: You might want to jump ahead to the section about Continuous Deployment with GitHub Actions.

## Environment Variables

You need to set some environment variables first.

Set the `ENVIRONMENT`, by default `local` (for development), but when deploying to a server you would put something like `staging` or `production`:

```bash
export ENVIRONMENT=production
```

Set the `DOMAIN`, by default `localhost` (for development), but when deploying you would use your own domain, for example:

```bash
export DOMAIN=perchpub.net
```

You can set several variables, like:

* `PROJECT_NAME`: The name of the project, used in the API for the docs and emails.
* `STACK_NAME`: The name of the stack used for Docker Compose labels and project name, this should be different for `staging`, `production`, etc. You could use the same domain replacing dots with dashes, e.g. `fastapi-project-example-com` and `staging-fastapi-project-example-com`.
* `BACKEND_CORS_ORIGINS`: A list of allowed CORS origins separated by commas.
* `SECRET_KEY`: The secret key for the FastAPI project, used to sign tokens.
* `FIRST_SUPERUSER`: The email of the first superuser, this superuser will be the one that can create new users.
* `FIRST_SUPERUSER_PASSWORD`: The password of the first superuser.
* `SMTP_HOST`: The SMTP server host to send emails, this would come from your email provider (E.g. Mailgun, Sparkpost, Sendgrid, etc).
* `SMTP_USER`: The SMTP server user to send emails.
* `SMTP_PASSWORD`: The SMTP server password to send emails.
* `EMAILS_FROM_EMAIL`: The email account to send emails from.
* `POSTGRES_SERVER`: The hostname of the PostgreSQL server. You can leave the default of `db`, provided by the same Docker Compose. You normally wouldn't need to change this unless you are using a third-party provider.
* `POSTGRES_PORT`: The port of the PostgreSQL server. You can leave the default. You normally wouldn't need to change this unless you are using a third-party provider.
* `POSTGRES_PASSWORD`: The Postgres password.
* `POSTGRES_USER`: The Postgres user, you can leave the default.
* `POSTGRES_DB`: The database name to use for this application. You can leave the default of `app`.
* `SENTRY_DSN`: The DSN for Sentry, if you are using it.

## GitHub Actions Environment Variables

There are some environment variables only used by GitHub Actions that you can configure:

* `LATEST_CHANGES`: Used by the GitHub Action [latest-changes](https://github.com/tiangolo/latest-changes) to automatically add release notes based on the PRs merged. It's a personal access token, read the docs for details.
* `SMOKESHOW_AUTH_KEY`: Used to handle and publish the code coverage using [Smokeshow](https://github.com/samuelcolvin/smokeshow), follow their instructions to create a (free) Smokeshow key.

### Generate secret keys

`SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD`, `POSTGRES_PASSWORD`, `ENROLLMENT_HMAC_KEY_HEX`, and `STEP_CA_ADMIN_PASSWORD` in `.env.prod` need real values before first deploy. Generate with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# for ENROLLMENT_HMAC_KEY_HEX use bytes(32).hex():
python -c "import secrets; print(secrets.token_bytes(32).hex())"
```

`STEP_CA_ADMIN_PASSWORD` is currently **not load-bearing on first prod boot** — see "Setting up Perchpub services / step-ca first boot" below. Track this under FU-19.

The `GARAGE_KEY_ID` / `GARAGE_SECRET` values target a self-hosted Garage instance (`blob-storage:3900`) that's currently commented out in `docker-compose.yml`; replace them with real values once that service is wired in.

### Deploy with Docker Compose

With `.env.prod` populated, deploy with:

```bash
docker compose --env-file .env.prod -f docker-compose.yml up -d
```

`--env-file .env.prod` is the single source of truth for both compose-parse-time `${VAR}` substitution (image tags, Traefik labels) and per-service `env_file:` injection. `-f docker-compose.yml` excludes `docker-compose.override.yml` so dev-only services (mailcatcher, playwright, the proxy override) don't come along.

## Continuous Deployment (CD)

You can use GitHub Actions to deploy your project automatically. 😎

You can have multiple environment deployments.

There are already two environments configured, `staging` and `production`. 🚀

### Install GitHub Actions Runner

* On your remote server, create a user for your GitHub Actions:

```bash
sudo adduser github
```

* Add Docker permissions to the `github` user:

```bash
sudo usermod -aG docker github
```

* Temporarily switch to the `github` user:

```bash
sudo su - github
```

* Go to the `github` user's home directory:

```bash
cd
```

* [Install a GitHub Action self-hosted runner following the official guide](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners#adding-a-self-hosted-runner-to-a-repository).

* When asked about labels, add a label for the environment, e.g. `production`. You can also add labels later.

After installing, the guide would tell you to run a command to start the runner. Nevertheless, it would stop once you terminate that process or if your local connection to your server is lost.

To make sure it runs on startup and continues running, you can install it as a service. To do that, exit the `github` user and go back to the `root` user:

```bash
exit
```

After you do it, you will be on the previous user again. And you will be on the previous directory, belonging to that user.

Before being able to go the `github` user directory, you need to become the `root` user (you might already be):

```bash
sudo su
```

* As the `root` user, go to the `actions-runner` directory inside of the `github` user's home directory:

```bash
cd /home/github/actions-runner
```

* Install the self-hosted runner as a service with the user `github`:

```bash
./svc.sh install github
```

* Start the service:

```bash
./svc.sh start
```

* Check the status of the service:

```bash
./svc.sh status
```

You can read more about it in the official guide: [Configuring the self-hosted runner application as a service](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service).

### Set Secrets

On your repository, configure secrets for the environment variables you need, the same ones described above, including `SECRET_KEY`, etc. Follow the [official GitHub guide for setting repository secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions#creating-secrets-for-a-repository).

The current Github Actions workflows expect these secrets:

* `DOMAIN_PRODUCTION`
* `DOMAIN_STAGING`
* `STACK_NAME_PRODUCTION`
* `STACK_NAME_STAGING`
* `EMAILS_FROM_EMAIL`
* `FIRST_SUPERUSER`
* `FIRST_SUPERUSER_PASSWORD`
* `POSTGRES_PASSWORD`
* `SECRET_KEY`
* `LATEST_CHANGES`
* `SMOKESHOW_AUTH_KEY`

## GitHub Action Deployment Workflows

There are GitHub Action workflows in the `.github/workflows` directory already configured for deploying to the environments (GitHub Actions runners with the labels):

* `staging`: after pushing (or merging) to the branch `main`.
* `production`: after publishing a release.

If you need to add extra environments you could use those as a starting point.

## URLs

### Main Traefik Dashboard

Traefik UI: `https://traefik.perchpub.net`

### Production

- Frontend: `https://dashboard.perchpub.net`
- Backend API docs: `https://api.perchpub.net/docs`
- Backend API base URL: `https://api.perchpub.net`
- Adminer: `https://adminer.perchpub.net`

### Staging

- Frontend: `https://dashboard.staging.perchpub.net`
- Backend API docs: `https://api.staging.perchpub.net/docs`
- Backend API base URL: `https://api.staging.perchpub.net`
- Adminer: `https://adminer.staging.perchpub.net`


## Setting up Perchpub services

### Persisting classification data in S3

Models and labels must be made available in the S3 storage. Let Perchpub know where they are through the `CLASSIFICATION_MODEL_OBJECT_NAME` and `CLASSIFICATION_LABELS_OBJECT_NAME` env vars.

### Setting up the CA for mTLS

The dev/prod stacks both ship a `step-ca-provisioner-init` container that automates the historical manual recipe (CA bootstrap → provisioner add → JWK extract). On first `up -d` it idempotently creates the `backend-device-enrollment` JWK provisioner against the running CA and writes the decrypted private JWK to the `step-ca` named volume at `/home/step/backend-provisioner.jwk`. The backend mounts that file (subpath-narrow per FU-13) and the `certs/` dir; it never sees the CA root keys or the admin password.

Backend reads `STEP_CA_JWK_PATH=/home/step-ca/backend-provisioner.jwk` and derives the JWK's `kid` at runtime via `PyJWK.key_id`. There is no `STEP_CA_PROVISIONER_KID` env var to paste; mTLS-03 dropped it.

#### step-ca first boot

step-ca's auto-init generates an admin password on first boot and prints it to logs:

```bash
docker compose --env-file .env.prod -f docker-compose.yml up -d step-ca
docker compose --env-file .env.prod -f docker-compose.yml logs step-ca | grep -i "administrative password"
```

**Capture that value and paste it into `.env.prod` as `STEP_CA_ADMIN_PASSWORD` before bringing up the rest of the stack.** Until [FU-19](FOLLOWUPS.md) lands (wiring `DOCKER_STEPCA_INIT_PASSWORD: ${STEP_CA_ADMIN_PASSWORD}` into the step-ca service), the password is generated by step-ca itself, not read from the env file — so the env value has to be updated *after* first boot, not before. `step-ca-provisioner-init` reads `STEP_CA_ADMIN_PASSWORD` to authenticate to the admin API, so a mismatch fails the init container and blocks `backend` (which `depends_on: step-ca-provisioner-init: service_completed_successfully`).

Then bring up the rest:

```bash
docker compose --env-file .env.prod -f docker-compose.yml up -d
```

Verify:

```bash
docker compose --env-file .env.prod -f docker-compose.yml exec step-ca step ca provisioner list
```

You should see `admin` (auto-init) and `backend-device-enrollment` (the init container's work).

#### Manual recovery / inspection

```bash
# Inspect or rotate the admin provisioner manually:
docker compose --env-file .env.prod -f docker-compose.yml exec step-ca step ca token admin

# Check what file the backend is actually reading:
docker compose --env-file .env.prod -f docker-compose.yml exec backend ls -la /home/step-ca/
# Should show only `backend-provisioner.jwk` and `certs/` — not `secrets/` (FU-13).
```

The backend never needs the admin password directly; only `step-ca-provisioner-init` does, and only on first boot (subsequent runs short-circuit because the provisioner already exists).
