// The native multiple select is the form value and no-JavaScript fallback.
// The combobox only owns local typeahead and selection, not the board result.
(() => {
  const initialized = new WeakSet();
  function initializeGroups() {
    document.querySelectorAll('[data-group-picker]').forEach((root) => {
      if (initialized.has(root)) return;
      initialized.add(root);
      const select = root.querySelector('select');
      const enhanced = root.querySelector('[data-group-enhanced]');
      const input = enhanced.querySelector('input');
      const list = root.querySelector('[role="listbox"]');
      const chips = root.querySelector('[data-group-chips]');
      const status = root.querySelector('[data-group-status]');
      const options = Array.from(select.options);
      let active = 0;
      let matches = [];
      const selected = () => options.filter((option) => option.selected);
      const close = () => {
        list.hidden = true;
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
      };
      const highlight = () => {
        list.querySelectorAll('[role="option"]').forEach((option, index) => {
          option.dataset.active = String(index === active);
          if (index === active) {
            input.setAttribute('aria-activedescendant', option.id);
            option.scrollIntoView({ block: 'nearest' });
          }
        });
        if (!matches.length) input.removeAttribute('aria-activedescendant');
      };
      const render = () => {
        chips.replaceChildren();
        selected().forEach((option) => {
          const chip = document.createElement('button');
          chip.type = 'button';
          chip.className = 'group-combobox-chip';
          chip.textContent = `${option.textContent} ×`;
          chip.setAttribute('aria-label', `Fjern ${option.textContent}`);
          chip.addEventListener('click', () => toggle(option));
          chips.append(chip);
        });
        const query = input.value.trim().toLocaleLowerCase('nb');
        matches = options.filter((option) => option.textContent.toLocaleLowerCase('nb').includes(query));
        active = Math.min(active, Math.max(0, matches.length - 1));
        list.replaceChildren();
        matches.forEach((option, index) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.tabIndex = -1;
          button.id = `application-group-option-${option.value}`;
          button.className = 'group-combobox-option';
          button.setAttribute('role', 'option');
          button.setAttribute('aria-selected', String(option.selected));
          button.textContent = `${option.selected ? '✓ ' : ''}${option.textContent}`;
          button.addEventListener('pointerdown', (event) => event.preventDefault());
          button.addEventListener('click', () => { active = index; toggle(option); });
          list.append(button);
        });
        if (status) {
          status.textContent = matches.length
            ? (selected().length ? `${selected().length} grupper valgt` : '')
            : 'Ingen grupper funnet';
        }
        if (!list.hidden) highlight();
      };
      const open = () => {
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        render();
      };
      const toggle = (option) => {
        option.selected = !option.selected;
        render();
        select.dispatchEvent(new Event('change', { bubbles: true }));
        input.focus();
      };
      input.addEventListener('focus', open);
      input.addEventListener('click', open);
      input.addEventListener('input', () => { active = 0; open(); });
      input.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          if (list.hidden) { open(); return; }
          active = matches.length ? (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length : 0;
          highlight();
        } else if (event.key === 'Enter') {
          event.preventDefault();
          if (!list.hidden && matches[active]) toggle(matches[active]);
          else open();
        } else if (event.key === 'Escape') {
          event.preventDefault(); close();
        } else if (event.key === 'Backspace' && !input.value && selected().length) {
          toggle(selected().at(-1));
        }
      });
      root.addEventListener('focusout', (event) => {
        if (!root.contains(event.relatedTarget)) close();
      });
      select.hidden = true;
      select.classList.add('hidden');
      root.querySelector('label').htmlFor = input.id;
      enhanced.hidden = false;
      render();
    });
  }
  document.addEventListener('DOMContentLoaded', initializeGroups);
  document.addEventListener('htmx:after:process', initializeGroups);
})();
