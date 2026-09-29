# PriceWatch

[![Build and publish Docker image](https://github.com/jameshoffman7667/pricewatch/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/jameshoffman7667/pricewatch/actions/workflows/docker-publish.yml)
[![Docker Hub](https://img.shields.io/badge/docker%20hub-mybadreligon%2Fpricewatch-blue)](https://hub.docker.com/r/mybadreligon/pricewatch)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A self-hosted price / website-change monitor that combines the useful bits of
Visualping, Distill.io, changedetection.io and Prisync-style rule alerting
into one Docker container - with none of their paid-tier limits:

- **Unlimited monitors** and **unlimited checks** (only bounded by your server)
- **Any check interval**, down to 1 minute, on every monitor
- **JavaScript rendering** via headless Chromium (Playwright), included at no
  extra cost/tier
- **CSS selector, regex, or auto-detect** price extraction
- **Full price history**, kept forever, with a chart per monitor
- **Rule-based alerts**: notify on drop / rise / any change, with minimum
  %% or $ change thresholds, and a "target price" alert
- **Free notification fan-out** via [Apprise](https://github.com/caronc/apprise) -
  email, Slack, Discord, Telegram, ntfy, Pushover, generic webhooks, and 80+
  other services, all included
- **Full REST API**, not gated behind a paid plan
- **Optional full-page screenshots** on JS-rendered checks
- Your data never leaves your machine

## Quick start (build from source)

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

Then open **http://localhost:8000**.

Data (SQLite DB + screenshots) persists in the `pricewatch_data` Docker
volume, so it survives container rebuilds/restarts.

If you just want to run the published image instead of building locally,
skip to [Deploying via Dockhand / docker compose](#deploying-via-dockhand--docker-compose) below.

## Publishing: GitHub -> Docker Hub

This repo ships with a GitHub Actions workflow
(`.github/workflows/docker-publish.yml`) that builds a multi-arch
(amd64 + arm64) image and pushes it to Docker Hub automatically.

1. **Create the GitHub repo and push this code.**

   ```bash
   git remote add origin https://github.com/jameshoffman7667/pricewatch.git
   git branch -M main
   git push -u origin main
   ```

2. **Create a Docker Hub access token**: Docker Hub -> Account Settings ->
   Security -> **New Access Token** (read/write scope is enough).

3. **Add two repo secrets** in GitHub: Settings -> Secrets and variables ->
   Actions -> New repository secret.

   | Secret | Value |
   |---|---|
   | `DOCKERHUB_USERNAME` | your Docker Hub username |
   | `DOCKERHUB_TOKEN` | the access token from step 2 |

4. **Push to `main`** (or push a tag like `v1.0.0` for a versioned release).
   The workflow runs the test suite, then builds and pushes:
   - `mybadreligon/pricewatch:latest` on every push to `main`
   - `mybadreligon/pricewatch:1.0.0`, `:1.0`, `:1` on a `v1.0.0` tag
   - `mybadreligon/pricewatch:sha-<shortsha>` on every build, for
     traceability/rollback

   Watch it run under the repo's **Actions** tab. Once it's green, the image
   is live on Docker Hub at `hub.docker.com/r/mybadreligon/pricewatch`.

`docker-compose.yml` already points at `mybadreligon/pricewatch` - no
further edits needed once the image is published.

You don't need to do any of this to run PriceWatch locally - the Quick
Start above (build from source) works standalone. This section is only for
publishing an image other machines (like your Dockhand host) can pull
without a source checkout.

## Deploying via Dockhand / docker compose

Once the image is published to Docker Hub, deploy it anywhere docker compose
runs - including as a Dockhand stack - with just `docker-compose.yml`
(no source code needed on the target host):

1. In Dockhand, create a new stack and paste in the contents of
   `docker-compose.yml` from this repo (or point it at your Git repo if
   Dockhand supports Git-based stacks).
2. Set the stack's environment variables (or upload a `.env` based on
   `.env.example`):
   - `PRICEWATCH_IMAGE` - e.g. `<dockerhubuser>/pricewatch`
   - `PRICEWATCH_TAG` - `latest`, or pin to a version like `1.0.0`
   - `PRICEWATCH_PORT` - host port to expose (default `8000`)
   - `TZ` - your timezone, e.g. `America/Toronto`
3. Deploy the stack. Dockhand will pull the image and start the container;
   the built-in healthcheck reports readiness once `/healthz` responds.
4. Open `http://<host>:<PRICEWATCH_PORT>`.

Data persists in the `pricewatch_data` named volume Dockhand creates for the
stack. To upgrade later, bump `PRICEWATCH_TAG` (or re-pull `latest`) and
redeploy the stack - your monitors and history are untouched.

Plain docker compose works identically, without Dockhand:

```bash
cp .env.example .env   # edit PRICEWATCH_IMAGE to match what you published
docker compose up -d
```

## Adding a monitor

1. Click **+ New Monitor**.
2. Paste the product URL.
3. Leave **selector type** on "Auto-detect price" for most e-commerce sites -
   it scans the common price markup (`itemprop=price`, `data-price`,
   `.price`, Open Graph price meta tags, Amazon's price block, etc.).
   For a tricky page, right-click the price in your browser -> Inspect, copy
   a CSS selector, and switch to "CSS selector" mode.
4. If the price only appears after JavaScript runs (common on modern SPA
   storefronts), check **Render with headless browser**.
5. Set your check interval and alert rules (drop/rise, minimum change,
   target price).
6. Add a notification channel under **Notifications** first if you want
   alerts (e.g. `mailtos://user:pass@gmail.com`, `discord://webhook_id/webhook_token`,
   `slack://TokenA/TokenB/TokenC`, or `ntfy://ntfy.sh/your-topic`). See the
   [Apprise URL docs](https://github.com/caronc/apprise#supported-notifications)
   for the full list of ~80 supported services.

## RedFlagDeals Hot Deals feed

The **Deals** tab tracks new posts to [RedFlagDeals'](https://forums.redflagdeals.com)
Hot Deals forum as they're posted:

- **Unread / Read / Favourited** tabs, with per-deal or mark-all-visible
  "mark as read."
- Each row shows the deal title and price; clicking it opens a detail page
  with:
  - RFD's own AI-generated thread summary, when one exists. While a deal is
    unread, opening/refreshing its page re-checks RFD for a new or updated
    summary (a background job does the same every 10 minutes for deals
    nobody's actively viewing).
  - A link to the thread on RFD and a link to the deal on the retailer's
    own site.
  - Previous/expired RFD threads for the same or a similar product, found
    via RFD's own search.
  - Price history: PriceWatch automatically starts tracking the deal's
    price on the retailer's site the moment it's posted (shown as a chart,
    same as any other monitor), plus outbound links to CamelCamelCamel/Keepa
    (Amazon deals) or RetailRadar.ca/PriceDropper.ca (everything else) for
    price history from before the deal was posted. No paid price-history
    API is used - see the "Investigate: RedFlagDeals feed" project doc for
    why.

New threads are polled from RFD's Atom feed every 5 minutes; nothing needs
configuring for this to start working after deployment.

## REST API

```
GET    /api/monitors
POST   /api/monitors
GET    /api/monitors/{id}
DELETE /api/monitors/{id}
GET    /api/monitors/{id}/history
POST   /api/monitors/{id}/check

GET    /api/deals?tab=unread|read|favourited
GET    /api/deals/{id}
POST   /api/deals/poll        # trigger an immediate feed poll
```

Example: create a monitor programmatically

```bash
curl -X POST http://localhost:8000/api/monitors \
  -H 'Content-Type: application/json' \
  -d '{
        "name": "Headphones @ Example",
        "url": "https://example.com/product/123",
        "selector_type": "auto",
        "interval_minutes": 30,
        "notify_on_price_drop": true,
        "min_change_percent": 1
      }'
```

## How it compares to the paid tools

| | Visualping | Distill | Prisync | **PriceWatch** |
|---|---|---|---|---|
| Monitors | 5 free / paid tiers | 25 free (6h) / paid | pay per product | **unlimited** |
| Check frequency | quota-limited | 6h on free | daily | **unlimited, down to 1 min** |
| JS rendering | paid | paid tiers | n/a | **included** |
| API access | paid tier | limited | paid | **included** |
| History retention | limited | limited | limited | **unlimited** |
| Notification channels | few | few | email only | **~80 via Apprise** |
| Cost | $13-41+/mo | $15+/mo | $99-399+/mo | **$0 (your server)** |

## Architecture

- **FastAPI** app (`app/main.py`) serves the UI (Jinja2 + a small amount of
  vanilla JS/Chart.js) and the JSON API.
- **APScheduler** runs a per-monitor interval job in the background.
- **httpx** fetches static pages fast; **Playwright/Chromium** renders
  JS-heavy ones when a monitor has `render_js` enabled.
- **BeautifulSoup + regex** (`app/extract.py`) pulls the price out via CSS
  selector, regex, or an auto-detect heuristic over common price markup.
- **SQLite** (via SQLModel) stores monitors and an unbounded snapshot
  history, mounted on a Docker volume.
- **Apprise** fans alerts out to whatever notification channels you configure.

## Development / running tests without Docker

```bash
pip install -r requirements.txt
playwright install chromium   # only needed to test JS-rendered monitors
pip install pytest
PRICEWATCH_DATA_DIR=./data pytest tests/ -v
```

The same test command runs automatically in CI (`.github/workflows/docker-publish.yml`)
on every push and pull request, before an image is built or pushed.

## Repo layout

```
app/                     FastAPI app, extraction/fetch/checker logic, templates
app/rfd.py               RedFlagDeals fetch/parse (feed, thread detail, search)
app/rfd_jobs.py          RFD ingest/refresh/related-deal/auto-monitor logic
tests/                   pytest suite (incl. tests/fixtures/ for RFD parsing)
Dockerfile               multi-stage-free image w/ Playwright+Chromium baked in
docker-compose.yml       production compose file - pulls the published image (Dockhand-ready)
docker-compose.dev.yml   local compose file - builds from source
.env.example             config vars for docker-compose.yml
.github/workflows/       CI: test, then build+push multi-arch image to Docker Hub
```

## Notes / limitations

- Respect the terms of service and `robots.txt` of sites you monitor, and
  keep check intervals reasonable so you don't hammer a target site.
- Some sites actively block scrapers/headless browsers; this tool does not
  attempt to bypass bot-detection or CAPTCHAs.
- Auto-detect price extraction is a heuristic - for tricky pages, supply a
  CSS selector.
