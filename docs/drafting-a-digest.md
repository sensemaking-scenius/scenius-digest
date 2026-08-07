# Drafting a links digest

The bot collects links posted in a community's Telegram threads. This document
covers turning those links into a **draft digest**: fetch, triage, read the
sources, write. It assumes nothing but network access and a Firecrawl key.

## Scope — read this before anything else

This covers producing a draft and handing it to the maintainer. It deliberately
**does not** cover publishing, marking links published, or the announcements
section. Do not attempt those steps, and do not go looking for the credentials
they need.

The boundary is not bureaucratic. Each of the excluded steps is irreversible in a
way drafting is not:

- **Publishing** posts to a live community channel under a person's byline. Deleting a message afterwards does not unsend it.
- **The bot credential** can post to *every* channel the bot belongs to, not only the intended one. A mistyped destination puts one community's digest in front of another.
- **Marking links published** is one-way. There is no unmark, so a wrong call silently removes links from every future digest and leaves no trace of which ones.
- **The announcements section** is rendered from a private source that is not part of this repo.

Your output is a draft plus a report. A human takes it from there.

## What you need

A Firecrawl API key, as `FIRECRAWL_API_KEY`. Nothing else — the links API is
public and unauthenticated.

---

## 1. Fetch the links

```
GET https://scenius-digest.vercel.app/api/links?group=<group>
```

Groups are `cibc` and `scenius`. The endpoint returns **all unpublished** links,
which is usually far more than belong in one digest.

## 2. Triage — curation is the job, not inclusion

Do not dump the list. Propose a three-way split and get it approved before
reading anything:

| Bucket | What goes in it |
|---|---|
| **Publish now** | the strongest 6–10: time-sensitive items, substantive long-reads, named ecosystem builds |
| **Skip** | duplicates of recent coverage, off-topic, weak |
| **Save for later** | evergreen pieces, weaker hooks, anything that can wait a week |

The maintainer knows what has already been covered and what was held back last
time. Ask; do not assume.

**Section placement comes from the bot, not from you.** Every link carries a
`topic` field set from the Telegram thread it was posted in, and it is
authoritative. Use it. Do not re-derive a section from the title.

**Count topics programmatically before saying anything about the distribution.**
Parse the full JSON and tally, e.g. `Counter(l['topic'] for l in links)`. A
partial read of the rows is exactly how "they're all tagged news" gets asserted
about a set that isn't.

## 3. Read the sources — full text, not summaries

OG metadata is marketing prose at ~200 characters. It means "I have not read
this."

A summary-format scrape is only a half-read: it flattens multi-author bylines to
"the authors", drops the named figures that make an entry worth reading, and
undersells scale — a $2.5B partnership becomes "a non-profit". Use
`formats: ["markdown"]` with `onlyMainContent: true`, and actually read the
result. Batch in parallel.

- Summary format is fine for **triage only** — deciding whether something is worth publishing — never as the basis for what you write.
- **Loader stubs:** publisher epub and reader URLs return "loading a 3.6 MB publication" and nothing else. Scrape the article or abstract URL instead, which also carries the full author list in its metadata.
- **Oversized output** gets saved to a file rather than returned. Grep it for the byline and the key figures. Do not drop the source — long pages are usually the ones worth reading.

Skip fetching only for LinkedIn posts and X links, where the OG text *is* the
post, and for YouTube, where the metadata already gives you title and
description.

## 4. Write the draft

Structure is a lead-in per section naming the through-line that connects its
links, then a real sentence or two per link, grouped by theme. Sections are
`📰 News`, `📚 Resources`, and — for cibc only — `🏛 Deliberative Tech`, omitted
entirely when empty.

Default to HTML inline links (`<a href="URL">text</a>`), which saves roughly
80–150 characters per entry against separate URL lines and usually buys three or
four more entries.

**Every entry must name at least one specific from the content you read** — an
author, a deadline, a named feature, a concrete number. If you cannot name one,
you have not read the piece; go back to step 3.

**Credit every author, not just the first.** Attributing a three-author essay to
one person is an error that author will notice, on a post that goes out under
someone else's name. Page metadata lies here: a `citation_author` field
frequently lists one name for a co-authored piece, and byline extraction
sometimes returns the *illustrator's* credit instead of the writers'. Check the
rendered byline and any contributor block before naming anyone. Give
affiliations where the source states them, plus publication and date. For a
paper with more authors than the format can carry, lead with the first and name
the recognisable contributors with a count. If sources disagree on the byline,
say so in your report rather than picking one.

### Measuring length

The ceiling is **4096 UTF-16 code units of rendered text**. HTML tags and `href`
URLs do not count toward it — they become entities — but each non-BMP emoji
counts as two.

So measure `len(visible.encode('utf-16-le')) // 2` after stripping tags and
unescaping entities, not the raw string length. Raw length badly overstates: a
5165-character raw draft measured 4061 real units. A naive character count
understates. Leave margin, and report the number you measured and how.

If full-depth entries overrun, **do not silently compress**. Depth and the limit
genuinely conflict at eight or more items. Put the choice to the maintainer:
move the weakest items to save-for-later, or split into two messages. Gutting
every entry down to a clause defeats the point of having read the sources, and
is the one option not to take on your own.

### Register

A woven narrative, not a blurb list. Connective tissue between items, and room
for each item — not a flat "Title — description" sequence, which reads
mechanical, and not one dense paragraph where every link shrinks to a clause.
Conversational, specific, and interested in the ideas.

Do not invite readers to join the source group or contribute links to it;
non-members cannot post there.

## 5. Hand off

Report, in one place:

- The draft.
- Your measured length, and the method.
- The three triage buckets, with link IDs, so the maintainer can act on them.
- Every entry where you could not verify a byline, figure, or claim — say what you left out rather than filling the gap.
- Anything in this document that was unclear, missing, or that you worked around.

Then stop. Do not publish, do not mark anything published, and do not write the
announcements section.
