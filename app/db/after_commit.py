"""Transaction-owned, best-effort callbacks; no domain service dependencies."""
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

_PENDING = "_after_commit_callbacks"
_COMMITTED = "_committed_callback_transactions"


def after_commit(session: Session, callback: Callable[[], None]) -> bool:
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is None:
        return False
    session.info.setdefault(_PENDING, {}).setdefault(transaction, []).append(callback)
    return True


@event.listens_for(Session, "after_commit")
def _mark_committed(session: Session) -> None:
    transaction = session.get_nested_transaction() or session.get_transaction()
    session.info.setdefault(_COMMITTED, set()).add(transaction)


@event.listens_for(Session, "after_transaction_end")
def _finish_transaction(session: Session, transaction: SessionTransaction) -> None:
    pending = session.info.get(_PENDING, {})
    callbacks = pending.pop(transaction, [])
    committed = session.info.get(_COMMITTED, set())
    succeeded = transaction in committed
    committed.discard(transaction)
    if succeeded and transaction.nested and transaction.parent is not None:
        pending.setdefault(transaction.parent, []).extend(callbacks)
    elif succeeded and transaction.parent is None:
        for callback in callbacks:
            try:
                callback()
            except Exception:
                # A projection must never invalidate a successful database commit.
                from app.observability import _record_diagnostic

                _record_diagnostic("sink_failure")
    if transaction.parent is None:
        session.info.pop(_PENDING, None)
        session.info.pop(_COMMITTED, None)
