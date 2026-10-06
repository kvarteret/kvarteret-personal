"""Value-free diagnostics: never serialize messages, SQL, inputs or credentials."""

from __future__ import annotations

import re
from pathlib import Path


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
    tb = chain[-1].__traceback__
    if tb is not None:
        while tb.tb_next is not None:
            tb = tb.tb_next
        fields.update(
            error_file=Path(tb.tb_frame.f_code.co_filename).name,
            error_function=tb.tb_frame.f_code.co_name,
            error_line=tb.tb_lineno,
        )
    for item in chain:
        response = getattr(item, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            fields["dependency_status_code"] = status
    for item in chain:
        sqlstate = getattr(item, "sqlstate", None)
        if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
            fields["db_sqlstate"] = sqlstate
        if type(item).__name__ == "ResendDeliveryError":
            fields["error_category"] = item.category
            fields["retryable"] = item.retryable
            fields["failure_stage"] = item.phase
            fields["delivery_uncertain"] = item.delivery_uncertain
            if item.http_status is not None:
                fields["http_status_class"] = item.http_status // 100
    return fields
