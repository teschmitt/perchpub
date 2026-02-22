# PerchPub

This is a work in progress. To be clear: nothing works yet and this project is under active development. Submit a PR or an issue if you want to help it along.

PerchPub is a self-hosted bird-feeder observation server built on top of [FastAPI](https://github.com/fastapi/fastapi).

The goal of the project is to:

- Receive photos (and optionally short videos) of birds visiting a feeder.
- Identify bird species using image recognition.
- Store and display observations for authenticated users.
- Optionally publish observations into the Fediverse via ActivityPub (so they can be followed from Mastodon, Pixelfed, etc.).

The overall system consists of:

- **Station software (Raspberry Pi)** – built in a separate project and responsible for capturing media at the feeder and sending it to this server.
- **PerchPub server (this repository)** – receives uploads, runs image classification, stores observations, and exposes them via an API and web UI.

A link to the Raspberry Pi station project will be added later.

## Backend: Observation, Classification, and Sharing

This repository contains the backend that powers PerchPub. At a high level, the backend:

- Exposes an authenticated HTTP API for stations and users.
- Manages users, API keys, stations, species, and observations in a relational database.
- Accepts media uploads (images/videos) for each observation.
- Schedules and tracks classification tasks for uploaded media.
- Optionally publishes new observations via ActivityPub.

The backend is organized around a few core concepts:

- **Users and authentication** – standard user accounts with secure password hashing, JWT-based authentication, and optional email-based flows inherited from the template.
- **Stations** – registered devices (e.g. Raspberry Pis) that are allowed to upload observations. Stations authenticate using API keys or tokens.
- **Uploads** – raw media files (images or videos) sent by stations.
- **Observations** – domain objects that connect an upload with a timestamp, a station, and later a species classification.
- **Species** – known bird species that can be referenced by observations.
- **Classification tasks** – background tasks that run image recognition for newly uploaded media and attach the result to an observation.

### API surface

The API is structured into versioned routes under `/api/v1`. It includes endpoints for:

- Managing users and authentication flows.
- Registering and managing stations.
- Creating uploads and observations from stations.
- Listing and querying observations and species.

These endpoints are implemented as FastAPI routers under `backend/app/api/routes`.

### Data model

The data model is implemented using SQLModel and lives under `backend/app/models`. The main models are:

- `User`, `Token`, and related authentication models.
- `Station` and `Enrollment` for managing devices.
- `Upload` and `Observation` for media and bird sightings.
- `Species` for known bird species.
- `ClassifyTask` for tracking image-recognition jobs.

Migrations are managed with Alembic and are stored under `backend/app/alembic`.

### Background processing

Classification and other non-blocking work is handled via background tasks defined in `backend/app/tasks.py`. These tasks are responsible for:

- Scheduling classification for new uploads.
- Updating observations with recognition results.
- Preparing data that can later be sent via ActivityPub.

### ActivityPub and Fediverse integration

PerchPub is intended to optionally publish new observations into the Fediverse:

- New observations can be exposed as ActivityPub activities.
- Fediverse users (e.g. Mastodon, Pixelfed) can follow the bird feeder as if it were an account.

The details of the ActivityPub integration are experimental and may evolve, but the goal is to make each station or server instance publish a stream of bird sightings.

## Built on Full Stack FastAPI Template

PerchPub uses the Full Stack FastAPI Template as its foundation. That provides:

- A FastAPI backend with SQLModel models, authentication, and migrations.
- A Docker Compose setup for running the stack locally or in production.
- Built-in testing, email-based password recovery, and reverse proxy configuration.

For more detailed technical information about running and developing the backend, see:

- Backend docs: [backend/README.md](./backend/README.md).
- Deployment docs: [deployment.md](./deployment.md).
- General development docs: [development.md](./development.md).

## License

The project is currently based on the Full Stack FastAPI Template, which is licensed under the terms of the MIT license.
