"""reconcile event schema ownership under alembic

Revision ID: 20260325_1300
Revises: 20260319_2145
Create Date: 2026-03-25 13:00:00
"""

from alembic import op


revision = "20260325_1300"
down_revision = "20260319_2145"
branch_labels = None
depends_on = None


EVENT_SCHEMA_STATEMENTS = [
    """
create extension if not exists pgcrypto;
""",
    """
create table if not exists public.event_types (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    name text not null,
    description text,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);
""",
    """
create table if not exists public.event_organizer_groups (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    name text not null,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    default_event_type_id uuid references public.event_types(id) on delete set null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);
""",
    """
create table if not exists public.events (
    id uuid primary key default gen_random_uuid(),
    slug text not null,
    translations json not null,
    status text not null,
    price text,
    ticket_url text,
    image_url text,
    event_start timestamp without time zone,
    event_end timestamp without time zone,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamp without time zone,
    facebook_url text,
    event_type_id uuid not null references public.event_types(id) on delete restrict,
    is_internal boolean not null default false,
    is_featured boolean not null default false,
    recurring_interval_days integer,
    constraint events_recurring_interval_days_check
        check (recurring_interval_days is null or recurring_interval_days > 0)
);
""",
    """
alter table public.events
    add column if not exists facebook_url text,
    add column if not exists event_type_id uuid references public.event_types(id) on delete restrict,
    add column if not exists is_internal boolean not null default false,
    add column if not exists is_featured boolean not null default false,
    add column if not exists recurring_interval_days integer;
""",
    """
alter table public.events
    alter column id set default gen_random_uuid(),
    alter column created_at set default timezone('utc', now()),
    alter column is_internal set default false,
    alter column is_featured set default false;
""",
    """
alter table public.events
    drop constraint if exists events_recurring_interval_days_check;
""",
    """
alter table public.events
    add constraint events_recurring_interval_days_check
        check (recurring_interval_days is null or recurring_interval_days > 0);
""",
    """
do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.events'::regclass
          and contype = 'p'
    ) then
        alter table public.events add constraint events_pkey primary key (id);
    end if;
end
$$;
""",
    """
create table if not exists public.event_organizer_group_memberships (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null references public.events(id) on delete cascade,
    organizer_group_id uuid not null references public.event_organizer_groups(id) on delete cascade,
    display_order integer not null default 0,
    created_at timestamptz not null default timezone('utc', now()),
    unique (event_id, organizer_group_id)
);
""",
    """
create index if not exists events_event_start_idx on public.events (event_start);
""",
    """
create index if not exists events_event_type_id_idx on public.events (event_type_id);
""",
    """
create index if not exists event_organizer_group_memberships_event_id_idx
    on public.event_organizer_group_memberships (event_id);
""",
]


EVENT_SEED_STATEMENTS = [
    """
insert into public.event_types (slug, name, description, sort_order)
values
    ('aapen-oving', 'Åpen Øving', 'Opptak til orger.', 10),
    ('marked', 'Marked', 'Selger bruktting og slikt.', 20),
    ('infomote', 'Infomøte', 'Informasjon om samfunnet og organisasjonen.', 30),
    ('quiz', 'Quiz', null, 40),
    ('konsert', 'Konsert', null, 50),
    ('programslipp', 'Programslipp', null, 60),
    ('festival', 'Festival', null, 70),
    ('apningsmote', 'Åpningsmøte', 'Første arrangement i en serie.', 80),
    ('debatt', 'Debatt', 'To eller flere personer er uenig. Diskusjon av kontroversielle tema.', 90),
    ('panelsamtale', 'Panelsamtale', 'Felles samtale med to eller flere.', 100),
    ('foredrag', 'Foredrag', 'Eksterne talere med innleder.', 110),
    ('generalforsamling', 'Generalforsamling', 'Vedtaksdyktig møte angående samfunnet.', 120),
    ('film-kino', 'Film & Kino', null, 130),
    ('forestilling', 'Forestilling', null, 140),
    ('sosialt', 'Sosialt', 'Quiz, paint & sip, akttegning, perling, pitch a friend, speedating og sosialt.', 150),
    ('revy', 'Revy', null, 160),
    ('frokostmote', 'Frokostmøte', null, 170)
on conflict (slug) do update
set
    name = excluded.name,
    description = excluded.description,
    sort_order = excluded.sort_order,
    is_active = true,
    updated_at = timezone('utc', now());
""",
    """
with debatt_type as (
    select id from public.event_types where slug = 'debatt'
)
insert into public.event_organizer_groups (
    slug,
    name,
    sort_order,
    default_event_type_id
)
values
    ('samfunnet', 'Samfunnet', 10, null),
    ('hf', 'HF', 20, null),
    ('asf', 'ASF', 30, null),
    ('immaturus', 'Immaturus', 40, null),
    ('rf', 'RF', 50, null),
    ('echofestivalen', 'Echofestivalen', 60, null),
    ('vill-vill-vest', 'Vill Vill Vest', 70, null),
    ('bfk', 'BFK', 80, null),
    ('debattkomiteen', 'Debattkomiteen', 90, (select id from debatt_type)),
    ('kultur', 'Kultur', 100, null),
    ('upop', 'UPOP', 110, null),
    ('ekstraordinaert', 'EKSTRAORDINÆRT', 120, null),
    ('samklang', 'Samklang', 130, null),
    ('aktueltkomiteen', 'Aktueltkomiteen', 140, null)
on conflict (slug) do update
set
    name = excluded.name,
    sort_order = excluded.sort_order,
    default_event_type_id = excluded.default_event_type_id,
    is_active = true,
    updated_at = timezone('utc', now());
""",
]


EVENT_RECONCILIATION_STATEMENTS = [
    """
do $$
declare
    missing_event_type_slugs text;
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'events'
          and column_name = 'categories'
    ) then
        select string_agg(coalesce(slug, id::text), ', ' order by event_start asc nulls last)
        into missing_event_type_slugs
        from public.events
        where event_type_id is null;

        if missing_event_type_slugs is not null then
            raise exception 'Existing events are missing event_type_id assignments: %', missing_event_type_slugs;
        end if;

        alter table public.events drop column categories;
    end if;
end
$$;
""",
    """
alter table public.events
    alter column event_type_id set not null;
""",
]


EVENT_GRANTS_AND_STORAGE_STATEMENTS = [
    """
grant select, insert, update, delete on table public.events to anon, authenticated, service_role;
""",
    """
grant select, insert, update on table public.event_types to anon, authenticated, service_role;
""",
    """
grant select, insert, update on table public.event_organizer_groups to anon, authenticated, service_role;
""",
    """
grant select, insert, update, delete on table public.event_organizer_group_memberships to anon, authenticated, service_role;
""",
    """
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'event-images',
    'event-images',
    true,
    10485760,
    array['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/svg+xml', 'image/avif']
)
on conflict (id) do update
set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
""",
    """
do $$
begin
    if not exists (
        select 1
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'Public event images are readable'
    ) then
        create policy "Public event images are readable"
            on storage.objects
            for select
            to public
            using (bucket_id = 'event-images');
    end if;

    if not exists (
        select 1
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'Anyone can upload event images'
    ) then
        create policy "Anyone can upload event images"
            on storage.objects
            for insert
            to anon, authenticated
            with check (bucket_id = 'event-images');
    end if;

    if not exists (
        select 1
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'Anyone can update event images'
    ) then
        create policy "Anyone can update event images"
            on storage.objects
            for update
            to anon, authenticated
            using (bucket_id = 'event-images')
            with check (bucket_id = 'event-images');
    end if;

    if not exists (
        select 1
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname = 'Anyone can delete event images'
    ) then
        create policy "Anyone can delete event images"
            on storage.objects
            for delete
            to anon, authenticated
            using (bucket_id = 'event-images');
    end if;
end
$$;
""",
]


def execute_statements(statements: list[str]) -> None:
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    execute_statements(EVENT_SCHEMA_STATEMENTS)
    execute_statements(EVENT_SEED_STATEMENTS)
    execute_statements(EVENT_RECONCILIATION_STATEMENTS)
    execute_statements(EVENT_GRANTS_AND_STORAGE_STATEMENTS)


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported for reconciled event schema ownership.")
