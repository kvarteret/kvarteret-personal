// Delegation also handles pages reached through HTMX navigation. Keep the native
// select for keyboard support; searching never silently changes the active filter.
(() => {
  const optionsBySelect = new WeakMap();
  document.addEventListener("input", (event) => {
    if (!event.target.matches("[data-group-search]")) return;
    const filter = event.target.closest("[data-group-filter]");
    const select = filter.querySelector("[data-group-select]");
    if (!optionsBySelect.has(select)) {
      optionsBySelect.set(select, Array.from(select.options, (option) => option.cloneNode(true)));
    }
    const query = event.target.value.trim().toLocaleLowerCase("nb");
    const selected = select.value;
    const options = optionsBySelect.get(select);
    const matches = options.filter((option) => option.value !== "0" &&
      option.textContent.toLocaleLowerCase("nb").includes(query));
    select.replaceChildren(...options.filter((option) =>
      option.value === "0" || option.value === selected || matches.includes(option)
    ).map((option) => option.cloneNode(true)));
    select.value = selected;
    filter.querySelector("[data-group-feedback]").textContent = query
      ? `${matches.length} ${matches.length === 1 ? "gruppe" : "grupper"} funnet. Velg en gruppe nedenfor.`
      : "";
  });
})();
