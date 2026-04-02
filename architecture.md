# Architecture Overview
This document serves as a critical, living template designed to equip agents with a rapid and comprehensive understanding of the codebase's architecture, enabling efficient navigation and effective contribution from day one. Update this document as the codebase evolves.

This document was last updated by Codex 5.4 High on Thu April 2.

## 1. Project Structure
This section provides a high-level overview of the project's directory and file structure, categorized by architectural layer or major functional area. It is essential for quickly navigating the codebase, locating relevant files, and understanding the overall organization and separation of concerns.

```text
[Project Root]/
├── api/
│   └── index.py                 # Vercel ASGI entrypoint
├── app/
│   ├── api/                     # JSON APIs, including legacy adapters and v1 routes
│   ├── auth/                    # Login bridge, session storage, cookies, roles
│   ├── db/                      # SQLAlchemy session/runtime setup and shared table metadata
│   ├── domain/                  # Feature-oriented business logic
│   │   ├── admin_accounts/
│   │   ├── courses/
│   │   ├── feedback/
│   │   ├── groups/
│   │   ├── mobile_card/
│   │   ├── search/
│   │   ├── spotify/
│   │   ├── volunteer_applications/
│   │   └── volunteers/
│   ├── infrastructure/          # Cross-cutting adapters such as storage, email, phone, media, formatting
│   ├── media/                   # Backend media proxy routes for photos and documents
│   ├── shared/                  # Small reusable helpers with no domain ownership
│   ├── static/                  # Tailwind output, images, browser-side scripts
│   ├── system/                  # Health and system-oriented routes
│   ├── templates/               # Jinja layouts, pages, and feature-grouped components
│   ├── web/                     # Server-rendered route composition and template integration
│   ├── main.py                  # FastAPI app factory and middleware
│   └── runtime.py               # Application container and dependency wiring
├── plans/                       # Design notes and migration plans
├── scripts/                     # Operational and maintenance scripts
├── tests/
│   ├── api/                     # API and system route coverage
│   ├── support/                 # Shared test helpers
│   ├── unit/                    # Domain and infrastructure unit tests
│   └── web/                     # Server-rendered route coverage
├── AGENTS.md                    # Agent-specific repo instructions
├── Makefile                     # Common development commands
├── README.md                    # Project overview and local setup
├── architecture.md              # This document
├── package.json                 # Bun/Tailwind/browser asset pipeline
├── pyproject.toml               # Python package metadata and tool config
└── vercel.json                  # Vercel deployment and routing config
```

## 2. High-Level System Diagram
Provide a simple block diagram or a clear text-based description of the major components and their interactions. Focus on how data flows, services communicate, and key architectural boundaries.

```text
[Browser Admin UI]
        |
        v
[FastAPI app: app/main.py]
        |
        +--> [Web routes + Jinja templates]
        |         |
        |         v
        |   [Domain services]
        |         |
        |         v
        |   [SQLAlchemy repositories / db tables]
        |         |
        |         v
        |   [Supabase Postgres]
        |
        +--> [Media proxy routes]
        |         |
        |         +--> [Azure Blob Storage for photos when configured]
        |         |
        |         +--> [Supabase Storage for documents and fallback photo storage]
        |
        +--> [JSON APIs]
                  |
                  +--> [/api/v1/mobile-card/*]
                  +--> [/api/legacy/mobile-card/*]
                  +--> [/api/now-playing/*]

[Browser Admin UI] <--> [Session cookie + session store] <--> [Supabase Auth bridge]
[Spotify OAuth flow] <--> [Now playing domain] <--> [Spotify Web API]
[SMTP adapter] <--> [Volunteer applications / mobile card email flows]
```

## 3. Core Components
List and briefly describe the main components of the system. For each, include its primary responsibility and key technologies used.

### 3.1. Frontend

Name: Server-rendered admin UI

Description: The primary user-facing interface is rendered on the server with FastAPI and Jinja templates. It covers volunteer management, groups, courses, admin accounts, volunteer applications, feedback, and Spotify now-playing administration. The UI uses feature-grouped templates and small browser-side scripts rather than a separate SPA.

Technologies: FastAPI templating, Jinja2, Tailwind CSS, small Bun-built browser scripts

Deployment: Served from the same Vercel-hosted FastAPI application as the backend routes

### 3.2. Backend Services

#### 3.2.1. FastAPI Application

Name: Kvarteret Personal application server

Description: Handles server-rendered HTML, JSON APIs, media proxying, authentication/session middleware, and dependency wiring. The application is deployed as one ASGI service with separate route surfaces for web, API, media, and system endpoints.

Technologies: Python 3.13, FastAPI, SQLAlchemy Core, httpx, Jinja2

Deployment: Vercel via `api/index.py`

#### 3.2.2. Domain Packages

Name: Feature-oriented domain layer

Description: Encapsulates business workflows by feature instead of by technical layer. Each domain package owns its service orchestration and any feature-specific repositories, models, and mappers.

Technologies: Python, SQLAlchemy Core, dataclasses

Deployment: Runs inside the same FastAPI process

## 4. Data Stores
List and describe the databases and other persistent storage solutions used.

### 4.1. Primary Relational Database

Name: Kvarteret personnel database

Type: Supabase Postgres

Purpose: Stores the copied legacy personnel schema plus additive application tables for sessions, migrated users, admin memberships, volunteer applications, and related operational state.

Key Schemas/Collections: `public.personal`, `public.historie`, `public.verv`, `public.grupper`, `public.user_accounts`, `public.group_admin_memberships`, `public.web_sessions`, `public.registrering`, `public.nytt_personal`, `public.integration_tokens`

### 4.2. Private File Storage

Name: Document and media storage

Type: Supabase Storage and Azure Blob Storage

Purpose: Private documents are stored in Supabase Storage. Photos can be served from Azure Blob Storage when legacy Azure credentials are configured, otherwise photo operations can fall back to Supabase storage.

Key Schemas/Collections: Supabase buckets such as document and photo buckets, Azure photo container configured through settings

### 4.3. In-Process Caches

Name: Runtime TTL caches

Type: Process-local memory

Purpose: Used for request-adjacent performance optimizations such as session lookups, volunteer detail panels, pending application counts, and small option lists. These caches improve latency but are intentionally ephemeral and worker-local.

## 5. External Integrations / APIs
List any third-party services or external APIs the system interacts with.

Service Name 1: Supabase Auth

Purpose: Migrated web-user authentication and user lifecycle management

Integration Method: Supabase Auth HTTP API through the auth gateway

Service Name 2: Supabase Storage

Purpose: Private document storage, signed URLs, bucket maintenance, optional photo storage

Integration Method: Storage REST API through `httpx`

Service Name 3: Azure Blob Storage

Purpose: Legacy-compatible photo storage and signed photo access when configured

Integration Method: Azure SDK

Service Name 4: Spotify Web API

Purpose: OAuth token exchange and current-track retrieval for the now-playing feature

Integration Method: HTTPS API through `httpx`

Service Name 5: SMTP server

Purpose: Sending volunteer application and mobile-card related emails

Integration Method: Python SMTP client

## 6. Deployment & Infrastructure

Cloud Provider: Vercel for the application runtime, plus Supabase and Azure for managed services

Key Services Used: Vercel Functions, Supabase Postgres, Supabase Auth, Supabase Storage, Azure Blob Storage

CI/CD Pipeline: Not explicitly documented in this repository

Monitoring & Logging: Application request logging and context binding live in `app/observability.py`; browser-side Vercel Analytics and Speed Insights assets are bundled through the frontend asset pipeline

## 7. Security Considerations
Highlight any critical security aspects, authentication mechanisms, or data encryption practices.

Authentication: Signed session cookies for the admin UI, Supabase Auth for migrated users, signed mobile-card session tokens for app access

Authorization: Role-based checks via `UserRole` and route-level dependency enforcement; group-admin scope is still narrower in some flows than intended

Data Encryption: Application-layer signing is used for cookies and media tokens. Transport security and managed-service encryption are primarily delegated to the deployment platform and hosted providers.

Key Security Tools/Practices: Signed opaque session ids, backend media-token indirection instead of exposing storage URLs directly, explicit `NotConfiguredError` failures for missing secrets, known gaps around CSRF and RLS still tracked as debt

## 8. Development & Testing Environment

Local Setup Instructions: `make install` installs Python dependencies with `uv` and frontend tooling with `bun`; `make run` builds assets and starts the FastAPI app; `make css-watch` watches Tailwind CSS changes

Testing Frameworks: `pytest`, `pytest-asyncio`

Code Quality Tools: `ruff`, `ty`, Bun asset builds, Tailwind CLI

## 9. Future Considerations / Roadmap
Briefly note any known architectural debts, planned major changes, or significant future features that might impact the architecture.

- Tighten group-admin scoped authorization so admin mutations do not over-rely on full admin role checks
- Add stronger browser mutation protections such as CSRF coverage
- Improve migration story for the copied legacy public schema so the baseline is reproducible
- Continue replacing stale architectural language left over from the old Angular/ASP.NET system as new slices are rewritten

## 10. Project Identification

Project Name: Kvarteret Personal

Repository URL: https://github.com/kvarteret/kvarteret-personal

Primary Contact/Team: Not documented in the repository

Date of Last Update: 2026-04-02

## 11. Glossary / Acronyms
Define any project-specific terms or acronyms.

Digital Internkort: The mobile card feature and API surface used by the organization's mobile app

Pingvin points: Legacy point values attached to role assignments and used in reporting and search filters

HTMX fragment request: A partial-page request identified by headers such as `HX-Request`, used to refresh sections of server-rendered pages without a full navigation

Semester transfer: The workflow that previews and inserts next-semester group assignments based on a prior semester
