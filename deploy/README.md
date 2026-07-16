# Cloud deployment

This project can be deployed in two ways:

- Docker Compose: recommended for the first ECS deployment.
- systemd: useful when you want to run the backend directly on the host.

This compose profile runs MySQL and Redis on the ECS host. Use OSS for uploaded files. For a later higher-availability production setup, migrate MySQL to RDS and Milvus to a managed/private deployment. Do not commit `.env.production`.

## 1. Docker Compose deployment

On the server:

```bash
git clone <your-repository-url> /opt/engineering-files
cd /opt/engineering-files
cp .env.production.example .env.production
```

Edit `.env.production` and replace every `replace-with-*` value. Set:

```dotenv
CORS_ORIGINS=https://your-domain.com
TRUSTED_HOSTS=your-domain.com,www.your-domain.com,127.0.0.1,localhost
REDIS_PASSWORD=<same-password-used-inside-REDIS_URL>
REDIS_URL=redis://:<same-password>@redis:6379/0
MYSQL_HOST=mysql
MYSQL_PASSWORD=<database-password>
MYSQL_ROOT_PASSWORD=<root-password-for-local-mysql-container>
MYSQL_SSL_CA=
```

Run database migration before starting production replicas:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python scripts/migrate.py
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

To validate the compose file with the example env before creating real secrets:

```bash
APP_ENV_FILE=.env.production.example docker compose --env-file .env.production.example -f docker-compose.prod.yml config
```

The app listens only on localhost:

- API: `127.0.0.1:8000`
- Web: `127.0.0.1:8080`
- Redis: `127.0.0.1:6379`
- MySQL: `127.0.0.1:3306`

Put host Nginx in front of it.

The MySQL data volume is named `engineering-files_mysql-data`. Back it up regularly. If you later switch to RDS, set `MYSQL_HOST` to the RDS private endpoint and set `MYSQL_SSL_CA` to the RDS CA file path.

## 2. Nginx

Copy the example config and replace `example.com`:

```bash
sudo cp deploy/nginx/engineering-files.conf /etc/nginx/conf.d/engineering-files.conf
sudo sed -i 's/example.com/your-domain.com/g' /etc/nginx/conf.d/engineering-files.conf
sudo nginx -t
sudo systemctl reload nginx
```

Install HTTPS certificates with your preferred ACME client, for example Certbot. The config expects:

```text
/etc/letsencrypt/live/your-domain.com/fullchain.pem
/etc/letsencrypt/live/your-domain.com/privkey.pem
```

## 3. systemd deployment

Install runtime dependencies:

```bash
sudo useradd --system --create-home --home-dir /opt/engineering-files engineering
sudo chown -R engineering:engineering /opt/engineering-files
cd /opt/engineering-files
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd frontend
npm ci
npm run build
```

Create the backend environment file:

```bash
sudo mkdir -p /etc/engineering-files
sudo cp .env.production.example /etc/engineering-files/api.env
sudo chmod 600 /etc/engineering-files/api.env
sudo chown root:root /etc/engineering-files/api.env
```

Edit `/etc/engineering-files/api.env`, then migrate:

```bash
cd /opt/engineering-files
sudo -u engineering /opt/engineering-files/.venv/bin/python scripts/migrate.py
```

If your RDS provider requires a dedicated CA file, download it to the server and set `MYSQL_SSL_CA` to that absolute path. The Docker example uses the container system CA bundle by default.

Install services:

```bash
sudo cp deploy/systemd/engineering-files-api.service /etc/systemd/system/
sudo cp deploy/systemd/engineering-files-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now engineering-files-api engineering-files-web
sudo systemctl status engineering-files-api
sudo systemctl status engineering-files-web
```

## 4. Release update

For Docker Compose:

```bash
cd /opt/engineering-files
git pull
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python scripts/migrate.py
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

For systemd:

```bash
cd /opt/engineering-files
git pull
. .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
sudo -u engineering /opt/engineering-files/.venv/bin/python scripts/migrate.py
sudo systemctl restart engineering-files-api engineering-files-web
```

## 5. Smoke test

After deployment, verify:

```bash
curl -I https://your-domain.com/
curl https://your-domain.com/api/health/live
curl https://your-domain.com/api/health/ready
```

Then test login, guest login, document upload, image upload, image search, download usage recording, and deletion from the browser.
