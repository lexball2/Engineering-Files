# Source backup and Git upload

## OSS mode

The project is configured for OSS with:

```dotenv
STORAGE_BACKEND=oss
```

Before running in OSS mode, fill these values in local `.env` or your cloud secret manager:

```dotenv
OSS_REGION=cn-hangzhou
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=your-private-bucket
OSS_PREFIX=engineering-files/dev
OSS_ACCESS_KEY_ID=your-ram-access-key-id
OSS_ACCESS_KEY_SECRET=your-ram-access-key-secret
OSS_SESSION_TOKEN=
```

Use a private bucket and a RAM user that only has permissions for this bucket/prefix.

OSS only stores uploaded file bodies. Document search, image search, and image asset processing still need Milvus. For local development, keep Milvus running on `localhost:19530` or set a remote URI:

```dotenv
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_URI=
MILVUS_TOKEN=
MILVUS_SERVER_PEM_PATH=
```

For managed/cloud Milvus, set `MILVUS_URI` and `MILVUS_TOKEN`, then restart the backend.

## Create a local source backup

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup_source.ps1
```

The backup zip is written to `backups/`. The script excludes `.env`, `.git`, `.venv`, `data`, `node_modules`, and build/cache folders.

## Upload source to Git

Initialize once:

```powershell
git init
git add .
git commit -m "Initial source backup"
git branch -M main
```

Create an empty remote repository on GitHub, Gitee, GitLab, or another Git server, then connect it:

```powershell
git remote add origin <your-repository-url>
git push -u origin main
```

For later backups:

```powershell
git status
git add .
git commit -m "Update project source"
git push
```

Never commit `.env` or uploaded files under `data/`; they are intentionally ignored.
