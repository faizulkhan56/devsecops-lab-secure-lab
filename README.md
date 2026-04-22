# DevSecOps Flask Lab — Secure User Service

A small but complete **DevSecOps** example: a **Flask** user API behind **Nginx**, backed by **PostgreSQL**, observable with **Sentry** and **Uptime Kuma**, with **GitHub Actions** running tests, **SonarCloud** quality analysis, **Trivy** security scans, and **EC2** deployment via **Docker Compose**.

---

## Table of contents

1. [Project overview](#1-project-overview)  
2. [Architecture and design choices](#2-architecture-and-design-choices)  
3. [Repository layout](#3-repository-layout)  
4. [Prerequisites](#4-prerequisites)  
5. [Local deployment](#5-local-deployment)  
6. [SonarCloud integration (detailed)](#6-sonarcloud-integration-detailed)  
7. [Sentry integration (detailed)](#7-sentry-integration-detailed)  
8. [Uptime Kuma](#8-uptime-kuma)  
9. [CI/CD pipeline overview](#9-cicd-pipeline-overview)  
10. [EC2 preparation](#10-ec2-preparation)  
11. [GitHub secrets reference](#11-github-secrets-reference)  
12. [Deploy script behavior](#12-deploy-script-behavior)  
13. [Changing the public port (e.g. to 80)](#13-changing-the-public-port-eg-to-80)  
14. [Troubleshooting](#14-troubleshooting)  
15. [Post-deployment verification checklist](#15-post-deployment-verification-checklist)

---

## 1. Project overview

This project is a **Flask**-based user service:

- **PostgreSQL** stores users.
- **Nginx** is the public entry point; it reverse-proxies to the app.
- **Docker Compose** runs **nginx**, **web** (Gunicorn + Flask), **db** (Postgres), and **uptime-kuma** for uptime checks.

The Flask app exposes routes such as:

| Route | Method | Purpose |
|--------|--------|---------|
| `/api/health` | GET | Liveness / version JSON for probes and monitors |
| `/api/users` | GET | List users (no passwords returned) |
| `/api/users` | POST | Create user (validated input) |
| `/api/login` | POST | Simple credential check (lab-style; not production auth) |
| `/boom` | GET | **Intentional error** to verify **Sentry** end-to-end |

**Sentry** is initialized **only** when the environment variable `SENTRY_DSN` is set, so local runs without Sentry stay quiet.

---

## 2. Architecture and design choices

### 2.1 Why Nginx?

Traffic from the host hits **Nginx** first (`APP_PORT` on the host maps to **port 80 inside the Nginx container**). Nginx forwards to **`http://web:5000`**, where **Gunicorn** serves Flask on **5000** inside the **web** container.

You **do not** change the Dockerfile or Gunicorn bind when adding Nginx: the app keeps listening on **5000** internally. This mirrors common production patterns and leaves room for TLS termination, caching, or stricter headers later.

### 2.2 Port model (`APP_PORT`)

Compose maps the host to Nginx with:

```yaml
ports:
  - "${APP_PORT:-5000}:80"
```

So **`APP_PORT`** is the **host** port users curl (for example `5000`). Inside Docker, Nginx listens on **80** and proxies to **`web:5000`**. [Docker Compose variable interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/) applies here; your `.env` or shell can set `APP_PORT` for flexibility.

### 2.3 Why SonarCloud?

**SonarCloud** adds **static analysis**, **security hotspots**, and **maintainability** feedback on every analysis. For Python, Sonar expects coverage in **Cobertura XML** form — this repo’s CI generates **`coverage.xml`** with **pytest-cov** and passes it to the Sonar scanner.

### 2.4 Why Sentry?

**Sentry** captures **unhandled exceptions** in production-like environments with stack traces and request context. The official approach for Flask is **`sentry-sdk`** with **`FlaskIntegration`**, which this app uses.

### 2.5 Why Uptime Kuma?

**Uptime Kuma** gives a simple **HTTP monitor** and history for `/api/health`, so you can see outages and latency without only relying on logs.

---

## 3. Repository layout

| Path | Role |
|------|------|
| `app.py` | Flask application, DB access, optional Sentry init |
| `Dockerfile` | Multi-stage image; non-root user; Gunicorn |
| `docker-compose.yml` | Stack: nginx, web, db, uptime-kuma |
| `nginx.conf` | Reverse proxy to `web:5000` |
| `requirements.txt` | Runtime deps including `sentry-sdk[flask]` |
| `tests/` | Pytest suite |
| `.flake8` | Shared flake8 rules (e.g. max line length 120) |
| `.github/workflows/ci.yml` | Test → Sonar → build/push → Trivy → deploy |
| `.github/workflows/matrix-lab.yml` | Optional manual matrix (lint + tests) |
| `scripts/deploy.sh` | EC2-side `compose pull` + `up` + health check |
| `sonar-project.properties` | Sonar project key, org, Python version, coverage path |
| `.env.example` | Documented template (never commit real `.env`) |

---

## 4. Prerequisites

- **Docker** and **Docker Compose** plugin (v2) on your machine for local runs.
- For CI/CD: a **GitHub** repository, optional **SonarCloud** and **Sentry** accounts, and an **EC2** (or similar) host if you use the deploy job.

---

## 5. Local deployment

### 5.1 Required files

Ensure you have at least: `app.py`, `Dockerfile`, `docker-compose.yml`, `nginx.conf`, `requirements.txt`, and a populated **`.env`** (copy from `.env.example`).

### 5.2 Configure `.env`

Typical values for Compose:

```env
DB_HOST=db
DB_NAME=securecart
DB_USER=postgres
DB_PASSWORD=<choose-a-strong-password>
SECRET_KEY=<long-random-string>
APP_PORT=5000
APP_VERSION=dev
IMAGE_TAG=latest
```

Optional, for Sentry during local testing:

```env
SENTRY_DSN=https://<public-key>@<org>.ingest.sentry.io/<project-id>
```

`docker-compose.yml` uses **`build`** plus **`image`** for **web**: you can build locally while still tagging the image in a **GHCR**-friendly way. On **push to `main`**, CI builds and pushes **`${{ github.sha }}`** and **`latest`** to GHCR using the lowercase repository name.

### 5.3 Build and run

From the repository root:

```bash
docker compose down
docker compose up -d --build
```

### 5.4 Quick API checks

Replace `5000` if you changed `APP_PORT`.

**Health**

```bash
curl http://localhost:5000/api/health
```

**Create a user**

```bash
curl -X POST http://localhost:5000/api/users \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"StrongPass123"}'
```

**List users**

```bash
curl http://localhost:5000/api/users
```

**Login**

```bash
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"StrongPass123"}'
```

**Sentry smoke test** (only meaningful if `SENTRY_DSN` is set)

```bash
curl -i http://localhost:5000/boom
```

You should see a **500** response; in Sentry, a new **Issue** should appear for the intentional exception.

---

## 6. SonarCloud integration (detailed)

SonarCloud analyzes your source and (when configured) merges **test coverage** from **`coverage.xml`** into the dashboard.

### 6.1 One-time setup in the SonarCloud portal

1. Sign in to **[SonarQube Cloud](https://sonarcloud.io/)** (SonarCloud is the SaaS offering).
2. **Import** your GitHub organization or repository (Sonar’s GitHub onboarding wizard is the usual path).
3. **Create** (or select) a project. Note:
   - **`sonar.projectKey`** — unique project identifier (often `org_repo` style).
   - **`sonar.organization`** — your SonarCloud organization key.
4. Choose **GitHub Actions** as the analysis method when prompted; Sonar will show you the token workflow.
5. In GitHub: **Settings → Secrets and variables → Actions**, create **`SONAR_TOKEN`**: a **SonarCloud user token** (or analysis token) with permission to execute analyses for that project.

> **Forking this repo:** Replace the keys in `sonar-project.properties` with **your** Sonar project key and organization. The committed file is an example tied to the original lab owner’s Sonar project.

### 6.2 What lives in this repository

**`sonar-project.properties`** (root) tells the scanner where code and tests live and where coverage lives:

```properties
sonar.projectKey=<your-project-key>
sonar.organization=<your-organization-key>

sonar.sources=.
sonar.tests=tests
sonar.test.inclusions=tests/**/*.py

sonar.exclusions=**/__pycache__/**,.pytest_cache/**,.github/**,scripts/**

sonar.python.version=3.11
sonar.python.coverage.reportPaths=coverage.xml
```

The important coverage line for Python is **`sonar.python.coverage.reportPaths=coverage.xml`**, which matches [Sonar’s documentation for Python coverage](https://docs.sonarcloud.io/enriching/test-coverage/overview/) (Cobertura XML).

### 6.3 What the GitHub Actions workflow does

In **`.github/workflows/ci.yml`**:

1. **`test`** job runs **pytest** with **`--cov=app --cov-report=xml --cov-fail-under=60`**, producing **`coverage.xml`**.
2. That file is uploaded as an artifact named **`coverage-report`**.
3. **`sonarcloud`** job (runs after `test`) checks out the repo, **downloads** the same artifact so `coverage.xml` sits at the workspace root, then runs:

   **`SonarSource/sonarqube-scan-action@v6`**

   with **`SONAR_TOKEN`** from secrets. The action reads **`sonar-project.properties`** automatically.

### 6.4 After a pipeline run — what to verify in SonarCloud

Open your project in SonarCloud and confirm:

- **Coverage** shows a real percentage (not stuck on “set up coverage”).
- **Quality Gate** passed or failed with clear reasons.
- **Issues** tab lists bugs, vulnerabilities, and code smells as expected.
- **Security / Reliability / Maintainability** ratings reflect the latest analysis.

If coverage is missing, almost always either **`coverage.xml` was not present** in the Sonar job workspace, or **`sonar.python.coverage.reportPaths`** does not point to the correct filename or path.

---

## 7. Sentry integration (detailed)

Sentry gives **real-time error tracking** for the Flask app.

### 7.1 One-time setup in the Sentry portal

1. Create a project at **[sentry.io](https://sentry.io/)** and choose **Flask** (or Python) as the platform — this aligns with **[Sentry’s Flask integration](https://docs.sentry.io/platforms/python/guides/flask/)** documentation.
2. After creation, copy the **DSN** (Data Source Name). You will find it in the onboarding wizard or under **Project Settings → Client Keys (DSN)**.

The DSN is a **secret**: treat it like a password. Anyone with the DSN can send events to your project.

### 7.2 What lives in this repository

**`requirements.txt`** includes:

```text
sentry-sdk[flask]>=2.0.0
```

**`app.py`** (conceptually) does the following:

- If **`SENTRY_DSN`** is set, call **`sentry_sdk.init(...)`** with **`FlaskIntegration()`** and a **traces sample rate** (performance monitoring sample).
- Set **`release`** from **`APP_VERSION`** when present, so deploys tagged with a Git SHA line up with Sentry releases and your `/api/health` version field.

There is a **`/boom`** route that raises an exception on purpose so you can confirm the pipeline from browser or `curl`.

**Important behavior:** Handlers that **`except Exception`**, log, and return **500** without **re-raising** will **not** automatically create Sentry events. Only unhandled exceptions (like `/boom`) or code paths that call **`sentry_sdk.capture_exception`** will. For production services you often add **`capture_exception`** in critical `except` blocks or enable the logging integration.

### 7.3 Local and GitHub configuration

- **Local:** put `SENTRY_DSN=...` in **`.env`** (this file should stay **gitignored**).
- **GitHub Actions deploy:** the workflow writes **`SENTRY_DSN`** into the remote **`.env`** on the server from the **`SENTRY_DSN`** repository secret.

### 7.4 Verifying Sentry after EC2 deploy

1. Ensure the **web** container received **`SENTRY_DSN`** (remote `.env` generated by CI).
2. From your workstation:

   ```bash
   curl -i "http://<EC2_PUBLIC_IP>:<APP_PORT>/boom"
   ```

   Use the same **`APP_PORT`** you configured (often `5000`).

3. In Sentry → **Issues**, you should see the event with stack trace and request metadata.

4. Ensure the EC2 instance has **outbound HTTPS** to Sentry’s ingest endpoints (corporate firewalls sometimes block this).

---

## 8. Uptime Kuma

Compose includes **`uptime-kuma`** mapping **`3001:3001`** and a volume **`uptime_data`** for persistence. The upstream project documents running Kuma in Docker; the UI is on **port 3001** by default.

### 8.1 First-time UI

- **Local:** [http://localhost:3001](http://localhost:3001)  
- **EC2 (if security group allows it):** `http://<EC2_PUBLIC_IP>:3001`

Create an admin account, then add an **HTTP(s)** monitor.

### 8.2 What URL should the monitor use?

- **External check (recommended for “is the site up?”):**  
  `http://<host>:<APP_PORT>/api/health`  
  (same URL family as your users — goes through Nginx).

- **From another container on the same Compose network** (internal):  
  e.g. `http://nginx/api/health` (Nginx listens on port **80** in-container; service name **`nginx`** resolves on the **`internal`** network).

### 8.3 What “good” looks like

- Monitor status **UP**, HTTP **200**, latency visible.
- If you stop **`nginx`** or **`web`**, the external monitor should go **DOWN**; bringing the stack back should restore **UP**.

---

## 9. CI/CD pipeline overview

Workflow: **`.github/workflows/ci.yml`**

| Stage | Purpose |
|--------|---------|
| **`test`** | Postgres service on the runner; `pip install`; **flake8** on `app.py` + `tests`; **pytest** with **≥ 60%** coverage gate; uploads **`coverage.xml`**. |
| **`sonarcloud`** | Downloads coverage artifact; **SonarQube Cloud** scan with **`sonarqube-scan-action@v6`**. |
| **`build-and-push`** | After tests + Sonar pass: **Docker Buildx**; login to **GHCR** with **`GITHUB_TOKEN`**; push **`ghcr.io/<lowercase-owner>/<lowercase-repo>:<sha>`** and **`:latest`** (push only on **`main`**). |
| **`scan-image`** | **Trivy** scan of the pushed image; **CRITICAL** severity fails the job; JSON report uploaded as artifact. *(Runs on push to `main`.)* |
| **`scan-deps`** | **Trivy filesystem** scan of the repo; **CRITICAL** fails; JSON artifact. |
| **`deploy`** | On **`main`** push only: SSH/SCP to EC2, write remote **`.env`**, GHCR login on host with **`GHCR_USERNAME`** / **`GHCR_PAT`**, run **`deploy.sh`**, verify health via HTTP from the runner. |

**Note:** Image build and push in CI use **`docker/login-action`** with **`github.actor`** and **`secrets.GITHUB_TOKEN`**. The **EC2** host uses **`GHCR_PAT`** (classic PAT or fine-grained token with **read packages**) so **`docker compose pull`** can authenticate to GHCR.

---

## 10. EC2 preparation

Before the first successful deploy:

1. **Install Docker Engine** and the **Docker Compose** plugin.
2. **Stop/disable host-level Nginx** if it would bind the same port as Dockerized Nginx (e.g. `sudo systemctl stop nginx` / `disable`).
3. **Create deployment tree** and ownership for your deploy user, for example:

   ```bash
   sudo mkdir -p /opt/teams
   sudo chown -R ubuntu:ubuntu /opt/teams
   sudo chmod -R 755 /opt/teams
   ```

4. Add the user to the **`docker`** group if needed (`sudo usermod -aG docker ubuntu`), then re-login.
5. **Remove old stacks** that still bind legacy ports (for example an old app on **8001**) so **`APP_PORT`** matches what Compose expects.
6. **AWS Security Group:** allow **22** (SSH), **`APP_PORT`** (e.g. **5000**) for HTTP to Nginx, and **3001** only if you intentionally expose Kuma. **Do not** expose **5432** to the world; Postgres should stay private.

---

## 11. GitHub secrets reference

The **`deploy`** job expects these **repository secrets** (names must match the workflow):

| Secret | Typical use |
|--------|----------------|
| `SSH_PRIVATE_KEY` | Full PEM for SSH to EC2 |
| `DEPLOY_HOST` | `ubuntu@<ec2-public-dns-or-ip>` |
| `TEAM_ID` | Folder segment under `/opt/teams`, e.g. `team-01` |
| `DB_HOST` | Inside Compose, use **`db`** (service name) |
| `DB_NAME` | e.g. `securecart` |
| `DB_USER` | e.g. `postgres` |
| `DB_PASSWORD` | Strong DB password |
| `SECRET_KEY` | Flask secret key |
| `GHCR_USERNAME` | GitHub username for `docker login` on EC2 |
| `GHCR_PAT` | PAT with **read:packages** (or equivalent) to pull private GHCR images |
| `APP_PORT` | Host port mapped to Nginx (e.g. `5000`) |
| `SENTRY_DSN` | Your Sentry DSN (optional but recommended for observability) |
| `SONAR_TOKEN` | SonarCloud token for the **`sonarcloud`** job |

**`SONAR_TOKEN`** is documented in Sonar’s GitHub Actions onboarding. **`SENTRY_DSN`** should match the DSN from the Sentry project settings.

---

## 12. Deploy script behavior

**`scripts/deploy.sh`** (run **on EC2** with env `TEAM_ID`, `APP_PORT`, and optionally `GIT_SHA`):

- Resolves **`APP_DIR=/opt/teams/$TEAM_ID/app`**.
- When **`GIT_SHA`** is set, exports **`APP_VERSION`** and **`IMAGE_TAG`** to that SHA so Compose pulls the image built for that commit.
- Verifies **`docker-compose.yml`**, **`nginx.conf`**, and **`.env`** exist.
- Runs **`docker compose pull`** then **`docker compose up -d --remove-orphans`**.
- Waits briefly, then **`curl`**s **`http://localhost:${APP_PORT}/api/health`** on the **EC2 host** (through Nginx from the host’s perspective — same port visitors use).

---

## 13. Changing the public port (e.g. to 80)

If you move the public listener from **5000** to **80**:

- **Keep** the Dockerfile and Gunicorn bind on **0.0.0.0:5000** inside **web**.
- **Keep** Nginx **`proxy_pass http://web:5000`**.
- **Change** the host mapping by setting **`APP_PORT=80`** (GitHub secret and remote `.env`), and ensure **`${APP_PORT:-5000}:80`** in Compose resolves to **`80:80`**.
- **Open port 80** in the security group; ensure **no other process** (including apt **nginx**) owns port **80** on the host.

---

## 14. Troubleshooting

| Symptom | Things to check |
|---------|-------------------|
| SSH/SCP fails | `DEPLOY_HOST` format, key in `SSH_PRIVATE_KEY`, SG port **22** |
| `docker compose pull` fails on EC2 | `GHCR_USERNAME` / `GHCR_PAT`, image visibility, network |
| App unreachable | SG allows **`APP_PORT`**, `docker compose ps`, `docker compose logs nginx` / `web` |
| Nginx container fails | `nginx.conf` present on server, port conflict with host Nginx |
| Sentry silent | `SENTRY_DSN` in remote `.env`, outbound HTTPS, SDK installed in image |
| Sonar has no coverage | `coverage.xml` in Sonar job workspace, `sonar.python.coverage.reportPaths` |
| Kuma always down | Monitor URL, SG for **3001** if using UI remotely, app health actually 200 |

---

## 15. Post-deployment verification checklist

1. **`curl http://<EC2_IP>:<APP_PORT>/api/health`** → JSON **healthy**.  
2. **POST /api/users** → **201**.  
3. **POST /api/login** → **200** with user payload.  
4. **`curl .../boom`** → **500**, matching **Issue** in Sentry.  
5. **Uptime Kuma** monitor **UP** on `/api/health`.  
6. **SonarCloud** shows latest analysis, **coverage**, and **quality gate**.

---

## Contributing and safety notes

- Never commit **`.env`** or real **tokens**. Use **`.env.example`** as documentation only.  
- Rotate any credential that may have been exposed in logs, tickets, or chat.  
- This lab uses **plaintext passwords in the database** for teaching purposes — **do not** reuse that pattern in real systems; use password hashing and proper session security.

---

## License and acknowledgements

This repository is maintained as part of a **DevSecOps crash course / lab** curriculum. Tooling references: **Docker**, **Flask**, **SonarCloud**, **Sentry**, **Trivy**, **GitHub Actions**, **Uptime Kuma** — see each vendor’s documentation for the latest setup details beyond what this README summarizes.
