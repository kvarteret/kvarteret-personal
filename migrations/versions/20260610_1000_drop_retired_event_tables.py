"""drop retired legacy and event tables

Revision ID: 20260610_1000
Revises: 20260521_1200
Create Date: 2026-06-10 10:00:00
"""

from alembic import op


revision = "20260610_1000"
down_revision = "20260521_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _execute_each(
        [
            """
            do $$
            begin
                if to_regclass('storage.objects') is not null then
                    drop policy if exists "Anyone can delete event images" on storage.objects;
                    drop policy if exists "Anyone can update event images" on storage.objects;
                    drop policy if exists "Anyone can upload event images" on storage.objects;
                    drop policy if exists "Public event images are readable" on storage.objects;
                end if;
            end $$
            """,
            "drop table if exists public.event_organizer_group_memberships cascade",
            "drop table if exists public.events cascade",
            "drop table if exists public.event_organizer_groups cascade",
            "drop table if exists public.event_types cascade",
            "drop table if exists public.rooms cascade",
            "drop table if exists public.board_game_open_invite cascade",
            "drop table if exists public.volunteer_signup cascade",
            "drop table if exists public.grupper_admin_kobling cascade",
            "drop table if exists public.personal_fil cascade",
            "drop table if exists public.aspnetuserroles cascade",
            "drop table if exists public.aspnetroles cascade",
            "drop table if exists public.aspnetusers cascade",
            "alter table public.nytt_personal drop column if exists arb_status cascade",
            "alter table public.personal drop column if exists arb_status cascade",
            "alter table public.personal drop column if exists brukerkonto cascade",
            "alter table public.personal drop column if exists email cascade",
            "alter table public.personal drop column if exists temp_column cascade",
        ]
    )


def downgrade() -> None:
    _execute_each(
        [
            """
            create table if not exists public.event_types (
            id uuid primary key default gen_random_uuid(),
            slug text not null unique,
            name text not null,
            description text,
            taxonomy_group text not null,
            sort_order integer not null default 0,
            is_active boolean not null default true,
            created_at timestamptz not null default timezone('utc', now()),
            updated_at timestamptz not null default timezone('utc', now())
        )
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
        )
            """,
            """
            create table if not exists public.rooms (
            id uuid primary key default gen_random_uuid(),
            slug text not null unique,
            name text not null,
            sort_order integer not null default 0,
            is_active boolean not null default true,
            created_at timestamptz not null default timezone('utc', now()),
            updated_at timestamptz not null default timezone('utc', now())
        )
            """,
            """
            create table if not exists public.events (
            id uuid primary key default gen_random_uuid(),
            slug text not null,
            translations jsonb not null default '{}'::jsonb,
            status text not null default 'draft',
            price text,
            ticket_url text,
            image_url text,
            event_start timestamptz,
            event_end timestamptz,
            created_at timestamptz not null default timezone('utc', now()),
            updated_at timestamp,
            facebook_url text,
            room_id uuid references public.rooms(id) on delete set null,
            room_text text,
            event_type_id uuid not null references public.event_types(id) on delete restrict,
            is_internal boolean not null default false,
            is_featured boolean not null default false,
            recurring_interval_days integer
        )
            """,
            """
            create table if not exists public.event_organizer_group_memberships (
            id uuid primary key default gen_random_uuid(),
            event_id uuid not null references public.events(id) on delete cascade,
            organizer_group_id uuid not null references public.event_organizer_groups(id) on delete cascade,
            display_order integer not null default 0,
            created_at timestamptz not null default timezone('utc', now()),
            constraint event_organizer_group_memberships_event_id_organizer_group_id_key
                unique (event_id, organizer_group_id)
        )
            """,
            "create index if not exists events_event_start_idx on public.events (event_start)",
            "create index if not exists events_event_type_id_idx on public.events (event_type_id)",
            "create index if not exists events_room_id_idx on public.events (room_id)",
            """
            create index if not exists event_organizer_group_memberships_event_id_idx
            on public.event_organizer_group_memberships (event_id)
            """,
            """
            create table if not exists public.aspnetusers (
            id bigint primary key,
            username varchar(256),
            normalizedusername varchar(256),
            email varchar(256),
            normalizedemail varchar(256),
            emailconfirmed boolean not null default false,
            passwordhash text,
            securitystamp text,
            concurrencystamp text,
            phonenumber text,
            phonenumberconfirmed boolean not null default false,
            twofactorenabled boolean not null default false,
            lockoutend timestamptz,
            lockoutenabled boolean not null default false,
            accessfailedcount integer not null default 0,
            name varchar(256),
            created timestamptz,
            lastlogin timestamptz
        )
            """,
            """
            create table if not exists public.aspnetroles (
            id bigint primary key,
            name varchar(256) not null,
            normalizedname varchar(256),
            concurrencystamp text
        )
            """,
            """
            create table if not exists public.aspnetuserroles (
            userid bigint not null references public.aspnetusers(id) on delete cascade,
            roleid bigint not null references public.aspnetroles(id) on delete cascade,
            primary key (userid, roleid)
        )
            """,
            """
            create table if not exists public.grupper_admin_kobling (
            id_user bigint not null references public.aspnetusers(id) on update cascade on delete cascade,
            id_gruppe bigint not null references public.grupper(id) on update cascade on delete cascade,
            primary key (id_user, id_gruppe)
        )
            """,
            """
            create table if not exists public.personal_fil (
            id bigint primary key,
            id_personal bigint not null references public.personal(id) on update cascade on delete cascade,
            gruppekobling bigint references public.grupper(id) on update cascade on delete cascade,
            filename text not null,
            filetype text,
            opprettet timestamptz not null
        )
            """,
            """
            create table if not exists public.board_game_open_invite (
            id bigint primary key generated by default as identity,
            created_at timestamptz not null default timezone('utc', now())
        )
            """,
            """
            create table if not exists public.volunteer_signup (
            id bigint primary key generated by default as identity,
            created_at timestamptz not null default timezone('utc', now())
        )
            """,
            "alter table public.personal add column if not exists arb_status integer",
            "alter table public.personal add column if not exists brukerkonto varchar(64)",
            "alter table public.personal add column if not exists email varchar",
            "alter table public.personal add column if not exists temp_column varchar(10)",
            "alter table public.nytt_personal add column if not exists arb_status integer",
        ]
    )


def _execute_each(statements: list[str]) -> None:
    for statement in statements:
        op.execute(statement)
