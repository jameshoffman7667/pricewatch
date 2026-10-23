# Pending changes

Requests are logged here and built only when James sends a build message.

## Pending

### P-1 - Make the UI an installable PWA with mobile and desktop layouts
Requested: 2026-10-22 (found in the home server spec audit; not requested in chat)
Type: minor (new feature)        Status: Pending
Notes / questions: manifest, icons, wide and narrow screenshots, service worker with offline page, install button, designed phone and desktop layouts, light/dark. Needs a public hostname (https) and a Cloudflare Access bypass for manifest, sw.js and icons.

### P-2 - Automated checks for config, SIGTERM and version consistency
Requested: 2026-10-22 (found in the home server spec audit; not requested in chat)
Type: patch (tests)        Status: Pending
Notes / questions: one-command test run, SIGTERM clean-exit test, /healthz and PORT tests, VERSION vs CHANGELOG length checks. The 5400 vs register port should be confirmed.

## Done

