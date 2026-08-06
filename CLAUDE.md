# CLAUDE.md

Multi-community digest system: collects links from Telegram groups, serves curated digests and a REST API for the My Community extension.

**Communities:** Scenius (@scenius), CIBC (@citizen_infra), NSRT (@nsrt_news). Plus event-only communities (Newspeak House, Civic Tech Toronto, Metagov) via `event_sources.json`.

**Outputs:** Meeting digests → Telegram, Weekly links roundup → Telegram, REST API for links + events → My Community / Dear Neighbors extensions.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env

# Auto-deploy: push to main on github.com/zhiganov/scenius-digest triggers Vercel build.
# Manual fallback (requires login as tema.zhiganov@gmail.com for "Artem's projects" team):
npx vercel --prod

# Env vars (set via Vercel dashboard — Artem's projects → scenius-digest → Settings → Environment Variables)
# Required: BOT_TOKEN, WEBHOOK_SECRET, SUPABASE_URL, SUPABASE_SERVICE_KEY
# WEBHOOK_SECRET is dual-use: Telegram secret_token header + Bearer auth for send-message/backfill endpoints
```

### community-admin coupling — three pinned values, all fetched with `urllib`

`CA_CONFIG_URL`, `CA_JWKS_URL` and `CA_ISSUER` point at community-admin. Two hard-won constraints (#16):

- **`CA_ISSUER` must equal community-admin's `API_URL`**, because that is what it stamps as `iss` (`jwt.js:28`). It is a literal string compare, so when CA moved host on 2026-08-02 and this did not follow, every valid token was rejected — and `member_ids_from_request` returns an empty set on any failure, so verified members were served **public-only** content for a day with no error, no 401, and (then) no log line. It logs now. `/api/groups`, `/api/links` and `/api/events` all widen visibility from that set; the outage cost Sensemaking Scenius members 73 of 102 links.
- **`CA_CONFIG_URL` failing is silent and makes private communities public.** `lib/config.py:78` falls back to `groups.json` on any error, and that file marks nothing private — so a broken value does not 500, it exposes `scenius`. **The canary is a single unauthenticated request:** anonymous `GET /api/groups` must return `{"groups": {"cibc": ...}}` and nothing else. If a private community appears there, the config fetch is failing — revert and redeploy immediately. Run it after any change to these vars; it needs no token, which is why there is no excuse for skipping it.

  **Host moved 2026-08-06.** `CA_CONFIG_URL` and `CA_JWKS_URL` now point at `admin.citizeninfra.org`; the events URL follows automatically (`manual_events_url()` rewrites `/api/config` → `/api/events/manual`). They had been pinned to `community-admin-server-production.up.railway.app` because the citizeninfra host 403'd Python's default user agent — `lib/config.py:78`, `api/events.py:130` and `PyJWKClient` all fetch via `urllib` and none sets a `User-Agent`. A Cloudflare Configuration Rule now disables the Browser Integrity Check for `/.well-known/`, `/api/`, `/oauth/` and `/panel/oauth/` on that host (ruleset `112c19aa`, rule `f79f50ba`). Post-move checks: anonymous `/api/groups` → `['cibc']`, `/api/links` → 33 (unchanged), `/api/events` → 25 including one `manual`, which is the derived third URL proving itself.

  Three things worth keeping, because each cost real time. It was **not the WAF** — the 403 body is `error code: 1010`, the Browser Integrity Check, a *zone setting*, so the instrument is `set_config`, not a WAF skip. **`/.well-known/*` alone was never enough**: BIC blocks the whole host, and only `CA_JWKS_URL` sits under that prefix. And config rules **take seconds to propagate** — a probe run immediately after creation still showed 403s and read exactly like a broken expression. Full record: **community-admin#26**.

Vercel injects env at **deploy** time, so changing a value in the dashboard does nothing until a redeploy. Rule + episodes: cibc-brain `decisions/2026-08-03-identifiers-accept-a-set-during-migration.md` (D-08).

**Repo moved 2026-04-17** from `sensemaking-scenius/scenius-digest` to `zhiganov/scenius-digest` so the Vercel GitHub App could attach cleanly to the personal team (cross-org GitHub App install kept failing). Vercel project moved from Harmonica → Artem's projects team in the same batch.

### Webhook Registration

```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook"

curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://scenius-digest.vercel.app/api/webhook","secret_token":"YOUR_SECRET","allowed_updates":["message"]}'
```

## API

Deployed at `https://scenius-digest.vercel.app`.

| Endpoint | Description |
|----------|-------------|
| `GET /api/links` | All unpublished links |
| `GET /api/links?group=cibc` | Links from specific group |
| `GET /api/links?days=14` | Links from last N days |
| `GET /api/links?all=true` | All links including published (for MC digest feed) |
| `GET /api/events` | All upcoming events across communities |
| `GET /api/events?community=nsrt` | Events for a specific community |
| `GET /api/events?city=novi-sad` | Events for communities in a city (used by DN) |
| `GET /api/groups` | List configured groups with city/event metadata |
| `POST /api/mark-published` | Mark as published: `{"ids": [1,2,3]}` |
| `POST /api/send-message` | Send message: `{"chat_id": "...", "text": "..."}` (Bearer WEBHOOK_SECRET) |
| `POST /api/backfill-og` | Backfill OG metadata (Bearer WEBHOOK_SECRET) |
| `GET /api/health` | Health check |

Links response includes `group_id`, `group_name`, `message_text`, and OG metadata (`og_title`, `og_description`, `og_image`).

Events response includes `id`, `title`, `description`, `image`, `url`, `starts_at`, `ends_at`, `location`, `source`, `community`.

## Bot Commands

| Command | Description |
|---------|-------------|
| `/debug` | Show chat/topic IDs, check if monitored |
| `/groups` | List all configured groups |
| `/stats [group]` | Show link statistics |

## MCP Integrations

- **Fireflies MCP** — meeting transcripts (`keyword:"scenius" scope:title`)
- **Firecrawl MCP** — scrape link content for digest summaries

## Posting to Telegram

```bash
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "{output_channel}", "text": "...", "disable_web_page_preview": true}'
```

BOT_TOKEN is stored as a Vercel environment variable.

---

## Digest Generation Instructions

### Meeting Digests

Source: Fireflies.ai transcripts filtered by `keyword:"scenius" scope:title`

Format:
```
📋 [Meeting Title] Digest
🗓 [Date] • ⏱ [Duration] min

[Engaging narrative paragraphs - tell the story of what was discussed. Highlight interesting ideas, projects, insights. Conversational tone. Include specific details - numbers, project names, concepts.]

[Second paragraph diving into highlights that would interest people outside the community.]
```

### Weekly Links Roundup

Source: `GET https://scenius-digest.vercel.app/api/links?group={group}`

Workflow:
1. Fetch links from API (with group filter)
2. Fetch each URL to understand content
3. Generate narrative digest
4. Post to group's output_channel
5. Mark links as published via API

Format:
```
🔗 {Group Name} Links Digest
🗓 Week of [Monday date of current week]

[Opening sentence about what the community explored this week.]

📚 Worth Reading / 📰 News / 📚 Resources (topic-appropriate)

[1-2 sentence description per link - why it's interesting, why it matters]

• [Title] - [URL]

🎭 Memes & Delight (if applicable)

[Brief fun intro]

• [URL]
```

### Important Notes

- **No closing CTA**: Do NOT add a closing line inviting people to contribute or join. The output channels are public-facing and read by non-members who can't post to the source group.
- **Week starts on Monday**: The "Week of" date should always be the Monday of the current week.
- **Aware of prior posts**: The API returns only unpublished links, but other links may have already been posted earlier in the week. Don't comment on volume.

### Writing Style

- Narrative and engaging, not bullet points
- Highlight interesting/novel ideas
- Specific details (numbers, names, concepts)
- Conversational tone for Telegram
- Credit sharers when relevant (e.g., "via @username")

### What NOT to Include

- Action items or internal task assignments
- Internal governance details
- Sensitive/private discussions
- Broken links
- Transcript links (require login)

## Communities

| Community | Key | Link source | Digest output | Events |
|-----------|-----|-------------|---------------|--------|
| Sensemaking Scenius | scenius | TG topics: links, memes, events, ai-tools-library | @scenius | TG events |
| Citizen Infra Builders | cibc | TG topics: news, resources, events | @citizen_infra | TG events + Luma |
| Novi Sad Relational Tech | nsrt | TG topics: links, events | @nsrt_news | TG events + Luma |
| Newspeak House | newspeak-house | — (community-admin) | — | Luma |
| Civic Tech Toronto | civic-tech-toronto | — (community-admin) | — | guild.host |
| Metagov | metagov | — (community-admin) | — | Luma |

## Reference

Read when working on internals: [Architecture](docs/architecture.md) — system diagram, serverless functions, shared modules, multi-group config, database schema, event enrichment.
