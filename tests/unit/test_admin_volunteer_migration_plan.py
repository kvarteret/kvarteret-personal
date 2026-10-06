import json

import pytest

from scripts.plan_admin_volunteer_migration import build_plan, outside_checkout, write_private


@pytest.fixture
def inventory():
    return dict(
        accounts=[dict(id=1, auth_user_id='auth-one', display_name='Example Person', role='Admin')],
        volunteers=[dict(id=10, first_name='Example', last_name='Person', email=None),
                    dict(id=20, first_name='Another', last_name='Person', email=None)],
        groups=[dict(id=100)], memberships=[dict(auth_user_id='auth-one', group_id=100)],
        assignments=[dict(volunteer_id=10, semester=20262)],
    )


def test_shared_account_can_map_to_two_people_without_losing_access(inventory):
    plan = build_plan(inventory, {'1': dict(action='map', volunteer_ids=[10, 20])})
    assert [p['volunteer_id'] for p in plan['individual_accounts']] == [10, 20]
    assert all(p['role'] == 'Admin' for p in plan['individual_accounts'])
    assert all(p['source_grants'][0]['group_ids'] == [100] for p in plan['individual_accounts'])


def test_consolidation_preserves_separate_grants_and_highest_role(inventory):
    inventory['accounts'].append(dict(id=2, auth_user_id='auth-two', display_name='Other', role='Gruppeadmin'))
    plan = build_plan(inventory, {
        '1': dict(action='map', volunteer_ids=[10]),
        '2': dict(action='map', volunteer_ids=[10], group_ids=[100]),
    })
    assert len(plan['individual_accounts']) == 1
    person = plan['individual_accounts'][0]
    assert person['role'] == 'Admin'
    assert [g['account_id'] for g in person['source_grants']] == [1, 2]


@pytest.mark.parametrize('action', ['remove', 'no_recipient'])
def test_excluded_accounts_do_not_generate_grants(inventory, action):
    plan = build_plan(inventory, {'1': dict(action=action)})
    assert not plan['individual_accounts']
    assert plan['source_accounts'][0]['action'] == action


def test_duplicate_names_remain_unresolved(inventory):
    inventory['volunteers'][1].update(first_name='Example')
    inventory['assignments'].append(dict(volunteer_id=20, semester=20262))
    plan = build_plan(inventory, {})
    assert plan['summary']['unresolved_identities'] == 1
    assert not plan['individual_accounts']


def test_explicit_group_role_reduction_and_missing_scope(inventory):
    plan = build_plan(inventory, {'1': dict(action='map', volunteer_ids=[10], role='Gruppeadmin', group_ids=[])})
    assert plan['individual_accounts'][0]['role'] == 'Gruppeadmin'
    assert 'group_scope_missing' in plan['source_accounts'][0]['issues']


@pytest.mark.parametrize('decision', [
    dict(action='map', volunteer_ids=[999]),
    dict(action='remove', volunteer_ids=[10]),
    dict(action='map', volunteer_ids=[]),
    dict(action='map', volunteer_ids=[10], group_ids=[999]),
    dict(action='map', volunteer_ids=[10], role='Unknown'),
])
def test_invalid_selections_are_rejected(inventory, decision):
    with pytest.raises(ValueError):
        build_plan(inventory, {'1': decision})


def test_private_file_is_owner_only_and_never_overwritten(tmp_path):
    path = tmp_path / 'plan.json'
    write_private(path, {'review_only': True})
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())['review_only']
    with pytest.raises(FileExistsError):
        write_private(path, {})


def test_git_worktree_marker_blocks_private_files(tmp_path):
    (tmp_path / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError):
        outside_checkout(tmp_path / 'private.json')


def test_current_administration_members_receive_admin_even_without_source_account(inventory):
    inventory['assignments'].extend([
        dict(volunteer_id=20, group_id=100, semester=20262),
        dict(volunteer_id=20, group_id=100, semester=20262),
        dict(volunteer_id=10, group_id=100, semester=20261),
    ])
    plan = build_plan(inventory, {'1': dict(action='remove')}, admin_group_id=100, semester=20262)
    assert [p['volunteer_id'] for p in plan['individual_accounts']] == [20]
    assert plan['individual_accounts'][0]['role'] == 'Admin'
    assert plan['summary']['administration_admins'] == 1
    assert len(plan['individual_accounts'][0]['source_grants']) == 1


def test_administration_membership_overrides_group_role_reduction(inventory):
    inventory['assignments'][0]['group_id'] = 100
    plan = build_plan(inventory, {'1': dict(action='map', volunteer_ids=[10], role='Gruppeadmin', group_ids=[100])},
                      admin_group_id=100, semester=20262)
    assert plan['individual_accounts'][0]['role'] == 'Admin'
    assert len(plan['individual_accounts'][0]['source_grants']) == 2


def test_private_proposal_does_not_become_reviewed_selection(inventory):
    plan = build_plan(inventory, {'1': dict(action='map', volunteer_ids=[10], reviewed=False)})
    assert 'source_grant_pending_review' in plan['individual_accounts'][0]['issues']


def test_current_hovedstyret_gets_admin_and_overlapping_members_are_consolidated(inventory):
    inventory['groups'].append(dict(id=200))
    inventory['assignments'].extend([
        dict(volunteer_id=20, group_id=100, semester=20262),
        dict(volunteer_id=20, group_id=200, semester=20262),
        dict(volunteer_id=20, group_id=200, semester=20262),
        dict(volunteer_id=10, group_id=200, semester=20261),
    ])
    plan = build_plan(inventory, {'1': dict(action='remove')},
                      admin_group_id=100, board_group_id=200, semester=20262)
    assert [p['volunteer_id'] for p in plan['individual_accounts']] == [20]
    assert plan['individual_accounts'][0]['role'] == 'Admin'
    assert len(plan['individual_accounts'][0]['source_grants']) == 2
    assert plan['summary']['administration_admins'] == 1
    assert plan['summary']['hovedstyret_admins'] == 1


def test_hovedstyret_rule_can_run_without_administration_rule(inventory):
    inventory['assignments'][0]['group_id'] = 100
    plan = build_plan(inventory, {'1': dict(action='remove')}, board_group_id=100, semester=20262)
    assert plan['individual_accounts'][0]['role'] == 'Admin'
    assert plan['summary']['hovedstyret_admins'] == 1
