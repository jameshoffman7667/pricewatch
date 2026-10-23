# Changelog

Newest first. One entry per released version.

## v0.1.2 - 2026-10-22
**Short:** Release on push to main, no tag push needed
**Long:** Release workflow now runs when a push to main changes VERSION: it validates the CHANGELOG, builds X.Y.Z, X.Y and latest, then creates the tag and GitHub release itself. The v*.*.* tag trigger stays as a fallback.

## v0.1.1 - 2026-10-22
**Short:** Harden /healthz, 30s health start period
**Long:** Health check returns exactly status and version (the image tag) with no login or outside-service checks. Image and compose HEALTHCHECK call /healthz on $PORT with a 30 second start period.

## v0.1.0 - 2026-10-22
**Short:** Add release flow, health version, port 5400
**Long:** First versioned release: tag workflow builds amd64 image X.Y.Z, X.Y, latest and creates the GitHub release. Non-root tini image, /healthz returns version, PORT env, RFD deals feed, deploy/ files.
