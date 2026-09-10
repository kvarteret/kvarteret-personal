import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.after_commit import after_commit


def test_transaction_callbacks_follow_commit_rollback_and_new_transactions():
    seen = []
    with Session(create_engine("sqlite://")) as session:
        assert not after_commit(session, lambda: seen.append("no transaction"))
        session.execute(text("select 1"))
        after_commit(session, lambda: seen.append("rolled back"))
        session.rollback()
        session.execute(text("select 1"))
        after_commit(session, lambda: seen.append("committed"))
        session.commit()
        session.commit()
        assert seen == ["committed"]
        session.execute(text("select 1"))
        after_commit(session, lambda: seen.append("closed"))
    assert seen == ["committed"]


def test_savepoints_and_separate_sessions_do_not_leak_callbacks():
    seen = []
    engine = create_engine("sqlite://")
    with Session(engine) as outer, Session(engine) as other:
        outer.begin()
        after_commit(outer, lambda: seen.append("outer"))
        with outer.begin_nested():
            after_commit(outer, lambda: seen.append("released"))
        with pytest.raises(ValueError), outer.begin_nested():
            after_commit(outer, lambda: seen.append("savepoint rollback"))
            raise ValueError()
        other.begin()
        after_commit(other, lambda: seen.append("other"))
        other.commit()
        assert seen == ["other"]
        outer.commit()
        assert seen == ["other", "outer", "released"]


def test_callback_failure_does_not_fail_commit_or_skip_next_callback():
    seen = []
    with Session(create_engine("sqlite://")) as session:
        session.begin()
        def fail():
            raise RuntimeError("sink unavailable")
        after_commit(session, fail)
        after_commit(session, lambda: seen.append("success"))
        session.commit()
    assert seen == ["success"]
