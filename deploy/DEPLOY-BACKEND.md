# Deploying backend-phase2 (Docker Compose + systemd)

This is the microservices version: `user-service`, `itinerary-service`,
`recommendation-service`, `community-service`, and `api-gateway`, each in
its own Docker container, orchestrated by `docker-compose.yml`. systemd is
used only to start/stop the whole Compose stack on boot — Docker still runs
the actual containers.

The gateway is a **pure API** now (no frontend files inside it) — the
frontend is deployed and served separately by Nginx, from the sibling
`frontend` repo/zip.

**Port used:** the gateway listens on `127.0.0.1:8095` only (not exposed
publicly) — same port the Nginx config already expects to proxy `/api/`
to. Run `sudo ss -tulpn | grep :8095` first if you're not sure it's free.

Run everything below **on the VPS**, over SSH, as a user with sudo access.

## 0. One-time server prep (Docker)

Skip anything already installed:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
docker compose version   # confirms the plugin is present
```

## 1. Get the code onto the server

```bash
cd /opt
sudo git clone <your-backend-phase2-repo-url> serena-phase2-backend
cd serena-phase2-backend
ls   # should show api-gateway, user-service, itinerary-service,
     # recommendation-service, docker-compose.yml, deploy/, update.sh
```

(If you're uploading the zip instead of git, unzip it so the folder ends
up at exactly `/opt/serena-phase2-backend`.)

## 2. Secret key

Generate one:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Create the `.env` file (Docker Compose loads this automatically from the
same folder as `docker-compose.yml`):

```bash
sudo cp .env.example .env
sudo nano .env   # paste the generated value after SECRET_KEY=
sudo chmod 600 .env
```

## 3. Install the systemd wrapper

```bash
sudo cp deploy/serena-phase2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now serena-phase2
```

The first start builds all five Docker images, which can take a minute
or two. Watch it:

```bash
sudo systemctl status serena-phase2
docker compose -f /opt/serena-phase2-backend/docker-compose.yml ps
```

You want all five containers `Up`.

Logs:

```bash
docker compose logs -f              # all services
docker compose logs -f api-gateway  # just the gateway
```

## 4. Confirm it's answering

```bash
curl -i http://127.0.0.1:8095/health
# {"service":"api-gateway","status":"ok"}

curl -i http://127.0.0.1:8095/api/meta
# 200 with a JSON body of categories/quartiers — this route is public in
# this codebase (unlike the monolith, phase2 doesn't require login on
# every endpoint yet).
```

If either curl fails to connect at all, check `docker compose ps` — a
container that didn't come up is the usual cause.

## Updating the app later

```bash
cd /opt/serena-phase2-backend
sudo ./update.sh
```

This pulls the latest git changes, rebuilds the five images, and
restarts the containers with zero manual steps.

## Notes

- **Data storage**: each service keeps its own JSON files under
  `<service>/data/`, mounted into the container as a volume so they
  survive rebuots and rebuilds. Back them up before anything risky:
  `sudo cp -r /opt/serena-phase2-backend/*/data ~/backup-phase2-$(date +%F)`.
- **Nginx / frontend**: this repo does not include or serve the frontend
  — see the `frontend` repo's own `deploy/` folder for the Nginx config
  that serves it and proxies `/api/` to `127.0.0.1:8095`.
- **No domain / HTTPS yet**: same as the frontend side — everything is
  plain HTTP over the VPS's public IP for now.
