"""add rooms to events

Revision ID: 20260327_1400
Revises: 20260327_1030
Create Date: 2026-03-27 14:00:00
"""

from alembic import op


revision = "20260327_1400"
down_revision = "20260327_1030"
branch_labels = None
depends_on = None


ROOM_SCHEMA_STATEMENTS = [
    """
create table if not exists public.rooms (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    name text not null,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);
""",
    """
alter table public.events
    add column if not exists room_id uuid references public.rooms(id) on delete set null,
    add column if not exists room_text text;
""",
    """
create index if not exists events_room_id_idx on public.events (room_id);
""",
]


ROOM_SEED_STATEMENTS = [
    """
insert into public.rooms (slug, name, sort_order)
values
    ('teglverket', 'TEGLVERKET', 10),
    ('tivoli', 'TIVOLI', 20),
    ('storelogen', 'STORELOGEN', 30),
    ('speilsalen', 'SPEILSALEN', 40),
    ('maos', 'MAOS', 50),
    ('stillhet', 'STILLHET', 60),
    ('stoy', 'STØY', 70),
    ('grondahls', 'GRØNDAHLS', 80),
    ('halvtimen', 'HALVTIMEN', 90),
    ('stjernesalen', 'STJERNESALEN', 100)
on conflict (slug) do update
set
    name = excluded.name,
    sort_order = excluded.sort_order,
    is_active = true,
    updated_at = timezone('utc', now());
""",
]


ROOM_BACKFILL_STATEMENTS = [
    """
with normalized as (
    select
        events.id,
        lower(
            regexp_replace(
                coalesce(events.translations->'no'->>'description', '')
                || ' '
                || coalesce(events.translations->'en'->>'description', ''),
                '<[^>]+>',
                ' ',
                'g'
            )
        ) as description_text
    from public.events as events
),
canonical_match as (
    select
        normalized.id,
        case
            when normalized.description_text ~ 'sted\\s*:\\s*speilsalen' then 'speilsalen'
            when normalized.description_text like '%teglverket%' then 'teglverket'
            when normalized.description_text like '%tivoli%' then 'tivoli'
            when normalized.description_text like '%storelogen%' then 'storelogen'
            when normalized.description_text like '%speilsalen%' then 'speilsalen'
            when normalized.description_text like '%maos%' then 'maos'
            when normalized.description_text like '%stillhet%' then 'stillhet'
            when normalized.description_text like '%støy%' or normalized.description_text like '%stoy%' then 'stoy'
            when normalized.description_text like '%grøndahls%' or normalized.description_text like '%grondahls%' then 'grondahls'
            when normalized.description_text like '%halvtimen%' then 'halvtimen'
            when normalized.description_text like '%stjernesalen%' then 'stjernesalen'
            else null
        end as room_slug
    from normalized
),
best_effort_text as (
    select
        normalized.id,
        case
            when normalized.description_text ~ 'booket både torgallmenningen og festplassen'
                then 'Torgallmenningen og Festplassen'
            when normalized.description_text ~ 'oppmøte[^.]*arboretet og botanisk hage[^.]*milde'
                then 'Arboretet og Botanisk hage på Milde'
            when normalized.description_text ~ 'hele verden samlet under samme tak'
                or normalized.description_text ~ 'på kvarteret'
                then 'Kvarteret'
            else 'Ukjent'
        end as room_text
    from normalized
),
resolved as (
    select
        events.id,
        rooms.id as room_id,
        case
            when canonical_match.room_slug is not null then null
            else best_effort_text.room_text
        end as room_text
    from public.events as events
    left join canonical_match on canonical_match.id = events.id
    left join best_effort_text on best_effort_text.id = events.id
    left join public.rooms as rooms on rooms.slug = canonical_match.room_slug
)
update public.events as events
set room_id = resolved.room_id,
    room_text = resolved.room_text,
    updated_at = timezone('utc', now())
from resolved
where events.id = resolved.id
  and (events.room_id is distinct from resolved.room_id or events.room_text is distinct from resolved.room_text);
""",
]


ROOM_CONSTRAINT_STATEMENTS = [
    """
alter table public.events
    drop constraint if exists events_room_source_check;
""",
    """
alter table public.events
    add constraint events_room_source_check
    check (
        (
            room_id is not null
            and nullif(btrim(coalesce(room_text, '')), '') is null
        )
        or
        (
            room_id is null
            and nullif(btrim(coalesce(room_text, '')), '') is not null
        )
    ) not valid;
""",
    """
alter table public.events validate constraint events_room_source_check;
""",
]


ROOM_GRANT_STATEMENTS = [
    """
grant select, insert, update on table public.rooms to anon, authenticated, service_role;
""",
]


def upgrade() -> None:
    for statement in ROOM_SCHEMA_STATEMENTS:
        op.execute(statement)

    for statement in ROOM_SEED_STATEMENTS:
        op.execute(statement)

    for statement in ROOM_BACKFILL_STATEMENTS:
        op.execute(statement)

    for statement in ROOM_CONSTRAINT_STATEMENTS:
        op.execute(statement)

    for statement in ROOM_GRANT_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("alter table public.events drop constraint if exists events_room_source_check;")
    op.execute("drop index if exists public.events_room_id_idx;")
    op.execute("alter table public.events drop column if exists room_text, drop column if exists room_id;")
    op.execute("drop table if exists public.rooms;")
