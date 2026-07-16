# Production deployment

## Required settings

Set these values in the deployment secret manager, not in the image or repository:

```dotenv
ENVIRONMENT=production
JWT_SECRET=<at-least-32-random-characters>
COOKIE_SECURE=true
CORS_ORIGINS=https://kb.example.com
TRUSTED_HOSTS=kb.example.com
AUTO_INIT_DB=false
REDIS_URL=rediss://:<password>@redis.example.internal:6379/0
MYSQL_USER=knowledge_base_app
MYSQL_SSL_CA=/run/secrets/mysql-ca.pem
MILVUS_URI=https://milvus.example.internal:19530
MILVUS_TOKEN=<milvus-user:password-or-managed-token>
MILVUS_SERVER_PEM_PATH=/run/secrets/milvus-ca.pem
RAG_REQUIRE_DEPARTMENT_MATCH=true
STORAGE_BACKEND=oss
OSS_REGION=cn-hangzhou
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=<private-bucket-name>
OSS_PREFIX=engineering-files/prod
OSS_ACCESS_KEY_ID=<ram-access-key-id>
OSS_ACCESS_KEY_SECRET=<ram-access-key-secret>
IMAGE_ASSET_WORKERS=2
```

The MySQL account should only have DML permissions on the application database. Keep MySQL, Redis, Milvus, and the API port on a private network. Only the frontend ingress should be public.

## Release order

```bash
python scripts/migrate.py
docker build -t engineering-files-api:VERSION .
docker build -t engineering-files-web:VERSION frontend
```

Run one Uvicorn process per API container and scale containers horizontally. Redis is mandatory when more than one API process or replica is used. Use local `/app/data` only for development; production should set `STORAGE_BACKEND=oss` so uploaded documents, images, and thumbnails live outside the API container.

## OSS storage

Create a private Alibaba Cloud OSS bucket in the same region as the API whenever possible. Do not make the bucket public. The API keeps enforcing application login/role checks, then proxies file view/download responses from OSS.

Recommended setup:

- Bucket ACL: private.
- Region/endpoint: for example `cn-hangzhou` and `https://oss-cn-hangzhou.aliyuncs.com`.
- RAM user: grant only the target bucket and prefix, with `oss:PutObject`, `oss:GetObject`, `oss:DeleteObject`, and `oss:GetObjectMeta`.
- Prefix: use an environment-specific prefix such as `engineering-files/prod` to separate production from staging.
- CDN: optional later. Keep origin private and use signed URLs or origin authentication if direct CDN delivery is added.

After OSS is enabled, the database stores object locations such as `oss://bucket/engineering-files/prod/images/<id>.png`; MySQL still stores metadata, Milvus stores vectors, and OSS stores file bodies.

Legacy local files can remain readable while their database rows still point to `data/uploads/...` or `data/images/...`. For a full migration, upload those files to OSS, update `document_assets.file_path`, `image_assets.file_path`, and `image_assets.thumbnail_path` to the returned `oss://...` locations, then re-run a small validation that list, preview, view, download, and delete all work.

Batch image uploads return immediately after the original images and thumbnails are stored. Vision understanding, embedding, and Milvus writes run in the background with concurrency controlled by `IMAGE_ASSET_WORKERS`. Start with `2`; increase only after model cost, Milvus latency, and API CPU are stable. For larger multi-replica production, move the same processing function behind a durable queue such as Redis Queue, Celery, or Alibaba Cloud MNS so jobs survive container replacement across replicas.

## Initial capacity

- API: 2 replicas, each 2 vCPU and 4 GB RAM.
- Background/image processing: 2 workers, each 4 vCPU and 8 GB RAM when moved to a job queue.
- Redis: managed high-availability instance, 1 GB minimum.
- MySQL: MySQL 8.4 LTS managed high-availability instance, 2 vCPU and 8 GB RAM to start.
- Milvus: managed or distributed deployment with authentication, TLS, backups, and private networking.

Configure MySQL point-in-time recovery, Milvus backups, versioned file backups, centralized JSON logs, error tracking, model-cost alerts, and restore drills. The Nginx configuration keeps SSE buffering disabled and caps requests at 200 MB; the API applies stricter per-file and per-batch limits.
