# Deploy Runbook

Production URL:

```text
https://d5d05aesrv8vtemcc0ga.628pfjdx.apigw.yandexcloud.net
```

Cloud setup:

```text
cloud: ai-knowledge-tracing
cloud_id: b1g0jf3vns3anv5b4mcl
folder_id: b1g0n6gfqnu5803im5nt
container_id: bba72ii66ut7tsci620k
container_registry_id: crpvnq0p7r71ob9eg546
frontend_bucket: kt-frontend-meowmeow-2026
runtime_service_account: ajec7n6fkv9d5v2m5mkn
bucket_service_account: aje17g3u4jjva97h7gc6
network_id: enp24jtf8nokmn6f3vqs
```

## Golden Path

1. Merge the PR to `master`.
2. Open GitHub Actions: `Deploy to Yandex Cloud`.
3. Run the workflow from `master`.
4. Select only what changed:
   - frontend-only change: `frontend=true`, `backend=false`
   - backend change: `backend=true`, `frontend=true` when the frontend bundle should also be refreshed
5. Wait for the built-in production smoke check.

This path is OS-independent because all build and upload work happens in GitHub
Actions on Ubuntu.

## Terminal Dispatch

Any OS with GitHub CLI can dispatch the workflow directly:

```bash
gh workflow run deploy.yml --repo dqnilka/kn-trace-itmo --ref master -f backend=false -f frontend=true
gh workflow run deploy.yml --repo dqnilka/kn-trace-itmo --ref master -f backend=true -f frontend=true
```

macOS, Linux, WSL, or Git Bash can use the Bash helper:

```bash
scripts/deploy.sh --frontend-only --wait
scripts/deploy.sh --backend-only --wait
scripts/deploy.sh --wait
```

The script does not deploy local files. It dispatches the GitHub Actions
workflow on `master`, so production always comes from the reviewed remote branch.

## Frontend

Frontend deploy is static only. Do not rebuild the backend image for frontend-only
changes.

The GitHub Actions workflow runs on Ubuntu and uploads with:

```bash
aws --endpoint-url=https://storage.yandexcloud.net \
  s3 sync frontend/dist/ "s3://$YC_BUCKET/" \
  --delete --acl public-read
```

Do not upload frontend static files from a local native Windows shell. Use
GitHub Actions, or a POSIX shell such as macOS, Linux, WSL, or Git Bash.

## Backend

Backend deploy builds a linux/amd64 image and deploys a new Serverless Container
revision.

Important: the deploy workflow first reads the currently active revision and
copies its runtime config into the new revision:

```text
environment variables
Lockbox secret bindings
service account
network
memory, cores, timeout, concurrency
```

This prevents accidental deploys that drop `DATABASE_URL`, `JWT_SECRET`,
`LLM_API_KEY`, `ADMIN_EMAILS`, or the private network.

## Smoke Checks

The workflow fails if production does not pass these checks:

```bash
curl --connect-timeout 8 --max-time 30 --retry 2 --retry-all-errors -fsS "$PUBLIC_URL/healthz"
curl --connect-timeout 8 --max-time 30 --retry 2 --retry-all-errors -fsS "$PUBLIC_URL/" | grep -o '<title>[^<]*'
curl --connect-timeout 8 --max-time 30 --retry 2 --retry-all-errors -fsS "$PUBLIC_URL/" | grep -o 'index-[A-Za-z0-9_-]*\.js'
```

Expected:

```text
healthz status: ok
llm_configured: true
title: FinUplift
bundle: index-*.js
```

Local smoke check:

```bash
scripts/deploy.sh --smoke-only
```

## Do Not

- Do not deploy from a stale checkout. Use `master` on GitHub as the source of truth.
- Do not upload frontend without `--delete`.
- Do not deploy frontend static files from a local native Windows shell.
- Do not rebuild or redeploy the backend image for frontend-only changes.
- Do not create a backend revision unless the active revision config was copied.
- Do not accept a production deploy if smoke checks return 500 or bad `/healthz`.
