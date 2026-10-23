# Release v0.1.2
Image: mybadreligon/pricewatch:0.1.2   (built by the release workflow on the push to main)
Short: Release on push to main, no tag push needed
Long: Release workflow now runs when a push to main changes VERSION: it validates the CHANGELOG, builds X.Y.Z, X.Y and latest, then creates the tag and GitHub release itself. The v*.*.* tag trigger stays as a fallback.
Release commit: HEAD of main when VERSION changed to 0.1.2        Tag: created by the release workflow (gh release create --target), nobody pushes it
Update: later
Type: patch
Port: 8071 proposed (next free after finance-hub 8070; host = container; James to confirm). 5400 is only the local dev default and is outside the server port standard. Exception: none
Public hostname: none yet (needed only for PWA installability; see P-1)        Needs Caddy route: no, until a hostname is chosen
New or changed env vars: PORT (new, host=container), PRICEWATCH_DATA_DIR, TZ. No secrets.
Data: /data (SQLite pricewatch.db + screenshots/). Create the host folder `<FAST_STORAGE>/pricewatch` owned by UID 1000 / GID 100. Migration: none (tables created on start; RFD tables are added automatically).
Resources: idle ~150-250 MB RAM, low CPU; Chromium bursts only for monitors with "render with headless browser" (consider cpus: 2, mem_limit: 1g).
Healthcheck: GET /healthz on $PORT -> 200 {"status":"ok","version":"0.1.2"}; no login, local DB ping only; start period 30s (image and compose)
Verify after deploy: 1) `wget -qO- http://127.0.0.1:<port>/healthz` returns `{"status":"ok","version":"0.1.2"}` (the host has wget, not curl); 2) open / and add a test monitor, "Check now" records a price; 3) open /deals, unread deals appear within ~5 minutes and a detail page loads.
PWA: not yet installable (P-1). Layouts, Lighthouse and Access bypass: not applicable until P-1.
Docker build: not run locally (no Docker daemon in the authoring sandbox); first build is the release workflow run. Python tests were run with dependency stubs, not the real packages.
Rollback: pin the previous published tag (0.1.0 and 0.1.1 were never built). Data restore needed: no.
Known issues: no auth (protect hostname with Cloudflare Access); RFD parsing may need updates if RFD changes its pages.
Backup tier: small/critical (Tier 1); SQLite: stop container during copy.
