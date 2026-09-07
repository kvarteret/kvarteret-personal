import { createApp, computed, h, ref, watch } from 'vue';

const states = [
  ['new', 'Ny'], ['contacted', 'Kontaktet'], ['trial', 'På prøve'],
  ['volunteer', 'Frivillig'], ['not_volunteer', 'Ikke frivillig'],
];
const normalize = (value) => value.trim().toLocaleLowerCase('nb');
const mounted = new Map();

function mountBoards() {
  // HTMX owns navigation; each Vue instance exclusively owns its mount element.
  for (const [root, app] of mounted) {
    if (!root.isConnected) { app.unmount(); mounted.delete(root); }
  }
  const root = document.getElementById('application-vue-island');
  if (!root || mounted.has(root)) return;
  const cards = Array.from(root.querySelectorAll('[data-vue-card]'), (template) => ({
    id: template.dataset.id,
    state: template.dataset.state,
    search: normalize(template.dataset.search),
    groups: template.dataset.groups.split(','),
    // Jinja has already escaped applicant data; never compile it as Vue code.
    html: template.innerHTML,
  }));
  const groups = Array.from(root.querySelector('#application-group').options, (option) => ({
    id: option.value, name: option.textContent,
  }));
  const params = new URLSearchParams(location.search);
  const app = createApp({
    setup() {
      const query = ref(params.get('q') || '');
      const status = ref(params.get('application_status') || '');
      const group = ref(params.get('group_id') || '0');
      const groupQuery = ref('');
      const applications = ref(cards);
      const error = ref('');
      const visible = computed(() => applications.value.filter((card) =>
        (!query.value.trim() || card.search.includes(normalize(query.value))) &&
        (group.value === '0' || card.groups.includes(group.value)) &&
        (!status.value || (status.value === 'active'
          ? !['volunteer', 'not_volunteer'].includes(card.state)
          : card.state === status.value))));
      const matchingGroups = computed(() => groups.filter((option) => option.id !== '0' &&
        normalize(option.name).includes(normalize(groupQuery.value))));
      watch([query, status, group], () => {
        const url = new URL(location.href);
        for (const [key, value] of [['q', query.value], ['application_status', status.value], ['group_id', group.value]]) {
          if (value && value !== '0') url.searchParams.set(key, value);
          else url.searchParams.delete(key);
        }
        history.replaceState(history.state, '', url);
      });

      async function cancelInvitation(event) {
        const form = event.target.closest('[data-cancel-application]');
        if (!form) return; // Other forms retain normal server-side submission.
        event.preventDefault();
        if (!window.confirm('Avbryte denne invitasjonen?')) return;
        const button = form.querySelector('button');
        if (button.disabled) return;
        button.disabled = true;
        error.value = '';
        try {
          const response = await fetch(`/volunteer-applications/${form.dataset.cancelApplication}`, {
            method: 'DELETE', credentials: 'same-origin',
            headers: {
              'HX-Request': 'true',
              'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content,
            },
          });
          if (!response.ok || response.redirected) throw new Error('Cancellation failed');
          applications.value = applications.value.filter((card) => card.id !== form.dataset.cancelApplication);
        } catch {
          error.value = 'Kunne ikke avbryte invitasjonen. Prøv igjen.';
        } finally {
          button.disabled = false;
        }
      }

      const field = (label, control) => h('label', { class: 'grid gap-1' }, [
        h('span', { class: 'text-sm text-stone-500' }, label), control,
      ]);
      const input = (id, model, placeholder) => h('input', {
        id, class: 'app-input', type: 'search', autocomplete: 'off', placeholder,
        value: model.value, onInput: (event) => { model.value = event.target.value; },
      });
      const select = (id, model, options) => h('select', {
        id, class: 'app-input', value: model.value,
        onChange: (event) => { model.value = event.target.value; },
      }, options.map(([value, label]) => h('option', { value }, label)));

      return () => h('div', { class: 'grid min-w-0 gap-7' }, [
        h('section', { class: 'app-panel min-w-0 grid gap-4 md:grid-cols-2' }, [
          field('Søk i søknader', input('application-query', query, 'Navn, e-post, telefon eller studiested')),
          field('Status', select('application-status', status, [['', 'Alle statuser'], ['active', 'Aktive søknader'], ...states])),
          field('Finn gruppe', input('application-group-search', groupQuery, 'Skriv gruppenavn')),
          field('Filtrer på gruppe', select('application-group', group, groups.filter((option) =>
            option.id === '0' || option.id === group.value || matchingGroups.value.includes(option)
          ).map((option) => [option.id, option.name]))),
          h('a', { href: location.pathname + location.search, class: 'app-button-secondary' }, 'Oppdater søknader'),
          groupQuery.value && h('p', { role: 'status', class: 'text-sm text-stone-500' },
            `${matchingGroups.value.length} ${matchingGroups.value.length === 1 ? "gruppe" : "grupper"} funnet. Valgt gruppe beholdes til du velger en annen.`),
        ]),
        error.value && h('p', { role: 'alert', class: 'text-kvarteret-red' }, error.value),
        h('section', { id: 'volunteer-application-list-panel', class: 'min-w-0', 'aria-label': 'Søknadstavle' }, [
          h('p', { role: 'status', class: 'mb-3 text-sm text-stone-500' },
            `${visible.value.length} ${visible.value.length === 1 ? 'søknad' : 'søknader'} · Åpne en søknad for å endre status.`),
          !visible.value.length && h('p', { class: 'mb-4 text-sm' }, 'Ingen søknader passer filtrene.'),
          h('div', { class: 'flex gap-4 overflow-x-auto pb-4', tabindex: 0, role: 'region',
            'aria-label': 'Statuskolonner, rull sidelengs for å se alle' }, states.map(([state, label]) => {
            const column = visible.value.filter((card) => card.state === state);
            return h('section', { key: state, 'data-application-state': state, 'aria-labelledby': `column-${state}`,
              class: 'w-72 shrink-0 border border-stone-300 bg-stone-100 p-3' }, [
              h('h2', { id: `column-${state}`, class: 'mb-4 flex items-center justify-between gap-2 border-t-4 border-kvarteret-red pt-3 text-lg font-medium' }, [
                label, h('span', { class: 'text-sm text-stone-500' }, column.length),
              ]),
              h('div', { class: 'grid gap-3' }, column.length ? column.map((card) =>
                h('div', { key: card.id, innerHTML: card.html, onSubmit: cancelInvitation })
              ) : [h('p', { class: 'border border-dashed border-stone-300 p-4 text-sm text-stone-500' }, 'Ingen søknader')]),
            ]);
          })),
        ]),
      ]);
    },
  });
  mounted.set(root, app);
  app.mount(root.querySelector('[data-vue-mount]'));
  root.querySelectorAll('[data-vue-card]').forEach((template) => template.remove());
}

mountBoards();
document.addEventListener('htmx:after:process', mountBoards);
