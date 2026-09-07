// Status writes use the existing lifecycle endpoints. Only promotion needs the
// application detail form, because group/role/semester choices cannot be guessed.
(() => {
  const actions = {
    new: { contacted: 'contact', not_volunteer: 'reject' },
    contacted: { trial: 'trial', not_volunteer: 'reject' },
    trial: { volunteer: 'approval', not_volunteer: 'reject' },
    volunteer: { not_volunteer: 'reject' },
    not_volunteer: { contacted: 'reopen', volunteer: 'restore-volunteer' },
  };
  const instances = new Map();
  let saving = false;
  let originalNext = null;
  function feedback(message) {
    const target = document.getElementById('application-board-feedback');
    if (target) { target.hidden = false; target.textContent = message; }
  }
  function initializeBoard() {
    for (const [element, instance] of instances) {
      if (!element.isConnected) { instance.destroy(); instances.delete(element); }
    }
    const dialog = document.querySelector('dialog[data-open-promotion]');
    if (dialog && !dialog.open) { dialog.removeAttribute('data-open-promotion'); dialog.showModal(); }
    if (!window.Sortable) return;
    document.querySelectorAll('[data-application-lane]').forEach((lane) => {
      if (instances.has(lane)) return;
      instances.set(lane, new Sortable(lane, {
        group: 'applications', sort: false, draggable: '[data-application-card]',
        animation: 150, delay: 150, delayOnTouchOnly: true, touchStartThreshold: 5,
        ghostClass: 'application-drag-ghost', disabled: saving,
        onStart(event) {
          originalNext = event.item.nextSibling;
          const destinations = actions[event.item.dataset.state] || {};
          instances.forEach((_, element) => element.classList.toggle('application-drop-allowed', Boolean(destinations[element.dataset.applicationLane])));
        },
        onMove(event) {
          return Boolean(actions[event.dragged.dataset.state]?.[event.to.dataset.applicationLane]);
        },
        async onEnd(event) {
          instances.forEach((_, element) => element.classList.remove('application-drop-allowed'));
          if (event.from === event.to) return;
          // Keep the server-confirmed position until a fresh board is returned.
          event.from.insertBefore(event.item, originalNext);
          const action = actions[event.item.dataset.state]?.[event.to.dataset.applicationLane];
          if (!action || saving) return;
          const id = event.item.dataset.id;
          if (action === 'approval') {
            location.assign(`/volunteer-applications/${id}?promote=1`);
            return;
          }
          saving = true;
          instances.forEach((instance) => instance.option('disabled', true));
          feedback('Lagrer status …');
          try {
            const response = await fetch(`/volunteer-applications/${id}/${action}`, {
              method: 'POST', credentials: 'same-origin',
              headers: {
                'HX-Request': 'true', 'HX-Target': 'section#volunteer-application-list-panel',
                'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content,
              },
            });
            if (response.status !== 204) {
              let message = 'Kunne ikke flytte søknaden. Oppdater tavlen og prøv igjen.';
              if (response.headers.get('content-type')?.includes('application/json')) {
                const body = await response.json();
                if (typeof body.detail === 'string') message = body.detail;
              }
              throw new Error(message);
            }
            feedback('Status lagret.');
            const form = document.getElementById('application-filters');
            if (form) htmx.trigger(form, 'submit');
          } catch (error) {
            feedback(error.message || 'Kunne ikke kontakte serveren. Prøv igjen.');
          } finally {
            saving = false;
            instances.forEach((instance) => instance.option('disabled', false));
          }
        },
      }));
    });
  }
  document.addEventListener('DOMContentLoaded', initializeBoard);
  document.addEventListener('htmx:after:process', initializeBoard);
})();
