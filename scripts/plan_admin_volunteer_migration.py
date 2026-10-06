"""Plan individual admin accounts from private inventory and review decisions.

This command has no database connection and never applies the migration.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path
import unicodedata


VALID_ROLES = frozenset({'Admin', 'Gruppeadmin', 'Frivillig', 'Tilskuer'})
PRIORITY = {'Admin': 3, 'Gruppeadmin': 2, 'Frivillig': 1, 'Tilskuer': 0}


def normalize(value: str | None) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value or '').casefold().split())


def build_plan(inventory: dict, decisions: dict, *, admin_group_id: int | None = None,
               semester: int | None = None) -> dict:
    """Return private proposals; explicit selections override automatic matches."""
    accounts = inventory['accounts']
    volunteers = {p['id']: p for p in inventory['volunteers']}
    groups = {g['id'] for g in inventory['groups']}
    if (admin_group_id is None) != (semester is None):
        raise ValueError('Administration group and current semester must be supplied together')
    if admin_group_id is not None and (admin_group_id not in groups or semester <= 0):
        raise ValueError('Invalid administration group or semester')
    if len({a['id'] for a in accounts}) != len(accounts):
        raise ValueError('Duplicate source account identifiers')
    if len(volunteers) != len(inventory['volunteers']):
        raise ValueError('Duplicate volunteer identifiers')
    if set(decisions) - {str(a['id']) for a in accounts}:
        raise ValueError('Decision references an unknown source account')
    memberships = collections.defaultdict(set)
    for membership in inventory['memberships']:
        memberships[membership['auth_user_id']].add(membership['group_id'])
    assignments = collections.defaultdict(list)
    for assignment in inventory['assignments']:
        assignments[assignment['volunteer_id']].append(assignment)
    rows = []
    individuals = {}
    for account in accounts:
        decision = decisions.get(str(account['id']), {})
        action = decision.get('action', 'pending')
        if action not in {'map', 'remove', 'no_recipient', 'pending'}:
            raise ValueError('Invalid migration action')
        role = decision.get('role', account['role'])
        if role not in VALID_ROLES:
            raise ValueError('Unknown access role')
        group_ids = sorted(set(decision.get('group_ids', memberships[account['auth_user_id']])))
        if set(group_ids) - groups:
            raise ValueError('Unknown group scope')
        selected = decision.get('volunteer_ids', [])
        if len(selected) != len(set(selected)) or set(selected) - volunteers.keys():
            raise ValueError('Invalid volunteer selection')
        if action == 'map' and not selected:
            raise ValueError('Mapping requires at least one volunteer')
        if action != 'map' and selected:
            raise ValueError('Volunteer selections require the map action')
        proposed = list(selected)
        reviewed = decision.get('reviewed', action == 'map')
        if not isinstance(reviewed, bool):
            raise ValueError('Review state must be a boolean')
        basis = 'reviewed selection' if action == 'map' and reviewed else 'private proposal; pending review' if action == 'map' else ''
        if action == 'pending':
            name = normalize(account.get('display_name'))
            # A role-less organizational placeholder cannot become an individual.
            candidates = [p['id'] for p in volunteers.values()
                          if name and normalize(f"{p.get('first_name') or ''} {p['last_name']}") == name
                          and any(a['semester'] > 0 for a in assignments[p['id']])]
            if len(candidates) == 1:
                proposed = candidates
                basis = 'exact name; pending review'
            # Email alone cannot establish the holder of a shared account.
        issues = []
        if not proposed and action == 'pending':
            issues.append('identity_unresolved')
        if proposed and role == 'Gruppeadmin' and not group_ids:
            issues.append('group_scope_missing')
        grants = []
        for pid in proposed:
            p = volunteers[pid]
            email = (p.get('email') or '').strip()
            if not email:
                issues.append('personal_email_missing')
            grant = dict(account_id=account['id'], role=role, group_ids=group_ids,
                         reviewed=action == 'map' and reviewed)
            grants.append(dict(volunteer_id=pid, **grant))
            individual = individuals.setdefault(pid, dict(
                volunteer_id=pid, name=' '.join(f"{p.get('first_name') or ''} {p['last_name']}".split()),
                personal_email=email, source_grants=[], issues=[]))
            individual['source_grants'].append(grant)
            individual['issues'].extend(issues)
        rows.append(dict(account_id=account['id'], action=action,
                         volunteer_ids=proposed, basis=basis, issues=sorted(set(issues)), grants=grants))
    administration_members = sorted({a['volunteer_id'] for a in inventory['assignments']
                                     if admin_group_id is not None
                                     and a.get('group_id') == admin_group_id
                                     and a['semester'] == semester})
    for pid in administration_members:
        if pid not in volunteers:
            raise ValueError('Administration assignment references an unknown volunteer')
        p = volunteers[pid]
        individual = individuals.setdefault(pid, dict(
            volunteer_id=pid, name=' '.join(f"{p.get('first_name') or ''} {p['last_name']}".split()),
            personal_email=(p.get('email') or '').strip(), source_grants=[], issues=[]))
        individual['source_grants'].append(dict(
            account_id=None, role='Admin', group_ids=[], reviewed=True,
            basis='current administration membership', group_id=admin_group_id, semester=semester))
        if not individual['personal_email']:
            individual['issues'].append('personal_email_missing')
    emails = collections.defaultdict(list)
    for individual in individuals.values():
        grants = individual['source_grants']
        individual['role'] = max((g['role'] for g in grants), key=PRIORITY.__getitem__)
        individual['group_ids'] = sorted({gid for g in grants for gid in g['group_ids']})
        if any(not g['reviewed'] for g in grants):
            individual['issues'].append('source_grant_pending_review')
        if individual['personal_email']:
            emails[individual['personal_email'].casefold()].append(individual['volunteer_id'])
    for pids in emails.values():
        if len(pids) > 1:
            for pid in pids:
                individuals[pid]['issues'].append('personal_email_shared_by_multiple_profiles')
    for individual in individuals.values():
        individual['issues'] = sorted(set(individual['issues']))
    return dict(review_only=True, source_accounts=rows,
                individual_accounts=list(individuals.values()),
                summary=dict(source_accounts=len(rows), individual_accounts=len(individuals),
                             removals=sum(r['action'] == 'remove' for r in rows),
                             no_recipients=sum(r['action'] == 'no_recipient' for r in rows),
                             administration_admins=len(administration_members),
                             unresolved_identities=sum('identity_unresolved' in r['issues'] for r in rows)))


def outside_checkout(path: Path) -> Path:
    """Keep private inputs and generated outputs outside any Git checkout."""
    path = path.expanduser().resolve()
    if any((parent / '.git').exists() for parent in (path.parent, *path.parents)):
        raise ValueError('Private migration files must be outside Git checkouts')
    return path


def write_private(path: Path, plan: dict) -> None:
    """Create a new private file; refuse symlinks and existing outputs."""
    path = outside_checkout(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(plan, output, ensure_ascii=False, indent=2)
        output.write('\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--decisions', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--administration-group-id', type=int)
    parser.add_argument('--semester', type=int)
    args = parser.parse_args()
    try:
        inventory = json.loads(outside_checkout(args.inventory).read_text())
        decisions = json.loads(outside_checkout(args.decisions).read_text())
        plan = build_plan(inventory, decisions, admin_group_id=args.administration_group_id,
                          semester=args.semester)
        write_private(args.output, plan)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, 'Migration planning failed; check private inputs and output location.\n')
    print(json.dumps(plan['summary']))


if __name__ == '__main__':
    main()
