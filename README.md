# Community Digest Bot

Curated highlights from multiple communities, automatically published to their respective Telegram channels. Also powers the Community Digest feed and Participation (events) in [My Community](https://github.com/Citizen-Infra/my-community) and [Dear Neighbors](https://github.com/Citizen-Infra/dear-neighbors) Chrome extensions via the REST API.

## Supported Communities

| Community | Output Channel | Status |
|-----------|----------------|--------|
| Citizen Infra Builders | [@citizen_infra](https://t.me/citizen_infra) | Active |
| Novi Sad Relational Tech | [@nsrt_news](https://t.me/nsrt_news) | Paused |
| Sensemaking Scenius | [@scenius](https://t.me/scenius) | Retired 2026-08-25 |

Several further communities are event-only — Newspeak House, Civic Tech Toronto, Metagov
and the Social Internet Unconference contribute events through `/api/events` without a
Telegram link feed or a digest.

*(The repo is named after Sensemaking Scenius, the community it was originally built for.
That group wound down in August 2026; the name stayed.)*

## What It Does

### 1. Meeting Digests
Summarizes community Zoom calls and publishes engaging narrative recaps.
- Source: Fireflies.ai transcripts (auto-recorded from Zoom)
- Trigger: Manual via `/digest-meeting` command in Claude Code

### 2. Weekly Links Roundup
Monitors community conversations and curates the best links shared each week.
- Source: Telegram group topics (Links, Memes, News, Resources, etc.)
- Content understanding: [Firecrawl](https://www.firecrawl.dev/) scrapes each link to generate rich descriptions
- Trigger: Manual via `/digest-links [group]` command in Claude Code (autonomous generation planned — see [Roadmap](#roadmap))

### 3. Events Aggregation
Unified events feed from multiple sources, consumed by MC and DN extensions.
- Source A: Telegram event links (enriched with date/location from Luma API, Meetup/Eventbrite ld+json)
- Source B: External event APIs (Luma calendar polling)
- Served via `GET /api/events` with community and city filters

## Architecture

```
┌───────────────┐   ┌──────────────────┐        ┌───────────────┐
│ Zoom Meetings │   │ Telegram Groups  │        │ External APIs │
└───────┬───────┘   └────────┬─────────┘        │ (Luma, etc.)  │
        │                    │                  └───────┬───────┘
        ▼                    ▼                          │
┌───────────────┐   ┌──────────────────┐         ┌──────┴───────┐
│ Fireflies.ai  │   │ Vercel Webhook   │         │   REST API   │
│ (transcripts) │   │ + OG metadata    ├────────►│ GET /api/... │
└───────┬───────┘   │ + event enrich   │         └──────┬───────┘
        │           │ + Supabase       │                │
        │           └────────┬─────────┘                ▼
        │                    │              ┌─────────────────────────────────┐
        │              ┌─────┴─────┐        │ Chrome Extensions               │
        │              │ Firecrawl │        │ (Dear Neighbors, My Community)  │
        │              │ (scraping)│        └─────────────────────────────────┘
        │              └─────┬─────┘
        └────────┬───────────┘
                 ▼
        ┌─────────────────┐
        │   Claude Code   │
        │ (or Claude API) │
        └────────┬────────┘
                 │
                 ▼
        ┌─────────────────┐
        │ POST /api/      │
        │ send-message    │──────► Telegram Channels
        └─────────────────┘
```

## Setup

### Meeting Digests
Uses Claude Code with Fireflies MCP:
- Fireflies.ai for meeting transcripts
- Posts via Telegram Bot API
- See [CLAUDE.md](CLAUDE.md) for digest format guidelines

### Links Monitor
Serverless Python functions on Vercel with Supabase storage.

Deploys run automatically on push to `main`. The command below is the manual fallback and
requires being logged in to the Vercel account that owns the project.

```bash
# Manual deploy (fallback)
vercel --prod

# Set environment variables
vercel env add BOT_TOKEN
vercel env add WEBHOOK_SECRET
vercel env add SUPABASE_URL
vercel env add SUPABASE_SERVICE_KEY

# Register Telegram webhook
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://scenius-digest.vercel.app/api/webhook","secret_token":"...","allowed_updates":["message"]}'
```

## API

Deployed at `https://scenius-digest.vercel.app`. Used by Claude Code for digest generation, by [My Community](https://github.com/Citizen-Infra/my-community) for the digest feed + events, and by [Dear Neighbors](https://github.com/Citizen-Infra/dear-neighbors) for events.

| Endpoint | Description |
|----------|-------------|
| `GET /api/links` | Unpublished links (for digest generation). Rows carry `published_at` — the date a link went out in a digest, `null` for anything published before 2026-08-25 |
| `GET /api/links?all=true` | All links including published (for My Community) |
| `GET /api/links?group=cibc` | Links from specific group |
| `GET /api/events` | All upcoming events across communities |
| `GET /api/events?community=nsrt` | Events for a specific community |
| `GET /api/events?city=novi-sad` | Events by city (used by Dear Neighbors) |
| `GET /api/groups` | List configured groups with event metadata |
| `POST /api/mark-published` | Mark as published: `{"ids": [1,2,3]}` |
| `POST /api/send-message` | Post to Telegram: `{"chat_id": "...", "text": "..."}` (Bearer `WEBHOOK_SECRET`) |
| `POST /api/backfill-og` | Backfill OG metadata for stored links (Bearer `WEBHOOK_SECRET`) |
| `GET /api/health` | Health check |

### Private communities are filtered, not errored

`/api/links`, `/api/events` and `/api/groups` all narrow their results to communities the
caller may see. A community marked `visibility: private` in community-admin is visible only
to a caller presenting a community-admin ES256 JWT whose claims include it.

**An anonymous request for a private community returns a valid `group_id` alongside
`count: 0`** — indistinguishable from a community that has collected nothing. This is
deliberate: it is what stops a private group's existence leaking to unauthenticated
callers. It is also the single most confusing behaviour in this API, and it has been
misread as "the bot stopped working" more than once.

If a group you expect to have links returns zero, check its `visibility` before checking
anything else.

The canary for the whole mechanism is one unauthenticated request: `GET /api/groups` should
return `cibc` and nothing else. If a private community appears there, the community-admin
config fetch is failing and the app has silently fallen back to `groups.json`, which marks
nothing private.

## Claude Code Commands

This repo includes custom slash commands for Claude Code:

| Command | Description |
|---------|-------------|
| `/digest-links` | Generate weekly links roundup (asks which group) |
| `/digest-links cibc` | Generate digest for CIBC |
| `/digest-meeting` | Generate digest from latest meeting |

### Usage

```bash
git clone https://github.com/zhiganov/scenius-digest
cd scenius-digest
claude  # start Claude Code
```

Then type `/digest-links cibc` or `/digest-meeting`.

### Requirements

To use these commands, you need Claude Code configured with:
- **Fireflies MCP** - for accessing meeting transcripts (meeting digests only)
- **Firecrawl MCP** - for scraping link content to generate rich descriptions (links digests)
- **Bot token** - for posting to Telegram (stored as Vercel env var)

Contact [@zhiganov](https://t.me/zhiganov) if you want to help with digest generation.

## Adding a New Community

1. Add bot to the Telegram group as admin
2. Run `/debug` in topics to get IDs
3. Register the community in [community-admin](https://github.com/Citizen-Infra/community-admin), which
   serves group config to this app at runtime via `CA_CONFIG_URL` → `GET /api/config`
4. Optionally mirror it into `groups.json`, which is only the **fallback** used when that
   fetch fails
5. No webhook re-registration needed (same endpoint)

`groups.json` marks nothing private, so a community whose visibility matters should be
configured in community-admin and — if in doubt — left out of the fallback entirely.

## Roadmap

### Autonomous Digest Generation

Currently, digest generation requires a Claude Code session — someone runs `/digest-links cibc`, Claude scrapes the links via Firecrawl, writes the narrative, and posts it. The goal is to make this fully autonomous.

The API surface is almost complete:

| Step | Endpoint | Status |
|------|----------|--------|
| Fetch links | `GET /api/links?group={group}` | Done |
| Scrape & generate narrative | `POST /api/generate-digest` | Planned |
| Post to Telegram | `POST /api/send-message` | Done |
| Mark as published | `POST /api/mark-published` | Done |

The missing piece is a serverless function that calls the Claude API with link metadata (OG titles/descriptions are already stored) to generate the digest narrative. This would enable:
- **Scheduled digests** via Vercel cron or GitHub Actions
- **Bot-triggered digests** via a `/digest` Telegram command
- **Community-run digests** without needing Claude Code access

See [GitHub issue #1](https://github.com/zhiganov/scenius-digest/issues/1).

### Slack Integration

Multi-platform link collection from Slack workspaces (starting with Metagov). See `docs/plans/2026-02-12-slack-integration-design.md`.

## Contributing

Open source, maintained at [zhiganov/scenius-digest](https://github.com/zhiganov/scenius-digest). PRs welcome!
