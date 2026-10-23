# Release v0.1.0
Image: mybadreligon/pricewatch:0.1.0   (built by the v0.1.0 tag workflow)
Short: Add release flow, health version, port 5400
Long: First versioned release: tag workflow builds amd64 image X.Y.Z, X.Y, latest and creates the GitHub release. Non-root tini image, /healthz returns version, PORT env, RFD deals feed, deploy/ files.
Release commit: see `git log -1` on main (the commit that adds VERSION 0.1.0)        Tag pushed from authoring session: no (Claude Code pushes it)
Type: minor (baseline; first versioned release, nothing was tagged before)
Port: TBD (assign from the port register; 8070-8099 range). Dev default 5400 was requested earlier by James: confirm. Exception: none
Public hostname: none yet (needed only for PWA installability; see P-1)        Needs Caddy route: no, until a hostname is chosen
New or changed env vars: PORT (new, host=container), PRICEWATCH_DATA_DIR, TZ. No secrets.
Data: /data (SQLite pricewatch.db + screenshots/). Create the host folder `<FAST_STORAGE>/pricewatch` owned by UID 1000 / GID 100. Migration: none (tables created on start; RFD tables are added automatically).
Resources: idle ~150-250 MB RAM, low CPU; Chromium bursts only for monitors with "render with headless browser" (consider cpus: 2, mem_limit: 1g).
Healthcheck: GET /healthz on $PORT -> 200 {status, version}
Verify after deploy: 1) `GET /healthz` returns version 0.1.0; 2) open / and add a test monitor, "Check now" records a price; 3) open /deals, unread deals appear within ~5 minutes and a detail page loads.
PWA: not yet installable (P-1). Layouts, Lighthouse and Access bypass: not applicable until P-1.
Docker build: not run locally (no Docker daemon in the authoring sandbox); first build is the tag workflow. Python tests were run with dependency stubs, not the real packages.
Rollback: no earlier published tag; any earlier `latest` on Docker Hub was built by the old multi-arch workflow. Data restore needed: no.
Known issues: no auth (protect hostname with Cloudflare Access); RFD parsing may need updates if RFD changes its pages.
Backup tier: small/critical (Tier 1); SQLite: stop container during copy.
