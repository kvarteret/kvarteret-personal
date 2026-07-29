from app.shared.slugs import slugify


def test_slugify_transliterates_norwegian_group_names() -> None:
    assert slugify("Grøndahls") == "grondahls"
    assert slugify("Blandede Akademikere") == "blandede-akademikere"
    assert slugify("Quiz-gruppen") == "quiz-gruppen"


def test_slugify_has_no_group_specific_aliases() -> None:
    assert slugify("Debatt") == "debatt"
    assert slugify("Fest") == "fest"
