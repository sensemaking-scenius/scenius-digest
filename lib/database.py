import os
from datetime import datetime, timedelta, timezone
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")  # scenius-digest project
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def add_link(url: str, topic: str, shared_by: str = None, title: str = None,
             description: str = None, message_id: int = None, message_text: str = None,
             topic_thread_id: int = None,
             group_id: str = None, group_name: str = None,
             og_title: str = None, og_description: str = None, og_image: str = None,
             link_type: str = None, event_starts_at: str = None, event_location: str = None) -> bool:
    """Add a new link. Returns False if duplicate (same URL in same group within 7 days)."""
    client = get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    # Check for duplicates
    query = client.table("digest_links").select("id").eq("url", url).gte("shared_at", since)
    if group_id:
        query = query.eq("group_id", group_id)

    result = query.execute()
    if result.data:
        return False

    row = {
        "url": url,
        "title": title,
        "description": description,
        "group_id": group_id,
        "group_name": group_name,
        "topic": topic,
        "topic_thread_id": topic_thread_id,
        "shared_by": shared_by,
        "message_id": message_id,
        "message_text": message_text,
    }
    if og_title:
        row["og_title"] = og_title
    if og_description:
        row["og_description"] = og_description
    if og_image:
        row["og_image"] = og_image
    if link_type:
        row["type"] = link_type
    if event_starts_at:
        row["event_starts_at"] = event_starts_at
    if event_location:
        row["event_location"] = event_location

    client.table("digest_links").insert(row).execute()

    return True


def get_unpublished_links(since_days: int = 7, group_id: str = None, include_published: bool = False) -> list[dict]:
    """Get unpublished links (or all links from the last N days if include_published=True)."""
    client = get_client()

    query = (
        client.table("digest_links")
        .select("*")
        .neq("type", "event")
        .order("topic")
        .order("shared_at", desc=True)
    )

    if include_published:
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
        query = query.gte("shared_at", since)
    else:
        query = query.eq("published", False)

    if group_id:
        query = query.eq("group_id", group_id)

    result = query.execute()
    return result.data


def get_links_by_group(group_id: str, since_days: int = 7, published: bool = None) -> list[dict]:
    """Get links for a specific group."""
    client = get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()

    query = (
        client.table("digest_links")
        .select("*")
        .eq("group_id", group_id)
        .gte("shared_at", since)
        .order("topic")
        .order("shared_at", desc=True)
    )

    if published is not None:
        query = query.eq("published", published)

    result = query.execute()
    return result.data


def mark_as_published(link_ids: list) -> None:
    """Mark links as published, stamping when the digest went out.

    `published_at` is the only record of a digest's publish date - the digest
    command reads it to build the `{previous digest date} - {today}` header.
    Rows marked before this column existed carry NULL.
    """
    if not link_ids:
        return
    client = get_client()
    client.table("digest_links").update({
        "published": True,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }).in_("id", link_ids).execute()


def get_stats(group_id: str = None) -> dict:
    """Get link statistics, optionally for a specific group."""
    client = get_client()

    base = client.table("digest_links").select("id", count="exact")
    if group_id:
        base = base.eq("group_id", group_id)

    total = base.execute().count or 0

    unpub_q = client.table("digest_links").select("id", count="exact").eq("published", False)
    if group_id:
        unpub_q = unpub_q.eq("group_id", group_id)
    unpublished = unpub_q.execute().count or 0

    return {"total": total, "unpublished": unpublished, "published": total - unpublished}


def get_event_links(group_ids: list[str] = None, since_days: int = 30) -> list[dict]:
    """Get event-type links, ordered by event_starts_at ascending (nulls last)."""
    client = get_client()
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()

    query = (
        client.table("digest_links")
        .select("*")
        .eq("type", "event")
        .gte("shared_at", since)
        .order("event_starts_at", desc=False)
    )

    if group_ids:
        query = query.in_("group_id", group_ids)

    result = query.execute()
    return result.data
