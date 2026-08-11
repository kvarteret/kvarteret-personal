from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.db.session import current_session
from app.db.table_defs.email_delivery import email_deliveries, email_delivery_attempts
from app.email_delivery import EmailDeliveryRequest


class EmailOutboxRepository:
    """Persist queue, lease, and attempt state without preparing or sending email."""

    async def enqueue(
        self,
        request: EmailDeliveryRequest,
        *,
        delivery_id: UUID,
        now: datetime,
        enqueued_trace_id: str | None,
    ) -> tuple[UUID, bool]:
        session = _session()
        existing = await session.scalar(
            select(email_deliveries.c.id).where(
                email_deliveries.c.idempotency_key == request.idempotency_key
            )
        )
        if existing is not None:
            return existing, False
        try:
            async with session.begin_nested():
                await session.execute(
                    insert(email_deliveries).values(
                        id=delivery_id,
                        template_key=request.template_key,
                        template_version=request.template_version,
                        recipient_email=request.recipient_email.strip().lower(),
                        business_type=request.business_type,
                        business_id=request.business_id,
                        source_domain_event_id=request.source_domain_event_id,
                        idempotency_key=request.idempotency_key,
                        status="pending",
                        automatic_attempt_count=0,
                        next_attempt_at=now,
                        encrypted_context=request.encrypted_context,
                        enqueued_trace_id=enqueued_trace_id,
                        registration_id=request.registration_id,
                        supersedes_delivery_id=request.supersedes_delivery_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError:
            existing = await session.scalar(
                select(email_deliveries.c.id).where(
                    email_deliveries.c.idempotency_key == request.idempotency_key
                )
            )
            if existing is None:
                raise
            return existing, False
        return delivery_id, True

    async def claim_due(
        self,
        *,
        batch_size: int,
        now: datetime,
        lease_duration: timedelta,
    ) -> tuple[list[UUID], int]:
        session = _session()
        rows = (
            (
                await session.execute(
                    select(email_deliveries.c.id, email_deliveries.c.lease_until)
                    .where(
                        email_deliveries.c.status == "pending",
                        email_deliveries.c.next_attempt_at <= now,
                        or_(
                            email_deliveries.c.lease_until.is_(None),
                            email_deliveries.c.lease_until <= now,
                        ),
                    )
                    .order_by(
                        email_deliveries.c.next_attempt_at.asc(),
                        email_deliveries.c.created_at.asc(),
                    )
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .all()
        )
        interrupted_count = 0
        claimed: list[UUID] = []
        for row in rows:
            delivery_id = row["id"]
            if row["lease_until"] is not None:
                started = list(
                    (
                        await session.execute(
                            select(email_delivery_attempts.c.id).where(
                                email_delivery_attempts.c.delivery_id == delivery_id,
                                email_delivery_attempts.c.outcome == "started",
                            )
                        )
                    ).scalars()
                )
                if started:
                    await session.execute(
                        update(email_delivery_attempts)
                        .where(email_delivery_attempts.c.id.in_(started))
                        .values(outcome="interrupted", finished_at=now)
                    )
                    interrupted_count += len(started)
            await session.execute(
                update(email_deliveries)
                .where(email_deliveries.c.id == delivery_id)
                .values(
                    lease_owner=uuid4().hex,
                    lease_until=now + lease_duration,
                    updated_at=now,
                )
            )
            claimed.append(delivery_id)
        return claimed, interrupted_count

    async def start_attempt(
        self, delivery_id: UUID, *, now: datetime
    ) -> tuple[int, int, int | None]:
        session = _session()
        delivery = await self.get_delivery_row(delivery_id)
        attempt_no = int(delivery["automatic_attempt_count"]) + 1
        attempt_id = (
            await session.execute(
                insert(email_delivery_attempts)
                .values(
                    delivery_id=delivery_id,
                    attempt_no=attempt_no,
                    stage="prepare",
                    outcome="started",
                    started_at=now,
                )
                .returning(email_delivery_attempts.c.id)
            )
        ).scalar_one()
        await session.execute(
            update(email_deliveries)
            .where(email_deliveries.c.id == delivery_id)
            .values(automatic_attempt_count=attempt_no, updated_at=now)
        )
        return int(attempt_id), attempt_no, delivery["registration_id"]

    async def set_attempt_stage(self, attempt_id: int, stage: str) -> None:
        await _session().execute(
            update(email_delivery_attempts)
            .where(email_delivery_attempts.c.id == attempt_id)
            .values(stage=stage)
        )

    async def finish_success(
        self,
        delivery_id: UUID,
        attempt_id: int,
        *,
        now: datetime,
        duration_ms: int,
    ) -> None:
        session = _session()
        await session.execute(
            update(email_delivery_attempts)
            .where(email_delivery_attempts.c.id == attempt_id)
            .values(
                stage="smtp",
                outcome="succeeded",
                duration_ms=duration_ms,
                finished_at=now,
            )
        )
        await session.execute(
            update(email_deliveries)
            .where(email_deliveries.c.id == delivery_id)
            .values(
                status="sent",
                sent_at=now,
                updated_at=now,
                lease_owner=None,
                lease_until=None,
                encrypted_context=None,
                last_error_category=None,
            )
        )

    async def finish_failure(
        self,
        delivery_id: UUID,
        attempt_id: int,
        *,
        stage: str,
        outcome: str,
        category: str,
        smtp_status: int | None,
        duration_ms: int,
        delivery_values: Mapping[str, Any],
        now: datetime,
    ) -> None:
        session = _session()
        await session.execute(
            update(email_delivery_attempts)
            .where(email_delivery_attempts.c.id == attempt_id)
            .values(
                stage=stage,
                outcome=outcome,
                error_category=category,
                smtp_status=smtp_status,
                smtp_status_class=(smtp_status // 100 if smtp_status else None),
                duration_ms=duration_ms,
                finished_at=now,
            )
        )
        await session.execute(
            update(email_deliveries)
            .where(email_deliveries.c.id == delivery_id)
            .values(**delivery_values)
        )

    async def get_delivery_row(self, delivery_id: UUID) -> Mapping[str, Any]:
        return (
            (
                await _session().execute(
                    select(email_deliveries).where(email_deliveries.c.id == delivery_id)
                )
            )
            .mappings()
            .one()
        )

    async def get_delivery_row_or_none(
        self, delivery_id: UUID, *, for_update: bool = False
    ) -> Mapping[str, Any] | None:
        statement = select(email_deliveries).where(
            email_deliveries.c.id == delivery_id
        )
        if for_update:
            statement = statement.with_for_update()
        return ((await _session().execute(statement)).mappings().first())

    async def list_delivery_rows(
        self,
        *,
        status: str | None,
        template_key: str | None,
        created_after: datetime | None,
        limit: int,
    ) -> list[Mapping[str, Any]]:
        statement = select(email_deliveries).order_by(
            email_deliveries.c.created_at.desc()
        )
        if status:
            statement = statement.where(email_deliveries.c.status == status)
        if template_key:
            statement = statement.where(
                email_deliveries.c.template_key == template_key
            )
        if created_after:
            statement = statement.where(
                email_deliveries.c.created_at >= created_after
            )
        return list(
            (
                await _session().execute(
                    statement.limit(max(1, min(limit, 200)))
                )
            )
            .mappings()
            .all()
        )

    async def get_attempt_rows(
        self, delivery_id: UUID
    ) -> list[Mapping[str, Any]]:
        return list(
            (
                await _session().execute(
                    select(email_delivery_attempts)
                    .where(email_delivery_attempts.c.delivery_id == delivery_id)
                    .order_by(email_delivery_attempts.c.attempt_no.asc())
                )
            )
            .mappings()
            .all()
        )

    async def get_latest_registration_row(
        self, registration_id: int
    ) -> Mapping[str, Any] | None:
        return (
            (
                await _session().execute(
                    select(email_deliveries)
                    .where(email_deliveries.c.registration_id == registration_id)
                    .order_by(email_deliveries.c.created_at.desc())
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )


def _session():
    session = current_session()
    if session is None:
        raise RuntimeError("Email outbox requires an active database session.")
    return session
