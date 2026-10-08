const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function load() {
  const window = {};
  vm.runInNewContext(fs.readFileSync('app/static/js/volunteer-instant-search.js', 'utf8'), {
    window,
    document: {addEventListener() {}, readyState: 'loading', querySelectorAll: () => []},
  });
  return window.volunteerInstantSearch;
}

// Rows: [id, first, last, email, phone, has_photo, last_semester, points,
//        active, current_groups, current_roles, groups, roles]
const raw = {
  semester: 20262,
  groups: {1: 'Bar', 2: 'Teknisk'},
  roles: {5: 'Skiftleder'},
  volunteers: [
    [1, 'Ola', 'Nordmann', 'ola@example.test', '91234567', 1, 20262, 4, 1, [1], [5], [1, 2], [5]],
    [2, 'Kari', 'Olsen', 'kari@example.test', '', 0, 20251, 2, 0, [], [], [1], []],
    [3, 'Per', 'Hansen', 'per@example.test', '', 0, null, 0, 1, [2], [], [2], []],
  ],
};

test('ranks exact and prefix name matches first and respects the active filter', () => {
  const {prepareIndex, search} = load();
  const index = prepareIndex(raw);
  const ids = (results) => [...results].map((v) => v.row[0]);

  assert.deepEqual(ids(search(index, '', true)), [1, 3]);
  assert.deepEqual(ids(search(index, '', false)), [1, 2, 3]);
  // "ol" prefixes Ola's full name and Olsen's last name: Ola ranks first.
  assert.deepEqual(ids(search(index, 'OL', false)), [1, 2]);
  // Inactive volunteers are excluded in active mode.
  assert.deepEqual(ids(search(index, 'ola', true)), [1]);
  // Every token must match somewhere.
  assert.deepEqual(ids(search(index, 'ola hansen', false)), []);
});

test('group and role names match current assignments in active mode, all history otherwise', () => {
  const {prepareIndex, search} = load();
  const index = prepareIndex(raw);
  const ids = (results) => [...results].map((v) => v.row[0]);

  assert.deepEqual(ids(search(index, 'bar', true)), [1]);
  assert.deepEqual(ids(search(index, 'bar', false)), [1, 2]);
  assert.deepEqual(ids(search(index, 'skiftleder', true)), [1]);
  assert.deepEqual(ids(search(index, 'teknisk', false)).sort(), [1, 3]);
});
