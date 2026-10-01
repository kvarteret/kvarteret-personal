"""Value-free diagnostics: never serialize messages, SQL, inputs or credentials."""

from __future__ import annotations

import re


def exception_chain(error: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    while len(chain) < 12 and not any(item is error for item in chain):
        chain.append(error)
        next_error = error.__cause__ or (
            None if error.__suppress_context__ else error.__context__
        )
        if next_error is None:
            break
        error = next_error
    return chain


def exception_diagnostics(error: BaseException) -> dict[str, object]:
    chain = exception_chain(error)
    fields: dict[str, object] = {
        "error_chain": ",".join(type(item).__name__ for item in chain),
        "error_category": type(chain[-1]).__name__.lower(),
    }
    for item in chain:
        sqlstate = getattr(item, "sqlstate", None)
        if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
            fields["db_sqlstate"] = sqlstate
        if type(item).__name__ == "SmtpDeliveryError":
            fields["error_category"] = item.category
            fields["retryable"] = item.retryable
            fields["failure_stage"] = item.phase
            fields["delivery_uncertain"] = item.delivery_uncertain
            if item.smtp_status is not None:
                fields["smtp_status_class"] = item.smtp_status // 100
    return fields
