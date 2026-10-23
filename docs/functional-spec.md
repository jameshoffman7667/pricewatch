# PriceWatch - Functional Specification (current state, v0.1.1)

## 1. Purpose
A single-user, self-hosted Docker app that monitors product prices and page changes without paid-tier limits, and tracks new RedFlagDeals (RFD) Hot Deals posts.

## 2. Runtime
- One image `mybadreligon/pricewatch`; FastAPI app served by uvicorn on `$PORT` (dev default 5400; host port assigned from the server port register).
- `GET /healthz` on `$PORT`: no login, no private data, no calls to outside services. Returns `{"status":"ok","version":"<VERSION = image tag>"}`; it only touches the local SQLite file and answers 503 `{"status":"error",...}` if that fails. Image `HEALTHCHECK` and the compose healthcheck both call it on `127.0.0.1:$PORT` with a 30 second start period.
- Version comes from the `VERSION` file (also shown in the API docs title metadata).
- Data in `/data` (SQLite `pricewatch.db`, `screenshots/`). Container runs as UID 1000 / GID 100 under `tini`.
- Env vars: `PORT`, `PRICEWATCH_DATA_DIR`, `TZ`. No authentication (single user, trusted network or protect the hostname with Cloudflare Access).
- Releases: pushing tag `vX.Y.Z` builds linux/amd64 and pushes `mybadreligon/pricewatch:X.Y.Z`, `:X.Y`, `:latest`, then creates the GitHub release.

## 3. Price / change monitors
- Fields: name, URL, selector type (`auto` | `css` | `regex` | `jsonpath`), selector, extra regex, render with headless browser, wait-for selector, custom user agent / headers / cookies, interval (minutes, min 1), enabled, screenshot capture, currency.
- Each check stores a Snapshot (status, price, text, content hash, error, screenshot, changed/notified). History is never pruned.
- Alerts: any change, price drop, price rise; minimum % and absolute change; target price (fires when price <= target, independent of the minimum-change thresholds).
- UI: dashboard, create/edit form, monitor detail with price chart, check-now, enable/disable, delete.

## 4. Notifications
- Apprise URL channels: add, test, delete in the UI. Alerts go to all enabled channels.

## 5. RedFlagDeals Hot Deals feed
- Source: RFD Hot Deals Atom feed (`/feed/forum/9`), polled every 5 minutes (first poll shortly after startup), polite identifying User-Agent.
- Deals (unique by thread id): title, retailer, price, original price, savings, expiry, RFD link, retailer link, thumbnail, author, votes, replies, posted time.
- List page `/deals`: Unread / Read / Favourited tabs with counts; title and price per row; favourite toggle; mark read/unread; mark all visible read.
- Detail page `/deals/{id}`: RFD AI thread summary if present (re-checked on open while unread, plus a 10-minute background refresh); RFD and retailer links; related expired RFD threads (RFD search of "Expired Hot Deals"); price history from an auto-created price monitor (auto-detect, every 180 min, alert on drop) plus outbound links to CamelCamelCamel/Keepa (Amazon) or RetailRadar.ca/PriceDropper.ca. No paid price-history API.
- Parsing relies on visible label text, not CSS classes.

## 6. REST API
- `GET/POST /api/monitors`, `GET/DELETE /api/monitors/{id}`, `GET /api/monitors/{id}/history`, `POST /api/monitors/{id}/check`
- `GET /api/deals?tab=unread|read|favourited`, `GET /api/deals/{id}`, `POST /api/deals/poll`

## 7. Mobile layout / Desktop layout / PWA
- Not yet implemented to the home server spec (installable PWA, distinct mobile and desktop layouts). Tracked as P-1 in `docs/pending-changes.md`.

## 8. Known limits
- No multi-user accounts or login.
- No CAPTCHA or bot-detection bypass.
- Auto price detection is heuristic; some sites need a CSS selector.
- RFD parsing depends on RFD's page structure.
