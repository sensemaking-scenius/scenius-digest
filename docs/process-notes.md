# Process Notes — scenius-digest

> **Canonical location:** `claude-config/docs/scenius-digest/process-notes.md` — the private cross-machine config repo. Operational details (env-var rotations, infra decisions, repo-transfer history) live there so they sync across machines and stay out of this public repo's working tree.
>
> Pull the latest claude-config (`zhiganov/claude-config`, private) on each machine. See `claude-config/README.md` for setup.

## 2026-06-22 — Persist message_thread_id (topic-attribution audit)
- **Done:** Closed the topic-attribution observability gap — added `digest_links.topic_thread_id` (Supabase migration + PostgREST reload), threaded it through `add_link` + `webhook.py`, plus a log line when a link is dropped from an unmapped/General topic. Pushed (7e5ad17); closes #11.
- **Decisions:** Round-trip-verified the column. Corrected my own mis-diagnosis that Vercel auto-deploy was broken — #3 was stale (deploys land on push), closed it. The Vercel MCP/CLI token can't see this project (it sits under the "Artem's projects" team, not Harmonica).
- **State:** Merged to main, auto-deploys. `topic_thread_id` populates on the next link in a monitored cibc topic (none since deploy yet).
- **Next:** confirm it populates once a real link lands.

## 2026-06-26 — /api/events: filter to real events + date parsing (#12)
- **Done:** `/api/events` now drops bare-link junk from the Telegram events topic (keep only if dated or an event-page URL) and dates more events: Eventbrite all TLDs, ld+json Event subtypes + `@graph`, generic ld+json fallback for event-ish URLs. Pushed (bd81ad2), deployed, verified live (cibc 16→12, dated 5→7). Closes #12.
- **Decisions:** Enrichment runs live at request time, so the fix took effect on next request. addevent / Zoom-registration pages have no structured data → stay undated (the my-community consumer hides undated). Surfaced during my-community Participation verification.
- **State:** Merged to main, deployed, verified.
- **Next:** none.

## 2026-06-27 — #13 gate; community-admin config seam; V7 visibility filter
- **Done:** (1) **#13** — `/api/groups` hides `group_id`/`output_channel` behind a read-only Bearer secret (avails sends it via its own secret); closed. (2) **Config seam** — `config.py` now reads community config from community-admin `GET /api/config` (60s TTL cache; `MONITORED_GROUPS` via PEP-562; `groups.json` fallback); verified live propagation (~60s). (3) **V7** — `/api/groups` / `/api/events` / `/api/links` filter private communities by `?identity=` (members from `/api/config`); verified hidden-from-anon / visible-to-member live.
- **Decisions:** `groups.json` stays as the fallback (zero-disruption; R8 held — consumers unchanged). `?identity=` is self-asserted (obscurity, not access control) → being replaced by verified JWTs (community-admin#21).
- **State:** All deployed + verified live.
- **Next:** IdP **S2** — verify community-admin JWTs via JWKS, filter by the `memberships` claim, drop `?identity=` + `members`-in-`/api/config`.

## 2026-06-27 — IdP S2: verify tokens, drop ?identity=
- **Done:** scenius-digest now verifies community-admin ES256 JWTs offline via JWKS (`lib/auth.py`, PyJWT[crypto]) and gates private communities by the verified `memberships` claim across `/api/groups`, `/api/events`, `/api/links`. Removed the self-asserted `?identity=` param. Added the repo's first pytest suite (11 tests: 6 auth + 5 config). Pushed + deployed.
- **Decisions:** Verify path fails closed — any missing/invalid/expired token or JWKS failure → empty member set → public only; private is never served without a valid token. `CONFIG_READ_SECRET` (#13 avails gate) left untouched; it coexists with the JWT path on `/api/groups`. Built subagent-driven (TDD); Opus final whole-branch review = READY TO ROLL OUT, 0 Critical/Important.
- **State:** Live. Verified anon → 3 public communities (cibc/nsrt/scenius); a real token decodes with the correct `iss` + slug memberships; JWKS live. The private-gating reveal is not demonstrable in prod (no private community has a Telegram `group_id`) — proven by tests + review, to be exercised in S3.
- **Next:** S3 — MC/DN email sign-in send Bearer tokens, exercising this gating end-to-end with real data.

## 2026-07-03 — cibc digest empty: upstream visibility-flip (no code change here)
- **Done:** Diagnosed `/api/links?group=cibc` returning 0 despite ~100 unpublished DB rows. Root cause upstream: cibc + scenius had been flipped to `visibility: private` in community-admin's live DB, and the S2 filter (`api/links.py` → `config.visible_groups`) correctly hides private communities from callers without a verified JWT — and the `/digest-links` curl carries none. Artem reverted both to public via the community-admin panel; digest then shipped.
- **Decisions:** No scenius-digest code change — behaving as designed. (The `topics:{links,memes}` field in the /api/links response is hardcoded scenius-centric counting — a red herring, not per-group.)
- **State:** cibc + scenius public again; digest posted to @citizen_infra (msg 385). Failure mode to remember: a community flipped to `private` upstream silently empties its PUBLIC digest/feed even though the DB still holds the links — check `/api/config` visibility before suspecting this repo. The digest read-path is unauthenticated by design.
- **Next:** nsrt is dark — absent from `/api/config` (not active or missing group_id) → community-admin#31.

## 2026-07-10 — V6 Source C (manual events merge)
- **Done:** Added community-admin manual events as a third source in `GET /api/events` (V6). `lib/config.py: manual_events_url()` derives the endpoint from `CA_CONFIG_URL`; `_fetch_manual_events()` is Bearer-authed + best-effort (returns `[]` on any failure, never breaks the feed); Source C filters `community in groups` against the ALREADY visibility-filtered `groups`, so private communities inherit the gate for free. PR #14 → `9e51cd9`, merged + deployed. 21 tests (10 new).
- **Decisions:** No new env var (reuse `CA_CONFIG_URL`/`CA_CONFIG_SECRET`). Merge is additive; degrades gracefully.
- **State:** main clean; live. Verified end-to-end via community-admin (a manual event on cibc surfaced here as `source:manual`, then removed).
- **Next:** none for this repo; MC/DN voting evolves under the consent-surface initiative (community-admin#39).

## 2026-07-12 — vercel.json send-message/backfill-og rewrites
- **Done:** Added `/api/send-message` + `/api/backfill-og` → underscore-filename rewrites in `vercel.json` (mirroring existing `mark-published`), fixing a silent 404 — the documented hyphen URLs were unreachable (only `mark-published` had a rewrite). Pushed to main (`1b6cde0`), auto-deployed, verified. Was breaking community-admin's consent notifier.
- **Decisions:** none (config completion).
- **State:** main clean + pushed + deployed; documented API URLs now all resolve.
- **Next:** none.

## 2026-07-16 — Probe: reactions here are ATTRIBUTED
- **Done:** Read-only probe of the live Bot API (`getMe`/`getWebhookInfo`/`getChat`/`getChatMember`) to settle whether reaction updates would be attributed or anonymous. No prod change made.
- **Decisions:** Answered the question without flipping `allowed_updates` — chat type + bot admin status fully determine it, so `getChat` + `getChatMember` sufficed.
- **State:** All three monitored groups (scenius `-1002141367711`, cibc `-1003188266615`, nsrt `-1003669626939`) are **supergroups with @sensemaking_bot already an administrator** → `message_reaction`, i.e. attributed, carrying the reacting user. Only the output *channels* give anonymous `message_reaction_count`, and proposals don't live there. `getWebhookInfo` confirms `allowed_updates: ['message']`, url `.../api/webhook`, 0 pending. Bot id 8511113052; token in `.env.local` is live.
- **Next:** #15 — handle `message_reaction` in `api/webhook.py:52` (currently early-returns on missing `message` key), and **store a salted hash of the reactor id, never the id**: attribution means we'd otherwise be collecting who-reacted-to-what across three communities. `allowed_updates` is a manual `setWebhook` curl (README:86-89), not code — a code-only PR silently does nothing.

## 2026-08-04 — silent outage: verified members served public-only for a day
- **Done:** Found and fixed #16. `CA_ISSUER` still pinned community-admin's old Railway host while CA stamps `iss` from `API_URL`, which moved 2026-08-02 — so every valid identity token was rejected. `member_ids_from_request` returns an empty set on any failure, so members of the private `scenius` community saw exactly what an anonymous caller sees: **29 links instead of 102**, for a day, with no error and no log line. Added coverage for the issuer-pin branch and an unreachable JWKS, plus a log line naming the rejection cause.
- **Decisions:** **`CA_JWKS_URL`, `CA_CONFIG_URL` and the events URL stay on the Railway hostname.** `admin.citizeninfra.org` is Cloudflare-proxied and 403s `Python-urllib` — the agent `PyJWKClient` and `urllib.request` use. Moving them would reintroduce the same silent failure; moving `CA_CONFIG_URL` would be worse, since the `groups.json` fallback marks nothing private and would expose `scenius` to anonymous callers.
- **State:** Fixed, redeployed, verified with a real token — `/api/groups` now returns `['cibc','scenius']` authenticated vs `['cibc']` anonymous. Issue closed on that evidence.
- **Next:** Cloudflare WAF skip for `/.well-known/*` (community-admin#26) unpins the three URLs. The autouse fixture still sets `CA_ISSUER = None`, so read the new tests before trusting the suite covers production config.
