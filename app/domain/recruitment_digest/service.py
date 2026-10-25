"""Daily digest emails for each group's rekrutteringsansvarlig.

One email per recipient per day, so a busy day of applications never becomes a
burst of messages. The digest covers new applicants, applicants still waiting
(``new``) after 3 and 7 days, and trials with 7 days left or just finished.
Recipients are the group's recruitment contact address and/or chosen person (both when both
are set), falling back to the group's current leaders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import func, select

from app.db.session import current_session
from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteer_applications.tables import (
    volunteer_application_invites,
    volunteer_application_submissions,
)
from app.domain.volunteers.tables import volunteer_records
from app.email_delivery import (
    RECRUITER_DAILY_DIGEST,
    EmailDeliveryOutboxProtocol,
    EmailDeliveryRequest,
)
from app.observability import get_logger
from app.shared.semester import get_current_semester_code

logger = get_logger(__name__)

LEADER_ROLE_NAMES = ("leder", "gruppeleder")
BUSINESS_TYPE = "recruitment_digest"

# Section key -> heading, in display order.
SECTION_TITLES = {
    "new": "Nye søkere",
    "waiting_3d": "Søkere som har ventet i 3 dager",
    "waiting_7d": "Søkere som har ventet i 7 dager",
    "trial_7d": "Prøvetid: 7 dager igjen",
    "trial_done": "Prøvetid: ferdig (0 dager igjen)",
    # Snapshot digest: where things stand right now.
    "waiting": "Søkere som venter på svar",
    "trial_active": "På prøvetid nå",
}

MAX_LISTED_PER_SECTION = 5
DRY_RUN_KEY = "_dry_run_for"
MISSING_KEY = "_missing_groups"

_DAY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class DigestCandidate:
    registration_id: int
    status: str
    created_at: datetime
    trial_ends_at: datetime | None
    group_ids: tuple[int, ...]


def classify(candidate: DigestCandidate, now: datetime) -> list[str]:
    """Return the digest sections this application belongs to at ``now``.

    Each section is a half-open day window ``(start, end]``, so a daily run
    reports every application exactly once.
    """

    def within(value: datetime | None, start: timedelta, end: timedelta) -> bool:
        return value is not None and now - start < value <= now - end

    created = _aware(candidate.created_at)
    ends = _aware(candidate.trial_ends_at) if candidate.trial_ends_at else None
    sections: list[str] = []
    if within(created, _DAY, timedelta(0)):
        sections.append("new")
    if candidate.status == "new":
        if within(created, 4 * _DAY, 3 * _DAY):
            sections.append("waiting_3d")
        if within(created, 8 * _DAY, 7 * _DAY):
            sections.append("waiting_7d")
    if candidate.status == "trial" and ends is not None:
        # trial_ends_at lies in the future for 7d, so mirror the window.
        if now + 6 * _DAY < ends <= now + 7 * _DAY:
            sections.append("trial_7d")
        if within(ends, _DAY, timedelta(0)):
            sections.append("trial_done")
    return sections


def classify_snapshot(candidate: DigestCandidate, now: datetime) -> list[str]:
    """Sections for the current-status digest, independent of day windows."""
    if candidate.status == "new":
        return ["waiting"]
    if candidate.status == "trial" and candidate.trial_ends_at is not None:
        ends = _aware(candidate.trial_ends_at)
        return ["trial_active"] if ends > now else ["trial_done"]
    return []


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class RecruitmentDigestService:
    def __init__(self, *, email_outbox: EmailDeliveryOutboxProtocol) -> None:
        self.email_outbox = email_outbox

    async def enqueue_daily_digests(self, *, now: datetime | None = None) -> int:
        """Queue one digest per recipient. Caller commits and dispatches."""
        now = now or datetime.now(UTC)
        digests, _missing = await self._collect(now, snapshot=False)
        today = now.date().isoformat()
        for recipient, per_section in digests.items():
            await self._enqueue(
                recipient, per_section, key=f"recruiter-digest:{today}:{recipient}",
                business_id=today,
            )
        return len(digests)

    async def enqueue_status_digests(
        self, *, now: datetime | None = None, redirect_to: str | None = None
    ) -> tuple[dict[str, dict[str, int]], list[dict]]:
        """Queue a current-status digest per recipient (a one-off, not a cron).

        With ``redirect_to`` every digest is sent to that address instead and
        marked as a dry run for the real recipient, and carries a note about
        groups that have applicants but nobody to send to. Returns the queued
        counts per recipient and those groups.
        """
        now = now or datetime.now(UTC)
        digests, missing = await self._collect(now, snapshot=True)
        missing_groups = await self._group_names(missing)
        stamp = now.strftime("%Y-%m-%dT%H%M")
        for recipient, per_section in digests.items():
            if redirect_to:
                await self._enqueue(
                    redirect_to,
                    {
                        **per_section,
                        DRY_RUN_KEY: recipient,
                        MISSING_KEY: missing_groups,
                    },
                    key=f"recruiter-status-dryrun:{stamp}:{recipient}",
                    business_id=stamp,
                )
            else:
                await self._enqueue(
                    recipient, per_section,
                    key=f"recruiter-status:{stamp}:{recipient}", business_id=stamp,
                )
        return (
            {r: {k: len(v) for k, v in s.items()} for r, s in digests.items()},
            missing_groups,
        )

    async def _group_names(self, counts: dict[int, int]) -> list[dict]:
        if not counts:
            return []
        rows = (
            await _session().execute(
                select(groups.c.id, groups.c.name).where(groups.c.id.in_(list(counts)))
            )
        ).all()
        return sorted(
            ({"group_id": g, "name": n, "applicants": counts[g]} for g, n in rows),
            key=lambda item: item["name"].lower(),
        )

    async def _enqueue(
        self, recipient: str, context: dict, *, key: str, business_id: str
    ) -> None:
        await self.email_outbox.enqueue(
            EmailDeliveryRequest(
                template_key=RECRUITER_DAILY_DIGEST,
                template_version=1,
                recipient_email=recipient,
                business_type=BUSINESS_TYPE,
                business_id=business_id,
                idempotency_key=key,
                # Only application ids; names are loaded when the email is
                # prepared so the outbox holds no applicant PII.
                encrypted_context=json.dumps(context).encode(),
            )
        )

    async def _collect(
        self, now: datetime, *, snapshot: bool
    ) -> tuple[dict[str, dict[str, list[list]]], dict[int, int]]:
        """Return recipient -> section -> [[registration_id, [group_ids]]] and
        the applicant count per group that has no recipient at all."""
        candidates = await self._load_candidates(now, snapshot=snapshot)
        digests: dict[str, dict[str, dict[int, list[int]]]] = {}
        recipients_by_group: dict[int, list[str]] = {}
        missing: dict[int, int] = {}
        for candidate in candidates:
            sections = (
                classify_snapshot(candidate, now) if snapshot else classify(candidate, now)
            )
            if not sections:
                continue
            for group_id in candidate.group_ids:
                if group_id not in recipients_by_group:
                    recipients_by_group[group_id] = await self._recipients(group_id)
                if not recipients_by_group[group_id]:
                    missing[group_id] = missing.get(group_id, 0) + 1
                for recipient in recipients_by_group[group_id]:
                    per_section = digests.setdefault(recipient, {})
                    for section in sections:
                        group_map = per_section.setdefault(section, {})
                        group_ids = group_map.setdefault(candidate.registration_id, [])
                        if group_id not in group_ids:
                            group_ids.append(group_id)
        return (
            {
                recipient: {
                    section: [[reg, gids] for reg, gids in group_map.items()]
                    for section, group_map in per_section.items()
                }
                for recipient, per_section in digests.items()
            },
            missing,
        )

    async def _load_candidates(
        self, now: datetime, *, snapshot: bool = False
    ) -> list[DigestCandidate]:
        invites = volunteer_application_invites
        trial_group = (
            select(role_assignments.c.group_id)
            .where(role_assignments.c.id == invites.c.trial_assignment_id)
            .scalar_subquery()
        )
        rows = (
            (
                await _session().execute(
                    select(
                        invites.c.id,
                        invites.c.status,
                        invites.c.created_at,
                        invites.c.trial_ends_at,
                        invites.c.first_choice_group_id,
                        invites.c.second_choice_group_id,
                        invites.c.initial_group_id,
                        trial_group.label("trial_group_id"),
                    ).where(
                        invites.c.status.in_(("new", "trial"))
                        if snapshot
                        else (invites.c.created_at > now - 8 * _DAY)
                        | (
                            (invites.c.status == "trial")
                            & (invites.c.trial_ends_at > now - _DAY)
                            & (invites.c.trial_ends_at <= now + 7 * _DAY)
                        )
                    )
                )
            )
            .mappings()
            .all()
        )
        candidates = []
        for row in rows:
            if row["status"] == "trial":
                group_ids = [
                    row["trial_group_id"]
                    or row["initial_group_id"]
                    or row["first_choice_group_id"]
                ]
                # A trial's own group is the interesting one for trial sections,
                # but the applicant also counts as an applicant to both choices.
                group_ids += [
                    row["first_choice_group_id"],
                    row["second_choice_group_id"],
                ]
            else:
                group_ids = [
                    row["first_choice_group_id"],
                    row["second_choice_group_id"],
                ]
            unique = tuple(dict.fromkeys(g for g in group_ids if g is not None))
            if unique:
                candidates.append(
                    DigestCandidate(
                        registration_id=row["id"],
                        status=row["status"],
                        created_at=row["created_at"],
                        trial_ends_at=row["trial_ends_at"],
                        group_ids=unique,
                    )
                )
        return candidates

    async def _recipients(self, group_id: int) -> list[str]:
        session = _session()
        # The explicit address and the chosen person both receive the digest;
        # leaders are only the fallback when neither is set.
        contact = (
            await session.execute(
                select(
                    groups.c.recruitment_contact_email,
                    volunteer_records.c.email.label("person_email"),
                )
                .select_from(
                    groups.outerjoin(
                        volunteer_records,
                        volunteer_records.c.id
                        == groups.c.recruitment_contact_volunteer_id,
                    )
                )
                .where(groups.c.id == group_id)
            )
        ).mappings().first()
        explicit = sorted(
            {
                value.strip().lower()
                for value in (
                    (contact or {}).get("recruitment_contact_email"),
                    (contact or {}).get("person_email"),
                )
                if value and value.strip()
            }
        )
        if explicit:
            return explicit
        emails = (
            await session.scalars(
                select(volunteer_records.c.email)
                .select_from(
                    role_assignments.join(
                        assignment_roles,
                        assignment_roles.c.id == role_assignments.c.role_id,
                    ).join(
                        volunteer_records,
                        volunteer_records.c.id == role_assignments.c.volunteer_id,
                    )
                )
                .where(
                    role_assignments.c.group_id == group_id,
                    role_assignments.c.semester == get_current_semester_code(),
                    func.lower(func.trim(assignment_roles.c.name)).in_(
                        LEADER_ROLE_NAMES
                    ),
                    volunteer_records.c.email.is_not(None),
                )
            )
        ).all()
        recipients = sorted({e.strip().lower() for e in emails if e and e.strip()})
        if not recipients:
            logger.warning(
                "recruitment_digest.no_recipient",
                extra={"event": "recruitment_digest.no_recipient", "group_id": group_id},
            )
        return recipients


_INK = "#26211e"
_MUTED = "#6f655e"
_BORDER = "#e4ddd3"
_RED = "#db242a"
_FONT = "DM Sans, Arial, Helvetica, sans-serif"
_LABEL = (
    f"font-family:{_FONT};font-size:11px;letter-spacing:1px;font-weight:700;"
    f"text-transform:uppercase;color:{_RED};margin:0 0 6px"
)

# Section -> one-line explanation shown under its title.
_SECTION_HINTS = {
    "new": "Søkte siden i går",
    "waiting_3d": "Ikke kontaktet etter 3 dager",
    "waiting_7d": "Ikke kontaktet etter 7 dager",
    "trial_7d": "Prøvetiden slutter om 7 dager",
    "trial_done": "Prøvetiden er over, men søkeren er ikke avklart",
    "waiting": "Ikke kontaktet ennå, eldste først",
    "trial_active": "Prøvetid pågår, de som slutter først øverst",
}


def _days_ago(moment: datetime, now: datetime) -> int:
    return max(0, (now - _aware(moment)).days)


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _age_text(days: int) -> str:
    return "i dag" if days == 0 else "for 1 dag siden" if days == 1 else f"for {days} dager siden"


async def render_digest_sections(
    per_section: dict, *, base_url: str, now: datetime | None = None
) -> tuple[str, int]:
    """Build the digest body (cards, stats, rows) and the applicant count.

    Every applicant links to their application, and every group chip links to
    the application list filtered to that group.
    """
    now = now or datetime.now(UTC)
    base = escape(base_url, quote=True)
    sections = {
        key: [(int(reg), [int(g) for g in gids]) for reg, gids in per_section.get(key, [])]
        for key in SECTION_TITLES
    }
    ids = sorted({reg for items in sections.values() for reg, _ in items})
    group_ids = sorted({g for items in sections.values() for _, gids in items for g in gids})
    people: dict[int, dict] = {}
    group_names: dict[int, str] = {}
    if ids:
        for row in (
            (
                await _session().execute(
                    select(
                        volunteer_application_invites.c.id,
                        volunteer_application_invites.c.email,
                        volunteer_application_invites.c.created_at,
                        volunteer_application_invites.c.trial_ends_at,
                        volunteer_application_submissions.c.first_name,
                        volunteer_application_submissions.c.last_name,
                    )
                    .select_from(
                        volunteer_application_invites.outerjoin(
                            volunteer_application_submissions,
                            volunteer_application_submissions.c.invite_id
                            == volunteer_application_invites.c.id,
                        )
                    )
                    .where(volunteer_application_invites.c.id.in_(ids))
                )
            )
            .mappings()
            .all()
        ):
            full = " ".join(filter(None, [row["first_name"], row["last_name"]])).strip()
            people[row["id"]] = {
                "name": full or row["email"],
                "created_at": row["created_at"],
                "trial_ends_at": row["trial_ends_at"],
            }
    if group_ids:
        group_names = dict(
            (await _session().execute(select(groups.c.id, groups.c.name).where(groups.c.id.in_(group_ids)))).all()
        )

    def row_meta(key: str, person: dict) -> tuple[str, int | None]:
        if key.startswith("trial") and person["trial_ends_at"] is not None:
            ends = _aware(person["trial_ends_at"])
            if ends > now:
                days = max(0, (ends - now).days)
                return f"{_plural(days, 'dag', 'dager')} igjen av prøvetiden", days
            days = _days_ago(ends, now)
            return f"Prøvetiden utløp {_age_text(days)}", days
        days = _days_ago(person["created_at"], now)
        return f"Søkte {_age_text(days)}", days

    def sort_key(key: str, item: tuple[int, list[int]]):
        person = people.get(item[0])
        if person is None:
            return (0, 0)
        if key in ("trial_active", "trial_7d") and person["trial_ends_at"]:
            return (0, _aware(person["trial_ends_at"]).timestamp())
        # Longest waiting first.
        return (0, _aware(person["created_at"]).timestamp())

    cards: list[str] = []
    listed: set[int] = set()
    counts: list[tuple[str, int]] = []
    oldest_waiting = 0
    for key, title in SECTION_TITLES.items():
        items = sorted(
            [item for item in sections[key] if item[0] in people],
            key=lambda item: sort_key(key, item),
        )
        if not items:
            continue
        listed.update(reg for reg, _ in items)
        counts.append((title, len(items)))
        rows = []
        for reg, gids in items[:MAX_LISTED_PER_SECTION]:
            person = people[reg]
            meta, days = row_meta(key, person)
            if key in ("waiting", "waiting_3d", "waiting_7d") and days is not None:
                oldest_waiting = max(oldest_waiting, days)
            chips = " ".join(
                f'<a href="{base}/volunteer-applications?groups_selected=true&amp;q=&amp;group_ids={g}"'
                f' style="color:{_RED};text-decoration:none">{escape(group_names.get(g, "Gruppe"))}</a>'
                for g in gids
            )
            rows.append(
                f'<tr><td style="padding:12px 16px;border-top:1px solid {_BORDER};font-family:{_FONT}">'
                f'<a href="{base}/volunteer-applications/{reg}" style="color:{_INK};font-weight:700;'
                f'font-size:15px;text-decoration:none">{escape(person["name"])}</a>'
                f'<div style="font-size:13px;color:{_MUTED};margin-top:2px">{escape(meta)}'
                f"{' · ' + chips if chips else ''}</div></td>"
                f'<td style="padding:12px 16px;border-top:1px solid {_BORDER};text-align:right;'
                f'font-family:{_FONT};font-size:18px;font-weight:700;color:{_INK};white-space:nowrap">'
                f'{"" if days is None else days}</td></tr>'
            )
        if len(items) > MAX_LISTED_PER_SECTION:
            rows.append(
                f'<tr><td colspan="2" style="padding:12px 16px;border-top:1px solid {_BORDER};'
                f'font-family:{_FONT};font-size:14px;color:{_MUTED}">'
                f"Og {len(items) - MAX_LISTED_PER_SECTION} til</td></tr>"
            )
        cards.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid {_BORDER};border-radius:8px;border-collapse:separate;margin:0 0 16px">'
            f'<tr><td colspan="2" style="padding:16px;font-family:{_FONT}">'
            f'<div style="font-size:16px;font-weight:700;color:{_INK}">{escape(title)}</div>'
            f'<div style="font-size:13px;color:{_MUTED};margin-top:2px">{escape(_SECTION_HINTS.get(key, ""))}</div>'
            f"</td></tr>{''.join(rows)}</table>"
        )

    parts: list[str] = []
    missing = per_section.get(MISSING_KEY) or []
    if cards:
        summary = f"{_plural(len(listed), 'søker trenger', 'søkere trenger')} oppfølging."
        if oldest_waiting:
            summary += f" Den som har ventet lengst, har ventet {_plural(oldest_waiting, 'dag', 'dager')}."
        parts.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:#fdf3e3;border-radius:8px;margin:0 0 16px"><tr>'
            f'<td style="padding:16px;font-family:{_FONT}">'
            f'<div style="{_LABEL}">Start her</div>'
            f'<div style="font-size:17px;font-weight:700;color:{_INK};line-height:24px">{escape(summary)}</div>'
            f'<div style="margin-top:12px"><a href="{base}/volunteer-applications" '
            f'style="color:{_RED};font-weight:700;font-size:14px;text-decoration:none">Åpne søknadene →</a></div>'
            f"</td></tr></table>"
        )
        stat_cells = "".join(
            f'<td width="{100 // min(len(counts), 3)}%" style="padding:0 {"8px" if n < min(len(counts), 3) - 1 else "0"} 0 0">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid {_BORDER};border-radius:8px"><tr><td style="padding:12px 16px;font-family:{_FONT}">'
            f'<div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{_MUTED}">{escape(title)}</div>'
            f'<div style="font-size:28px;font-weight:700;color:{_INK};margin-top:4px">{count}</div>'
            f"</td></tr></table></td>"
            for n, (title, count) in enumerate(counts[:3])
        )
        parts.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 16px"><tr>{stat_cells}</tr></table>'
        )
    parts.extend(cards)
    if missing:
        rows = "".join(
            f'<li style="margin:0 0 4px"><a href="{base}/groups/{int(m["group_id"])}" '
            f'style="color:{_INK}">{escape(m["name"])}</a> '
            f'({_plural(int(m["applicants"]), "søker", "søkere")})</li>'
            for m in missing
        )
        parts.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid #e8b35a;background:#fff7e6;border-radius:8px;margin:0 0 16px">'
            f'<tr><td style="padding:16px;font-family:{_FONT};font-size:14px;color:{_INK}">'
            f'<div style="font-weight:700;font-size:16px;margin-bottom:6px">Grupper uten mottaker</div>'
            f"Disse gruppene har søkere, men verken kontakt-e-post, valgt person eller gruppeleder "
            f"dette semesteret, så ingen får e-post for dem."
            f'<ul style="padding-left:20px;margin:8px 0 0">{rows}</ul></td></tr></table>'
        )
    return "".join(parts), len(listed)


def _session():
    session = current_session()
    if session is None:
        raise RuntimeError("Recruitment digest requires an active database session.")
    return session
