--
-- PostgreSQL database dump
--

\restrict yrySWULcns9RlxEmPL59jbLznsDs7zKf67bqBMTbhO6HnYBlSa5CYshThahcda1

-- Dumped from database version 17.6
-- Dumped by pg_dump version 18.0

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: current_legacy_user_id(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.current_legacy_user_id() RETURNS bigint
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
      SELECT ua.legacy_user_id
      FROM public.user_accounts AS ua
      WHERE ua.auth_user_id = auth.uid()
      LIMIT 1
    $$;


--
-- Name: grant_permissions_on_new_table(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.grant_permissions_on_new_table() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA "public" TO authenticated;
  GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA "public" TO anon;
END;
$$;


--
-- Name: rls_auto_enable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.rls_auto_enable() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: aspnetroles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aspnetroles (
    id bigint NOT NULL,
    concurrencystamp text,
    name character varying(256),
    normalizedname character varying(256)
);


--
-- Name: aspnetroles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.aspnetroles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: aspnetroles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.aspnetroles_id_seq OWNED BY public.aspnetroles.id;


--
-- Name: aspnetuserroles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aspnetuserroles (
    userid bigint NOT NULL,
    roleid bigint NOT NULL
);


--
-- Name: aspnetusers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aspnetusers (
    id bigint NOT NULL,
    accessfailedcount bigint NOT NULL,
    concurrencystamp text,
    created timestamp with time zone NOT NULL,
    email character varying(256),
    emailconfirmed boolean NOT NULL,
    lastlogin timestamp with time zone NOT NULL,
    lockoutenabled boolean NOT NULL,
    lockoutend timestamp with time zone,
    name character varying(256),
    normalizedemail character varying(256),
    normalizedusername character varying(256),
    passwordhash text,
    phonenumber text,
    phonenumberconfirmed boolean NOT NULL,
    securitystamp text,
    twofactorenabled boolean NOT NULL,
    username character varying(256)
);


--
-- Name: aspnetusers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.aspnetusers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: aspnetusers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.aspnetusers_id_seq OWNED BY public.aspnetusers.id;


--
-- Name: auth_migration_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_migration_events (
    id bigint NOT NULL,
    legacy_user_id bigint NOT NULL,
    auth_user_id uuid,
    email character varying(320),
    outcome character varying(64) NOT NULL,
    details text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: auth_migration_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auth_migration_events ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.auth_migration_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: board_game_open_invite; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.board_game_open_invite (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    game text DEFAULT 'chess'::text NOT NULL,
    room text NOT NULL
);


--
-- Name: TABLE board_game_open_invite; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.board_game_open_invite IS 'open invitation for board game';


--
-- Name: board_game_open_invite_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.board_game_open_invite ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.board_game_open_invite_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: event_organizer_group_memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_organizer_group_memberships (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_id uuid NOT NULL,
    organizer_group_id uuid NOT NULL,
    display_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: event_organizer_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_organizer_groups (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    default_event_type_id uuid,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: event_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_types (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    description text,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    taxonomy_group text NOT NULL
);


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    translations json NOT NULL,
    status text NOT NULL,
    price text,
    ticket_url text,
    image_url text,
    event_start timestamp with time zone,
    event_end timestamp with time zone,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp without time zone,
    facebook_url text,
    event_type_id uuid NOT NULL,
    is_internal boolean DEFAULT false NOT NULL,
    is_featured boolean DEFAULT false NOT NULL,
    recurring_interval_days integer,
    room_id uuid,
    room_text text,
    CONSTRAINT events_recurring_interval_days_check CHECK (((recurring_interval_days IS NULL) OR (recurring_interval_days > 0))),
    CONSTRAINT events_room_source_check CHECK ((((room_id IS NOT NULL) AND (NULLIF(btrim(COALESCE(room_text, ''::text)), ''::text) IS NULL)) OR ((room_id IS NULL) AND (NULLIF(btrim(COALESCE(room_text, ''::text)), ''::text) IS NOT NULL))))
);


--
-- Name: group_admin_memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.group_admin_memberships (
    auth_user_id uuid NOT NULL,
    gruppe_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: grupper; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grupper (
    id integer NOT NULL,
    navn character varying(255) NOT NULL,
    beskrivelse text,
    aktiv boolean DEFAULT true NOT NULL,
    aktiv_til_og_med integer NOT NULL,
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    id_overgruppe integer,
    rabatt_trinn integer
);


--
-- Name: grupper_admin_kobling; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grupper_admin_kobling (
    id_user bigint NOT NULL,
    id_gruppe bigint NOT NULL
);


--
-- Name: grupper_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grupper_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grupper_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grupper_id_seq OWNED BY public.grupper.id;


--
-- Name: grupper_kurs_kobling; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grupper_kurs_kobling (
    id_kurs bigint NOT NULL,
    id_gruppe bigint NOT NULL
);


--
-- Name: historie; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.historie (
    id bigint NOT NULL,
    id_personal bigint NOT NULL,
    id_gruppe bigint NOT NULL,
    id_verv bigint DEFAULT '1'::bigint,
    semester integer NOT NULL,
    signert_kontrakt boolean DEFAULT false NOT NULL,
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: historie_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.historie_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: historie_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.historie_id_seq OWNED BY public.historie.id;


--
-- Name: historie_kurs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.historie_kurs (
    id bigint NOT NULL,
    id_personal bigint NOT NULL,
    id_kurs bigint NOT NULL,
    gjennomfort_dato integer NOT NULL,
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: historie_kurs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.historie_kurs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: historie_kurs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.historie_kurs_id_seq OWNED BY public.historie_kurs.id;


--
-- Name: integration_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.integration_tokens (
    provider character varying(64) NOT NULL,
    refresh_token text NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    updated_by_user_account_id bigint
);


--
-- Name: kurs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kurs (
    id bigint NOT NULL,
    navn character varying(128) NOT NULL,
    beskrivelse character varying(1024),
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: kurs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kurs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kurs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.kurs_id_seq OWNED BY public.kurs.id;


--
-- Name: mobile_card_april_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mobile_card_april_state (
    enabled boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    updated_by_user_account_id bigint
);


--
-- Name: nytt_personal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nytt_personal (
    id bigint NOT NULL,
    registrering_id bigint NOT NULL,
    fornavn text,
    etternavn text NOT NULL,
    epost text NOT NULL,
    arb_status integer,
    kjonn text DEFAULT 'A'::text NOT NULL,
    fodselsdato date,
    gateadresse text,
    postnummerid text,
    telefon text,
    internkortaccesstoken text,
    opprettet timestamp with time zone DEFAULT now() NOT NULL,
    photo_sha1 text,
    photo_filetype text,
    studiested text,
    bakgrunn text,
    CONSTRAINT ck_nytt_personal_postnummerid_format CHECK (((postnummerid IS NULL) OR (postnummerid ~ '^\d{4}$'::text)))
);


--
-- Name: nytt_personal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.nytt_personal ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.nytt_personal_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: paarorende; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paarorende (
    id bigint NOT NULL,
    id_personal bigint NOT NULL,
    navn character varying(512) NOT NULL,
    telefon character varying(50) NOT NULL,
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: paarorende_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.paarorende_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: paarorende_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.paarorende_id_seq OWNED BY public.paarorende.id;


--
-- Name: personal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.personal (
    id integer NOT NULL,
    fornavn character varying(255),
    etternavn character varying(255) NOT NULL,
    brukerkonto character varying(64),
    epost character varying(1024),
    arb_status integer,
    kjonn character varying(1) NOT NULL,
    fodselsdato date,
    gateadresse character varying(128),
    postnummerid text,
    telefon character varying(50),
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    internkortaccesstoken character varying(60),
    temp_column character varying(10),
    internkort_access_token_created_at timestamp with time zone,
    email character varying
);


--
-- Name: personal_bilde; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.personal_bilde (
    id_personal bigint NOT NULL,
    sha1 character varying(40) NOT NULL,
    filetype character varying(5),
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: personal_fil; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.personal_fil (
    id bigint NOT NULL,
    id_personal bigint NOT NULL,
    gruppekobling bigint,
    filename character varying(255) DEFAULT '"INGEN NAVN"'::character varying NOT NULL,
    filetype character varying(10),
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: personal_fil_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.personal_fil_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: personal_fil_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.personal_fil_id_seq OWNED BY public.personal_fil.id;


--
-- Name: personal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.personal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: personal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.personal_id_seq OWNED BY public.personal.id;


--
-- Name: personal_kort; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.personal_kort (
    id bigint NOT NULL,
    id_personal bigint NOT NULL,
    kortnummer character varying(15) NOT NULL,
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: personal_kort_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.personal_kort_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: personal_kort_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.personal_kort_id_seq OWNED BY public.personal_kort.id;


--
-- Name: registrering; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.registrering (
    id bigint NOT NULL,
    token text NOT NULL,
    epost text NOT NULL,
    opprettet timestamp with time zone DEFAULT now() NOT NULL,
    initial_group_id bigint,
    initial_role_id bigint,
    source text DEFAULT 'invite'::text NOT NULL,
    status text DEFAULT 'invited'::text NOT NULL,
    first_choice_group_id bigint,
    second_choice_group_id bigint,
    trial_shift_attended boolean DEFAULT false NOT NULL,
    trial_shift_marked_at timestamp with time zone,
    full_profile_submitted_at timestamp with time zone,
    promoted_volunteer_id bigint,
    promoted_at timestamp with time zone
);


--
-- Name: registrering_gruppe; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.registrering_gruppe (
    id bigint NOT NULL,
    opprettet timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: registrering_gruppe_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.registrering_gruppe_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: registrering_gruppe_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.registrering_gruppe_id_seq OWNED BY public.registrering_gruppe.id;


--
-- Name: registrering_gruppe_medlem; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.registrering_gruppe_medlem (
    id bigint NOT NULL,
    gruppe_id bigint NOT NULL,
    registrering_id bigint,
    registrering_epost text NOT NULL,
    rolle text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    opprettet timestamp with time zone DEFAULT now() NOT NULL,
    droppet timestamp with time zone,
    droppet_av_user_id bigint,
    CONSTRAINT ck_registrering_gruppe_medlem_rolle CHECK ((rolle = ANY (ARRAY['inviter'::text, 'invitee'::text]))),
    CONSTRAINT ck_registrering_gruppe_medlem_status CHECK ((status = ANY (ARRAY['active'::text, 'dropped'::text])))
);


--
-- Name: registrering_gruppe_medlem_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.registrering_gruppe_medlem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: registrering_gruppe_medlem_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.registrering_gruppe_medlem_id_seq OWNED BY public.registrering_gruppe_medlem.id;


--
-- Name: registrering_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.registrering ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.registrering_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: rooms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rooms (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: user_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_accounts (
    id bigint NOT NULL,
    auth_user_id uuid NOT NULL,
    legacy_user_id bigint,
    username character varying(256) NOT NULL,
    email character varying(320) NOT NULL,
    display_name character varying(256),
    role character varying(64) NOT NULL,
    last_login timestamp with time zone,
    migrated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: user_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.user_accounts ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.user_accounts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: verv; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.verv (
    id bigint NOT NULL,
    verv character varying(255),
    id_gruppe bigint DEFAULT '1'::bigint NOT NULL,
    pingvinpoeng bigint DEFAULT '1'::bigint NOT NULL,
    opprettet timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: verv_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.verv_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: verv_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.verv_id_seq OWNED BY public.verv.id;


--
-- Name: volunteer_signup; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.volunteer_signup (
    id bigint NOT NULL,
    email text NOT NULL,
    name text NOT NULL,
    "group" text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    institution text NOT NULL,
    message text NOT NULL
);


--
-- Name: TABLE volunteer_signup; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.volunteer_signup IS 'blifrivillig.no form entries';


--
-- Name: COLUMN volunteer_signup.institution; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.volunteer_signup.institution IS 'The place where they study';


--
-- Name: COLUMN volunteer_signup.message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.volunteer_signup.message IS 'optional message';


--
-- Name: volunteer_request_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.volunteer_signup ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.volunteer_request_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: web_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.web_sessions (
    session_id character varying(128) NOT NULL,
    auth_user_id uuid NOT NULL,
    user_account_id bigint,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    ip_address character varying(64),
    user_agent text,
    impersonator_auth_user_id uuid,
    impersonator_user_account_id bigint
);


--
-- Name: aspnetroles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspnetroles ALTER COLUMN id SET DEFAULT nextval('public.aspnetroles_id_seq'::regclass);


--
-- Name: aspnetusers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspnetusers ALTER COLUMN id SET DEFAULT nextval('public.aspnetusers_id_seq'::regclass);


--
-- Name: grupper id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper ALTER COLUMN id SET DEFAULT nextval('public.grupper_id_seq'::regclass);


--
-- Name: historie id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie ALTER COLUMN id SET DEFAULT nextval('public.historie_id_seq'::regclass);


--
-- Name: historie_kurs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie_kurs ALTER COLUMN id SET DEFAULT nextval('public.historie_kurs_id_seq'::regclass);


--
-- Name: kurs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kurs ALTER COLUMN id SET DEFAULT nextval('public.kurs_id_seq'::regclass);


--
-- Name: paarorende id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paarorende ALTER COLUMN id SET DEFAULT nextval('public.paarorende_id_seq'::regclass);


--
-- Name: personal id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal ALTER COLUMN id SET DEFAULT nextval('public.personal_id_seq'::regclass);


--
-- Name: personal_fil id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_fil ALTER COLUMN id SET DEFAULT nextval('public.personal_fil_id_seq'::regclass);


--
-- Name: personal_kort id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_kort ALTER COLUMN id SET DEFAULT nextval('public.personal_kort_id_seq'::regclass);


--
-- Name: registrering_gruppe id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering_gruppe ALTER COLUMN id SET DEFAULT nextval('public.registrering_gruppe_id_seq'::regclass);


--
-- Name: registrering_gruppe_medlem id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering_gruppe_medlem ALTER COLUMN id SET DEFAULT nextval('public.registrering_gruppe_medlem_id_seq'::regclass);


--
-- Name: verv id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verv ALTER COLUMN id SET DEFAULT nextval('public.verv_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: auth_migration_events auth_migration_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_migration_events
    ADD CONSTRAINT auth_migration_events_pkey PRIMARY KEY (id);


--
-- Name: board_game_open_invite board_game_open_invite_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_game_open_invite
    ADD CONSTRAINT board_game_open_invite_pkey PRIMARY KEY (id);


--
-- Name: event_organizer_group_memberships event_organizer_group_membershi_event_id_organizer_group_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_organizer_group_memberships
    ADD CONSTRAINT event_organizer_group_membershi_event_id_organizer_group_id_key UNIQUE (event_id, organizer_group_id);


--
-- Name: event_organizer_group_memberships event_organizer_group_memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_organizer_group_memberships
    ADD CONSTRAINT event_organizer_group_memberships_pkey PRIMARY KEY (id);


--
-- Name: event_organizer_groups event_organizer_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_organizer_groups
    ADD CONSTRAINT event_organizer_groups_pkey PRIMARY KEY (id);


--
-- Name: event_organizer_groups event_organizer_groups_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_organizer_groups
    ADD CONSTRAINT event_organizer_groups_slug_key UNIQUE (slug);


--
-- Name: event_types event_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_types
    ADD CONSTRAINT event_types_pkey PRIMARY KEY (id);


--
-- Name: event_types event_types_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_types
    ADD CONSTRAINT event_types_slug_key UNIQUE (slug);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: group_admin_memberships group_admin_memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_admin_memberships
    ADD CONSTRAINT group_admin_memberships_pkey PRIMARY KEY (auth_user_id, gruppe_id);


--
-- Name: aspnetroles idx_26573_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspnetroles
    ADD CONSTRAINT idx_26573_primary PRIMARY KEY (id);


--
-- Name: aspnetuserroles idx_26591_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspnetuserroles
    ADD CONSTRAINT idx_26591_primary PRIMARY KEY (userid, roleid);


--
-- Name: aspnetusers idx_26595_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspnetusers
    ADD CONSTRAINT idx_26595_primary PRIMARY KEY (id);


--
-- Name: grupper idx_26607_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper
    ADD CONSTRAINT idx_26607_primary PRIMARY KEY (id);


--
-- Name: grupper_admin_kobling idx_26615_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper_admin_kobling
    ADD CONSTRAINT idx_26615_primary PRIMARY KEY (id_user, id_gruppe);


--
-- Name: grupper_kurs_kobling idx_26618_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper_kurs_kobling
    ADD CONSTRAINT idx_26618_primary PRIMARY KEY (id_kurs, id_gruppe);


--
-- Name: historie idx_26622_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie
    ADD CONSTRAINT idx_26622_primary PRIMARY KEY (id);


--
-- Name: historie_kurs idx_26630_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie_kurs
    ADD CONSTRAINT idx_26630_primary PRIMARY KEY (id);


--
-- Name: kurs idx_26636_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kurs
    ADD CONSTRAINT idx_26636_primary PRIMARY KEY (id);


--
-- Name: paarorende idx_26644_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paarorende
    ADD CONSTRAINT idx_26644_primary PRIMARY KEY (id);


--
-- Name: personal idx_26652_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal
    ADD CONSTRAINT idx_26652_primary PRIMARY KEY (id);


--
-- Name: personal_bilde idx_26659_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_bilde
    ADD CONSTRAINT idx_26659_primary PRIMARY KEY (id_personal);


--
-- Name: personal_fil idx_26664_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_fil
    ADD CONSTRAINT idx_26664_primary PRIMARY KEY (id);


--
-- Name: personal_kort idx_26671_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_kort
    ADD CONSTRAINT idx_26671_primary PRIMARY KEY (id);


--
-- Name: verv idx_26677_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verv
    ADD CONSTRAINT idx_26677_primary PRIMARY KEY (id);


--
-- Name: integration_tokens integration_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integration_tokens
    ADD CONSTRAINT integration_tokens_pkey PRIMARY KEY (provider);


--
-- Name: nytt_personal nytt_personal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nytt_personal
    ADD CONSTRAINT nytt_personal_pkey PRIMARY KEY (id);


--
-- Name: nytt_personal nytt_personal_registrering_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nytt_personal
    ADD CONSTRAINT nytt_personal_registrering_id_key UNIQUE (registrering_id);


--
-- Name: personal personal_email_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal
    ADD CONSTRAINT personal_email_unique UNIQUE (email);


--
-- Name: registrering_gruppe_medlem registrering_gruppe_medlem_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering_gruppe_medlem
    ADD CONSTRAINT registrering_gruppe_medlem_pkey PRIMARY KEY (id);


--
-- Name: registrering_gruppe registrering_gruppe_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering_gruppe
    ADD CONSTRAINT registrering_gruppe_pkey PRIMARY KEY (id);


--
-- Name: registrering registrering_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering
    ADD CONSTRAINT registrering_pkey PRIMARY KEY (id);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (id);


--
-- Name: rooms rooms_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_slug_key UNIQUE (slug);


--
-- Name: registrering_gruppe_medlem uq_registrering_gruppe_medlem_registrering; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering_gruppe_medlem
    ADD CONSTRAINT uq_registrering_gruppe_medlem_registrering UNIQUE (gruppe_id, registrering_id);


--
-- Name: registrering uq_registrering_token; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering
    ADD CONSTRAINT uq_registrering_token UNIQUE (token);


--
-- Name: user_accounts user_accounts_auth_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_accounts
    ADD CONSTRAINT user_accounts_auth_user_id_key UNIQUE (auth_user_id);


--
-- Name: user_accounts user_accounts_legacy_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_accounts
    ADD CONSTRAINT user_accounts_legacy_user_id_key UNIQUE (legacy_user_id);


--
-- Name: user_accounts user_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_accounts
    ADD CONSTRAINT user_accounts_pkey PRIMARY KEY (id);


--
-- Name: volunteer_signup volunteer_request_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.volunteer_signup
    ADD CONSTRAINT volunteer_request_pkey PRIMARY KEY (id);


--
-- Name: web_sessions web_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.web_sessions
    ADD CONSTRAINT web_sessions_pkey PRIMARY KEY (session_id);


--
-- Name: event_organizer_group_memberships_event_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX event_organizer_group_memberships_event_id_idx ON public.event_organizer_group_memberships USING btree (event_id);


--
-- Name: events_event_start_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_event_start_idx ON public.events USING btree (event_start);


--
-- Name: events_event_type_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_event_type_id_idx ON public.events USING btree (event_type_id);


--
-- Name: events_room_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_room_id_idx ON public.events USING btree (room_id);


--
-- Name: idx_26591_fk_aspnetuserroles_aspnetroles_roleid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26591_fk_aspnetuserroles_aspnetroles_roleid ON public.aspnetuserroles USING btree (roleid);


--
-- Name: idx_26607_id_overgruppe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26607_id_overgruppe ON public.grupper USING btree (id_overgruppe);


--
-- Name: idx_26607_navn; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_26607_navn ON public.grupper USING btree (navn);


--
-- Name: idx_26615_grupper_kobling; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26615_grupper_kobling ON public.grupper_admin_kobling USING btree (id_gruppe);


--
-- Name: idx_26618_id_gruppe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26618_id_gruppe ON public.grupper_kurs_kobling USING btree (id_gruppe);


--
-- Name: idx_26622_id_gruppe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26622_id_gruppe ON public.historie USING btree (id_gruppe);


--
-- Name: idx_26622_id_personal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26622_id_personal ON public.historie USING btree (id_personal);


--
-- Name: idx_26622_id_verv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26622_id_verv ON public.historie USING btree (id_verv);


--
-- Name: idx_26630_id_kurs; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26630_id_kurs ON public.historie_kurs USING btree (id_kurs);


--
-- Name: idx_26630_id_personal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26630_id_personal ON public.historie_kurs USING btree (id_personal);


--
-- Name: idx_26636_navn; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_26636_navn ON public.kurs USING btree (navn);


--
-- Name: idx_26644_id_personal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26644_id_personal ON public.paarorende USING btree (id_personal);


--
-- Name: idx_26652_etternavn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26652_etternavn ON public.personal USING btree (etternavn);


--
-- Name: idx_26652_fornavn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26652_fornavn ON public.personal USING btree (fornavn);


--
-- Name: idx_26664_id_gruppe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26664_id_gruppe ON public.personal_fil USING btree (gruppekobling);


--
-- Name: idx_26664_id_personal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26664_id_personal ON public.personal_fil USING btree (id_personal);


--
-- Name: idx_26671_id_personal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26671_id_personal ON public.personal_kort USING btree (id_personal);


--
-- Name: idx_26671_id_personal_2; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_26671_id_personal_2 ON public.personal_kort USING btree (id_personal, kortnummer);


--
-- Name: idx_26677_id_gruppe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_26677_id_gruppe ON public.verv USING btree (id_gruppe);


--
-- Name: idx_personal_full_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_personal_full_name_trgm ON public.personal USING gin (lower(btrim((((COALESCE(fornavn, ''::character varying))::text || ' '::text) || (COALESCE(etternavn, ''::character varying))::text))) public.gin_trgm_ops);


--
-- Name: ix_registrering_first_choice_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_registrering_first_choice_group_id ON public.registrering USING btree (first_choice_group_id);


--
-- Name: ix_registrering_gruppe_medlem_gruppe_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_registrering_gruppe_medlem_gruppe_id ON public.registrering_gruppe_medlem USING btree (gruppe_id);


--
-- Name: ix_registrering_gruppe_medlem_registrering_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_registrering_gruppe_medlem_registrering_id ON public.registrering_gruppe_medlem USING btree (registrering_id);


--
-- Name: ix_registrering_promoted_volunteer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_registrering_promoted_volunteer_id ON public.registrering USING btree (promoted_volunteer_id);


--
-- Name: ix_registrering_second_choice_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_registrering_second_choice_group_id ON public.registrering USING btree (second_choice_group_id);


--
-- Name: ix_user_accounts_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_accounts_email ON public.user_accounts USING btree (email);


--
-- Name: ix_user_accounts_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_accounts_username ON public.user_accounts USING btree (username);


--
-- Name: event_organizer_group_memberships event_organizer_group_memberships_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_organizer_group_memberships
    ADD CONSTRAINT event_organizer_group_memberships_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE CASCADE;


--
-- Name: event_organizer_group_memberships event_organizer_group_memberships_organizer_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_organizer_group_memberships
    ADD CONSTRAINT event_organizer_group_memberships_organizer_group_id_fkey FOREIGN KEY (organizer_group_id) REFERENCES public.event_organizer_groups(id) ON DELETE CASCADE;


--
-- Name: event_organizer_groups event_organizer_groups_default_event_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_organizer_groups
    ADD CONSTRAINT event_organizer_groups_default_event_type_id_fkey FOREIGN KEY (default_event_type_id) REFERENCES public.event_types(id) ON DELETE SET NULL;


--
-- Name: events events_event_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_event_type_id_fkey FOREIGN KEY (event_type_id) REFERENCES public.event_types(id) ON DELETE RESTRICT;


--
-- Name: events events_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id) ON DELETE SET NULL;


--
-- Name: personal_fil fil-gruppe-fkid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_fil
    ADD CONSTRAINT "fil-gruppe-fkid" FOREIGN KEY (gruppekobling) REFERENCES public.grupper(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: personal_fil fil-personal-fkid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_fil
    ADD CONSTRAINT "fil-personal-fkid" FOREIGN KEY (id_personal) REFERENCES public.personal(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: aspnetuserroles fk_aspnetuserroles_aspnetroles_roleid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspnetuserroles
    ADD CONSTRAINT fk_aspnetuserroles_aspnetroles_roleid FOREIGN KEY (roleid) REFERENCES public.aspnetroles(id) ON DELETE CASCADE;


--
-- Name: aspnetuserroles fk_aspnetuserroles_aspnetusers_userid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspnetuserroles
    ADD CONSTRAINT fk_aspnetuserroles_aspnetusers_userid FOREIGN KEY (userid) REFERENCES public.aspnetusers(id) ON DELETE CASCADE;


--
-- Name: mobile_card_april_state fk_mobile_card_april_state_updated_by_user_account_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobile_card_april_state
    ADD CONSTRAINT fk_mobile_card_april_state_updated_by_user_account_id FOREIGN KEY (updated_by_user_account_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;


--
-- Name: registrering fk_registrering_promoted_volunteer_id_personal; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering
    ADD CONSTRAINT fk_registrering_promoted_volunteer_id_personal FOREIGN KEY (promoted_volunteer_id) REFERENCES public.personal(id) ON DELETE SET NULL;


--
-- Name: web_sessions fk_web_sessions_impersonator_user_account_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.web_sessions
    ADD CONSTRAINT fk_web_sessions_impersonator_user_account_id FOREIGN KEY (impersonator_user_account_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;


--
-- Name: group_admin_memberships group_admin_memberships_gruppe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.group_admin_memberships
    ADD CONSTRAINT group_admin_memberships_gruppe_id_fkey FOREIGN KEY (gruppe_id) REFERENCES public.grupper(id) ON DELETE CASCADE;


--
-- Name: grupper grupper_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper
    ADD CONSTRAINT grupper_ibfk_1 FOREIGN KEY (id_overgruppe) REFERENCES public.grupper(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: grupper_admin_kobling grupper_kobling; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper_admin_kobling
    ADD CONSTRAINT grupper_kobling FOREIGN KEY (id_gruppe) REFERENCES public.grupper(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: grupper_kurs_kobling grupper_kurs_kobling_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper_kurs_kobling
    ADD CONSTRAINT grupper_kurs_kobling_ibfk_1 FOREIGN KEY (id_kurs) REFERENCES public.kurs(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: grupper_kurs_kobling grupper_kurs_kobling_ibfk_2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper_kurs_kobling
    ADD CONSTRAINT grupper_kurs_kobling_ibfk_2 FOREIGN KEY (id_gruppe) REFERENCES public.grupper(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: historie historie_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie
    ADD CONSTRAINT historie_ibfk_1 FOREIGN KEY (id_personal) REFERENCES public.personal(id) ON UPDATE CASCADE;


--
-- Name: historie historie_ibfk_2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie
    ADD CONSTRAINT historie_ibfk_2 FOREIGN KEY (id_gruppe) REFERENCES public.grupper(id) ON UPDATE CASCADE;


--
-- Name: historie historie_ibfk_3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie
    ADD CONSTRAINT historie_ibfk_3 FOREIGN KEY (id_verv) REFERENCES public.verv(id) ON UPDATE CASCADE;


--
-- Name: historie_kurs historie_kurs_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie_kurs
    ADD CONSTRAINT historie_kurs_ibfk_1 FOREIGN KEY (id_personal) REFERENCES public.personal(id) ON UPDATE CASCADE;


--
-- Name: historie_kurs historie_kurs_ibfk_2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historie_kurs
    ADD CONSTRAINT historie_kurs_ibfk_2 FOREIGN KEY (id_kurs) REFERENCES public.kurs(id) ON UPDATE CASCADE;


--
-- Name: integration_tokens integration_tokens_updated_by_user_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integration_tokens
    ADD CONSTRAINT integration_tokens_updated_by_user_account_id_fkey FOREIGN KEY (updated_by_user_account_id) REFERENCES public.user_accounts(id);


--
-- Name: nytt_personal nytt_personal_registrering_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nytt_personal
    ADD CONSTRAINT nytt_personal_registrering_id_fkey FOREIGN KEY (registrering_id) REFERENCES public.registrering(id) ON DELETE CASCADE;


--
-- Name: paarorende paarorende_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paarorende
    ADD CONSTRAINT paarorende_ibfk_1 FOREIGN KEY (id_personal) REFERENCES public.personal(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: personal_bilde personal_bilde_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_bilde
    ADD CONSTRAINT personal_bilde_ibfk_1 FOREIGN KEY (id_personal) REFERENCES public.personal(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: personal_kort personal_kort_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_kort
    ADD CONSTRAINT personal_kort_ibfk_1 FOREIGN KEY (id_personal) REFERENCES public.personal(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: registrering_gruppe_medlem registrering_gruppe_medlem_gruppe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering_gruppe_medlem
    ADD CONSTRAINT registrering_gruppe_medlem_gruppe_id_fkey FOREIGN KEY (gruppe_id) REFERENCES public.registrering_gruppe(id);


--
-- Name: registrering_gruppe_medlem registrering_gruppe_medlem_registrering_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.registrering_gruppe_medlem
    ADD CONSTRAINT registrering_gruppe_medlem_registrering_id_fkey FOREIGN KEY (registrering_id) REFERENCES public.registrering(id) ON DELETE SET NULL;


--
-- Name: grupper_admin_kobling user_kobling; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grupper_admin_kobling
    ADD CONSTRAINT user_kobling FOREIGN KEY (id_user) REFERENCES public.aspnetusers(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: verv verv_ibfk_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verv
    ADD CONSTRAINT verv_ibfk_1 FOREIGN KEY (id_gruppe) REFERENCES public.grupper(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: web_sessions web_sessions_user_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.web_sessions
    ADD CONSTRAINT web_sessions_user_account_id_fkey FOREIGN KEY (user_account_id) REFERENCES public.user_accounts(id) ON DELETE SET NULL;


--
-- Name: volunteer_signup Enable insert for all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Enable insert for all" ON public.volunteer_signup FOR INSERT WITH CHECK (true);


--
-- Name: aspnetroles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.aspnetroles ENABLE ROW LEVEL SECURITY;

--
-- Name: aspnetuserroles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.aspnetuserroles ENABLE ROW LEVEL SECURITY;

--
-- Name: aspnetusers; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.aspnetusers ENABLE ROW LEVEL SECURITY;

--
-- Name: auth_migration_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.auth_migration_events ENABLE ROW LEVEL SECURITY;

--
-- Name: board_game_open_invite; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.board_game_open_invite ENABLE ROW LEVEL SECURITY;

--
-- Name: group_admin_memberships; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.group_admin_memberships ENABLE ROW LEVEL SECURITY;

--
-- Name: grupper; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.grupper ENABLE ROW LEVEL SECURITY;

--
-- Name: grupper_admin_kobling; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.grupper_admin_kobling ENABLE ROW LEVEL SECURITY;

--
-- Name: grupper_kurs_kobling; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.grupper_kurs_kobling ENABLE ROW LEVEL SECURITY;

--
-- Name: grupper grupper_select_self_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY grupper_select_self_authenticated ON public.grupper FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.historie h
  WHERE ((h.id_gruppe = grupper.id) AND (h.id_personal = public.current_legacy_user_id())))));


--
-- Name: historie; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.historie ENABLE ROW LEVEL SECURITY;

--
-- Name: historie_kurs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.historie_kurs ENABLE ROW LEVEL SECURITY;

--
-- Name: historie historie_select_self_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY historie_select_self_authenticated ON public.historie FOR SELECT TO authenticated USING ((id_personal = public.current_legacy_user_id()));


--
-- Name: integration_tokens; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.integration_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: kurs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.kurs ENABLE ROW LEVEL SECURITY;

--
-- Name: nytt_personal; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.nytt_personal ENABLE ROW LEVEL SECURITY;

--
-- Name: paarorende; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.paarorende ENABLE ROW LEVEL SECURITY;

--
-- Name: personal; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.personal ENABLE ROW LEVEL SECURITY;

--
-- Name: personal_bilde; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.personal_bilde ENABLE ROW LEVEL SECURITY;

--
-- Name: personal_bilde personal_bilde_select_self_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY personal_bilde_select_self_authenticated ON public.personal_bilde FOR SELECT TO authenticated USING ((id_personal = public.current_legacy_user_id()));


--
-- Name: personal_fil; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.personal_fil ENABLE ROW LEVEL SECURITY;

--
-- Name: personal_kort; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.personal_kort ENABLE ROW LEVEL SECURITY;

--
-- Name: personal personal_select_self_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY personal_select_self_authenticated ON public.personal FOR SELECT TO authenticated USING ((id = public.current_legacy_user_id()));


--
-- Name: registrering; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.registrering ENABLE ROW LEVEL SECURITY;

--
-- Name: user_accounts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_accounts ENABLE ROW LEVEL SECURITY;

--
-- Name: user_accounts user_accounts_select_self_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY user_accounts_select_self_authenticated ON public.user_accounts FOR SELECT TO authenticated USING ((auth.uid() = auth_user_id));


--
-- Name: verv; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.verv ENABLE ROW LEVEL SECURITY;

--
-- Name: verv verv_select_self_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY verv_select_self_authenticated ON public.verv FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.historie h
  WHERE ((h.id_verv = verv.id) AND (h.id_personal = public.current_legacy_user_id())))));


--
-- Name: volunteer_signup; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.volunteer_signup ENABLE ROW LEVEL SECURITY;

--
-- Name: web_sessions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.web_sessions ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict yrySWULcns9RlxEmPL59jbLznsDs7zKf67bqBMTbhO6HnYBlSa5CYshThahcda1

