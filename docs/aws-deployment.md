# ChronicNerd AWS deployment preparation

Status: preparation only. Nothing has been provisioned. Do not use the credentials or AWS account named in the historical "AWS Everything" PDF without the account holder's authorization. Domain purchase, hosting charges and account selection need Harsh's approval.

## Topology

- Frontend: static `dietnerd-website/` files built with `scripts/build-s3-site.sh` and uploaded to a private S3 bucket. Place CloudFront in front with Origin Access Control (OAC), HTTPS-only viewer policy, and an ACM certificate in us-east-1 for `chronicnerd.org` and `www.chronicnerd.org`. Use a CloudFront Function or edge redirect if apex should redirect to www; otherwise serve both names.
- API: one EC2 instance running the existing backend container (the current local Compose file also starts MySQL and nginx and is not a production manifest), fronted by an HTTPS Application Load Balancer (ALB). The API route should be `https://chronicnerd.org/api` through a CloudFront `/api/*` behavior that forwards cookies, relevant headers, query strings and all API methods to the ALB. Rewrite `/api` off the origin request path before forwarding, or mount FastAPI under that prefix. Include both `/api` and `/api/*` behaviors; forward SSE without caching, and do not cache authenticated API responses. The static build defaults to `/api`, but the CloudFront behavior and path rewrite have not yet been provisioned or end-to-end tested. An alternative is `https://api.chronicnerd.org` via `API_URL=https://api.chronicnerd.org`, but that needs a separate cert/DNS record, exact CORS origin and cookie strategy; do not switch silently.
- Database: MySQL 8. Choose a managed RDS instance or an EC2-attached persistent volume with backups before going live. The existing local Compose MySQL volume is not a production backup plan. Never expose MySQL publicly. Backend port 8000 should be reachable only from the ALB security group; SSH should be restricted to an approved operator route, not the world.
- Email: password-reset mail already supports SES via `MAIL_BACKEND=ses`, `MAIL_FROM` and `AWS_SES_REGION`. Use an EC2 instance role scoped to SES SendEmail rather than long-lived AWS access keys. Verify the sending domain/identity and SES production access before relying on password reset. If SES is not ready, do not launch sign-in to the public with the log-mail fallback, since it logs reset links.
- Cloudflare DNS (once the domain is owned and access is authorized): ACM validation CNAMEs DNS-only; apex and www to CloudFront (Cloudflare supports CNAME flattening at apex). For an ALB subdomain, DNS-only CNAME to its assigned hostname. Check DNS, CloudFront deployment, cert SAN, HTTP-to-HTTPS redirect, API health, login/session cookie, SSE, upload, reset mail, and a real research query before announcement.

## Build and local checks

```
API_URL=/api ./scripts/build-s3-site.sh
# inspect dist/site/env.js; upload dist/site/* only after AWS/account/domain approval
```

`API_URL` is public browser configuration; it must be `/api` or an HTTPS URL. The current source `dietnerd-website/env.js` points at localhost for Docker/local browser tests; the build replaces it in the output directory. Do not upload the source tree as-is to S3. There are no secret keys in the generated env.js. For local Compose continue to use `docker compose up --build`.

Set backend environment privately on EC2 (not in Git or S3): DB host/port/user/password/name; OPENAI_API_KEY, NCBI_API_KEY and publisher keys; `PUBLIC_SITE_URL=https://chronicnerd.org`; `ALLOWED_ORIGINS=https://chronicnerd.org,https://www.chronicnerd.org`; `COOKIE_SECURE=1`; `COOKIE_SAMESITE=lax` for same-origin `/api`; SES variables above. Do not use `--reload` in production. Use instance roles and a secret store for long-lived values, least privilege, TLS, logs with no sensitive tokens, a deploy rollback, and DB backups.

## Open decisions before provisioning

1. Who owns/pays for the AWS account and newly purchased domain? Request authorized AWS access through the account owner, not from the PDF. Confirm region, budget ceiling and billing alerts before EC2, ALB, RDS, S3, CloudFront or SES provisioning.
2. Choose `/api` same-origin proxy vs separate API host, and the exact apex/www canonical URL. The same-origin path is preferred to avoid cross-site cookies/CORS.
3. Decide managed RDS versus EC2-local MySQL plus a tested restore path. Confirm SES sender and production access.
4. Confirm privacy/security review for user health-related uploads, retention and backups before public launch.

The PDF's older wirelessnerd.org recipe makes its S3 bucket world-readable and puts HTTP site endpoints behind CloudFront. For a new deployment, prefer private S3 + OAC. The PDF is reference architecture, not proof that ChronicNerd resources already exist.

Authentication rate limits use the socket peer instead of an arbitrary `X-Forwarded-For` header. Behind an ALB this limits the shared proxy peer; add a CloudFront/WAF per-client rate limit before public launch and assess whether a carefully configured trusted-proxy mechanism is needed.
