# Scenius Digest Architecture Reference

Read this file when working on internals. Not loaded every session.

## System Diagram

```
Zoom Meetings ──► Fireflies.ai ──┐
                                 ├──► Claude Code ──► Telegram Channels
Telegram Groups ──► Webhook ──► Supabase
                   (+ OG/events)    ├──► /api/links ──► My Community (digest feed)
Slack Workspaces ─► Slack Event ──┘ ├──► /api/events ──► MC + DN (participation)
                   (planned)        │
External APIs ──────────────────────┘    (Luma, guild.host)
```

## Serverless Functions (`api/`)

- `api/webhook.py` - Telegram webhook handler (receives messages, fetches OG metadata, enriches events, stores links)
- `api/links.py` - GET links (used by Claude Code for digests and My Community for the digest feed)
- `api/events.py` - GET unified events feed (aggregates Telegram event links + external APIs like Luma). Filters: `?community=nsrt`, `?city=novi-sad`
- `api/groups.py` - GET configured groups with city/event metadata (used by MC for community selection)
- `api/mark_published.py` - POST mark links as published
- `api/backfill_og.py` - POST backfill OG metadata for existing links missing it
- `api/send_message.py` - POST send message to a chat (accepts `{"chat_id": "...", "text": "..."}`, auth via Bearer WEBHOOK_SECRET)
- `api/health.py` - GET health check

## Shared Modules (`lib/`)

- `lib/config.py` - Env vars + groups.json/event_sources.json loading + helpers (`is_event_topic()`, `get_all_event_groups()`)
- `lib/database.py` - Supabase client (`digest_links` table, `add_link()`, `get_event_links()`)
- `lib/telegram.py` - Telegram Bot API helper (sendMessage via urllib)
- `lib/opengraph.py` - Open Graph metadata fetcher (stdlib only, 5s timeout, 32KB read limit)
- `lib/event_enrichment.py` - Event platform detection (Luma/Meetup/Eventbrite) + structured data extraction
- `lib/luma.py` - Luma calendar API fetcher (future events from a calendar URL)
- `lib/guildhost.py` - guild.host events fetcher (scrapes Relay store from SSR page via bot user-agent)
- `lib/eventus.py` - eventus.city events fetcher (archived — events lacked metadata and linked to unrelated Telegram groups)

## Design Docs

- `docs/plans/2026-02-08-events-aggregation-design.md` - Events API design (implemented)
- `docs/plans/2026-02-12-slack-integration-design.md` - Slack bot integration for multi-platform link digests

## Slash Commands

- `.claude/commands/digest-links.md` - Weekly links roundup workflow (supports group argument)
- `.claude/commands/digest-meeting.md` - Meeting digest workflow

**Legacy** (`bot/`): Original Fly.io bot (python-telegram-bot + SQLite + aiohttp). Kept for reference only — not deployed.

## Multi-Group Configuration

Telegram-based communities are defined in `groups.json` (project root). Non-Telegram communities with external event sources only are in `event_sources.json` (interim — will be replaced by community-admin's `GET /api/config`).

```json
{
  "scenius": {
    "name": "Sensemaking Scenius",
    "group_id": "-1002141367711",
    "output_channel": "-1002708526104",
    "city": null,
    "topics": { "links": "230", "memes": "4605", "events": "2156", "ai-tools-library": "6430" },
    "event_topics": ["events"],
    "event_apis": []
  },
  "cibc": {
    "name": "Citizen Infra Builders",
    "group_id": "...",
    "output_channel": "...",
    "topics": { "news": "...", "resources": "...", "events": "..." },
    "event_topics": ["events"],
    "event_apis": [{ "type": "luma", "url": "...", "api_id": "cal-..." }]
  },
  "nsrt": {
    "name": "Novi Sad Relational Tech",
    "group_id": "-1003669626939",
    "output_channel": "-1003857482838",
    "city": "novi-sad",
    "topics": { "links": "16", "events": "8" },
    "event_topics": ["events"],
    "event_apis": [{ "type": "luma", "url": "https://luma.com/cibc", "api_id": "cal-8H09wJN7syCCaRR" }]
  }
}
```

Each group in `groups.json` can have:
- `platform` — `"telegram"` (default if omitted) or `"slack"`. Determines ingestion path.
- `city` — slug for `/api/events?city=` filtering (used by Dear Neighbors)
- `event_topics` — Telegram topics where links are treated as events (enriched with date/location)
- `event_apis` — external event sources polled by `/api/events` (Luma calendars, guild.host communities)

Each entry in `event_sources.json` has: `name`, `city`, and `event_apis`. The events API (`/api/events`) merges both files when querying.
  - Luma: `{ "type": "luma", "url": "...", "api_id": "cal-..." }` — `api_id` is required since Luma migrated from lu.ma to luma.com and the URL slug no longer works as an API key. Find the `cal-` ID by searching for `cal-` in the page source of the Luma calendar page.
  - guild.host: `{ "type": "guildhost", "url": "https://guild.host/{slug}/events" }` — scrapes SSR page using bot user-agent

### Slack Integration (planned)

Slack-based communities (like Metagov) use an OAuth-installed Slack app instead of the Telegram webhook. Channel-to-topic mappings are stored in a `slack_installations` Supabase table, not in `groups.json`. Links are stored in the same `digest_links` table with `source = 'slack'`. Digests still post to Telegram. See `docs/plans/2026-02-12-slack-integration-design.md` for full design.

## Database

Uses `digest_links` table in the scenius-digest Supabase project. Schema:

```sql
CREATE TABLE digest_links (
  id BIGSERIAL PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  description TEXT,
  group_id TEXT,
  group_name TEXT,
  topic TEXT NOT NULL,
  topic_thread_id BIGINT,            -- raw Telegram message_thread_id at ingest (attribution audit; nullable)
  shared_by TEXT,
  shared_at TIMESTAMPTZ DEFAULT NOW(),
  message_id BIGINT,
  message_text TEXT,
  published BOOLEAN DEFAULT FALSE,
  published_at TIMESTAMPTZ,           -- when the digest went out; NULL for rows published before 2026-08-25
  og_title TEXT,
  og_description TEXT,
  og_image TEXT,
  type TEXT DEFAULT 'link',          -- 'link' or 'event'
  event_starts_at TIMESTAMPTZ,       -- event start time (enriched)
  event_location TEXT                 -- event location (enriched)
);
```

OG metadata (`og_title`, `og_description`, `og_image`) is fetched automatically when the webhook stores a new link. Uses stdlib `urllib` with a 5-second timeout and reads only the first 32KB of HTML. Falls back to `<title>` and `<meta name="description">` when OG tags are absent. Consumers should prefer `og_title` over `title` and `og_description` over `description` when available.

**Event enrichment:** Links shared in `event_topics` are stored with `type='event'`. The webhook calls `enrich_event()` which extracts structured data (start time, location) from known platforms — Luma (both `lu.ma` and `luma.com` domains) via public API, Meetup/Eventbrite via ld+json parsing. The `/api/events` endpoint also re-enriches Telegram events at read time to pick up rescheduled dates and updated locations.
