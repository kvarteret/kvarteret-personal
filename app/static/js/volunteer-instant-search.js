// Instant volunteer search: filter a compact index in the browser on every
// keystroke instead of a server round trip per keystroke.
//
// The page still renders server-side results first, and the form still works
// as a plain GET without JavaScript. Once the index arrives, typing and the
// "only active" toggle re-render the list locally. When nothing matches
// locally, the server's fuzzy (trigram) search gets a chance before showing
// "no matches".
(() => {
  const PAGE_SIZE = 50;
  const INDEX_MAX_AGE_MS = 60_000;
  const FIELD = {
    id: 0, first: 1, last: 2, email: 3, phone: 4, hasPhoto: 5, lastSemester: 6,
    points: 7, active: 8, currentGroups: 9, currentRoles: 10, groups: 11, roles: 12,
  };

  let indexPromise = null;
  let indexLoadedAt = 0;
  const photoUrls = new Map();

  function loadIndex(url) {
    if (!indexPromise || Date.now() - indexLoadedAt > INDEX_MAX_AGE_MS) {
      indexLoadedAt = Date.now();
      indexPromise = fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then((response) => {
          if (!response.ok) throw new Error(`search index ${response.status}`);
          return response.json();
        })
        .then(prepareIndex)
        .catch((error) => {
          indexPromise = null;
          throw error;
        });
    }
    return indexPromise;
  }

  function normalize(value) {
    return (value || "").toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  }

  function prepareIndex(raw) {
    const groupNames = new Map(Object.entries(raw.groups).map(([id, name]) => [Number(id), normalize(name)]));
    const roleNames = new Map(Object.entries(raw.roles).map(([id, name]) => [Number(id), normalize(name)]));
    const volunteers = raw.volunteers.map((row) => {
      const first = normalize(row[FIELD.first]);
      const last = normalize(row[FIELD.last]);
      return {
        row,
        first,
        last,
        full: normalize(`${row[FIELD.first]} ${row[FIELD.last]}`),
        email: normalize(row[FIELD.email]),
        phone: normalize(row[FIELD.phone]),
      };
    });
    return { semester: raw.semester, groupNames, roleNames, volunteers };
  }

  // Ids of groups/roles whose name contains the needle, computed once per
  // needle instead of once per volunteer.
  function namesMatching(names, needle) {
    const ids = new Set();
    for (const [id, name] of names) if (name.includes(needle)) ids.add(id);
    return ids;
  }

  function holdsAny(ids, matching) {
    if (!matching.size) return false;
    for (const id of ids) if (matching.has(id)) return true;
    return false;
  }

  // Mirrors the server's ranking (app/domain/volunteers/search_sql.py) minus
  // the trigram similarity terms, which the server fallback covers.
  function search(index, rawQuery, onlyActive) {
    const query = normalize(rawQuery);
    const pool = onlyActive ? index.volunteers.filter((v) => v.row[FIELD.active]) : index.volunteers;
    if (!query) return pool;

    const groupField = onlyActive ? FIELD.currentGroups : FIELD.groups;
    const roleField = onlyActive ? FIELD.currentRoles : FIELD.roles;
    const tokens = query.split(" ");
    const needles = [...new Set([query, ...tokens])];
    const groupMatches = new Map(needles.map((n) => [n, namesMatching(index.groupNames, n)]));
    const roleMatches = new Map(needles.map((n) => [n, namesMatching(index.roleNames, n)]));
    const inGroup = (v, n) => holdsAny(v.row[groupField], groupMatches.get(n));
    const inRole = (v, n) => holdsAny(v.row[roleField], roleMatches.get(n));

    const ranked = [];
    for (const v of pool) {
      let matchesAll = true;
      for (const token of tokens) {
        if (
          !v.full.includes(token) && !v.first.includes(token) && !v.last.includes(token) &&
          !v.email.includes(token) && !v.phone.includes(token) && !inGroup(v, token) && !inRole(v, token)
        ) {
          matchesAll = false;
          break;
        }
      }
      if (!matchesAll) continue;

      let score = 0;
      if (v.full === query) score += 100;
      if (v.last === query) score += 45;
      if (v.first === query) score += 35;
      if (v.full.startsWith(query)) score += 28;
      if (v.full.includes(query)) score += 16;
      if (inGroup(v, query)) score += 14;
      if (inRole(v, query)) score += 14;
      if (v.email.includes(query)) score += 10;
      if (v.phone.includes(query)) score += 10;
      for (const token of tokens) {
        if (v.full.includes(token)) score += 4;
        if (v.first.startsWith(token)) score += 5;
        if (v.last.startsWith(token)) score += 6;
        if (inGroup(v, token)) score += 3;
        if (inRole(v, token)) score += 3;
        if (v.email.includes(token)) score += 2.5;
      }
      ranked.push({ v, score });
    }
    ranked.sort((a, b) => b.score - a.score || compareNames(a.v, b.v));
    return ranked.map((entry) => entry.v);
  }

  function compareNames(a, b) {
    return (
      a.row[FIELD.last].localeCompare(b.row[FIELD.last], "nb") ||
      a.row[FIELD.first].localeCompare(b.row[FIELD.first], "nb") ||
      a.row[FIELD.id] - b.row[FIELD.id]
    );
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  function semesterLabel(code) {
    if (!code) return null;
    const year = Math.floor(code / 10);
    const season = code % 10;
    return season === 1 ? `${year} Vår` : season === 2 ? `${year} Høst` : String(code);
  }

  // Same markup as components/volunteers/volunteer_results.html.
  function rowHtml(v) {
    const row = v.row;
    const id = row[FIELD.id];
    const fullName = `${row[FIELD.first]} ${row[FIELD.last]}`.trim();
    const photoUrl = photoUrls.get(id);
    const avatar = photoUrl
      ? `<img alt="${escapeHtml(fullName)}" class="h-full w-full object-cover" decoding="async" fetchpriority="low" loading="lazy" src="${escapeHtml(photoUrl)}">`
      : escapeHtml(row[FIELD.last].slice(0, 1));
    const semester = semesterLabel(row[FIELD.lastSemester]);
    return `<a class="grid gap-4 border-b border-stone-300 py-4 text-stone-900 no-underline transition hover:bg-white/60 md:grid-cols-[minmax(0,1.7fr)_minmax(10rem,0.8fr)_minmax(14rem,1fr)_minmax(13rem,1fr)_minmax(10rem,0.8fr)] md:items-center" href="/volunteers/${id}">
    <div class="flex min-w-0 items-center gap-4">
      <div class="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-sm bg-stone-300 text-sm font-semibold text-stone-600" data-photo-for="${row[FIELD.hasPhoto] && !photoUrl ? id : ""}">${avatar}</div>
      <div class="min-w-0"><div class="truncate text-[1.15rem] font-medium tracking-[-0.03em]">${escapeHtml(fullName)}</div></div>
    </div>
    <div class="text-sm text-stone-800">Tlf: ${escapeHtml(row[FIELD.phone] || "-")}</div>
    <div class="text-sm text-stone-800">${escapeHtml(row[FIELD.email] || "Ingen e-post")}</div>
    <div class="text-sm text-stone-800">${semester ? `Sist registrert ${escapeHtml(semester)}` : "Ingen registrert historikk"}</div>
    <div class="text-sm text-stone-800">${row[FIELD.points]} pingvinpoeng</div>
  </a>`;
  }

  function countText(count, query, onlyActive) {
    if (query && onlyActive) return `${count} treff i dette semesteret`;
    if (query) return `${count} treff`;
    if (onlyActive) return `${count} aktive frivillige dette semesteret`;
    return `${count} frivillige`;
  }

  async function fillPhotos(container, photoUrlsEndpoint) {
    const slots = [...container.querySelectorAll("[data-photo-for]:not([data-photo-for=''])")];
    const ids = [...new Set(slots.map((slot) => Number(slot.dataset.photoFor)))].filter((id) => !photoUrls.has(id));
    if (ids.length) {
      try {
        const response = await fetch(`${photoUrlsEndpoint}?ids=${ids.join(",")}`, { credentials: "same-origin" });
        if (response.ok) {
          const urls = await response.json();
          for (const id of ids) photoUrls.set(id, urls[id] || null);
        }
      } catch {
        return; // Photos are decoration; the initials stay.
      }
    }
    for (const slot of slots) {
      const url = photoUrls.get(Number(slot.dataset.photoFor));
      if (!url || !slot.isConnected) continue;
      const img = document.createElement("img");
      img.alt = slot.parentElement.textContent.trim();
      img.className = "h-full w-full object-cover";
      img.decoding = "async";
      img.loading = "lazy";
      img.src = url;
      slot.replaceChildren(img);
      slot.dataset.photoFor = "";
    }
  }

  function init(root) {
    if (root.dataset.instantSearchReady) return;
    root.dataset.instantSearchReady = "true";

    const form = root.querySelector("form");
    const input = root.querySelector("input[name='q']");
    const activeToggle = root.querySelector("input[type='checkbox'][name='only_active']");
    const results = document.getElementById(root.dataset.resultsId);
    const indexUrl = root.dataset.indexUrl;
    const photoUrlsEndpoint = root.dataset.photoUrlsUrl;
    const serverListUrl = root.dataset.serverListUrl;
    if (!form || !input || !activeToggle || !results) return;

    let index = null;
    let matches = [];
    let shown = 0;
    let observer = null;
    let serverFallback = null;

    function syncUrl(query, onlyActive) {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      params.set("only_active", onlyActive ? "on" : "");
      history.replaceState(history.state, "", `${location.pathname}?${params}`);
    }

    function renderMore() {
      const next = matches.slice(shown, shown + PAGE_SIZE);
      shown += next.length;
      results.querySelector("[data-instant-sentinel]")?.remove();
      results.insertAdjacentHTML("beforeend", next.map(rowHtml).join(""));
      if (shown < matches.length) {
        // Loads automatically when scrolled into view; the button keeps it
        // reachable by keyboard and where IntersectionObserver never fires.
        results.insertAdjacentHTML(
          "beforeend",
          `<button class="w-full py-4 text-center text-sm text-stone-500 hover:text-stone-900" data-instant-sentinel type="button">Vis flere frivillige (${matches.length - shown} til)</button>`,
        );
        const sentinel = results.querySelector("[data-instant-sentinel]");
        sentinel.addEventListener("click", renderMore);
        observer.observe(sentinel);
      }
      schedulePhotos();
    }

    let photoTimer = null;
    function schedulePhotos() {
      // Typing re-renders on every keystroke; look up photos once it settles.
      clearTimeout(photoTimer);
      photoTimer = setTimeout(() => fillPhotos(results, photoUrlsEndpoint), 120);
    }

    async function renderServerFallback(query, onlyActive) {
      serverFallback?.abort();
      serverFallback = new AbortController();
      const params = new URLSearchParams({ q: query, only_active: onlyActive ? "on" : "", cursor: "" });
      try {
        const response = await fetch(`${serverListUrl}?${params}`, {
          credentials: "same-origin",
          signal: serverFallback.signal,
        });
        if (!response.ok) return;
        const html = await response.text();
        if (normalize(input.value) !== query || activeToggle.checked !== onlyActive) return;
        results.innerHTML = html;
        window.htmx?.process(results);
      } catch {
        // Aborted by a newer keystroke, or offline: keep the local result.
      }
    }

    function render() {
      if (!index) return;
      const query = normalize(input.value);
      const onlyActive = activeToggle.checked;
      matches = search(index, query, onlyActive);
      shown = 0;
      observer?.disconnect();
      observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) renderMore();
      });
      results.innerHTML = `<div class="flex items-center gap-2 border-b border-stone-300 pb-3 mb-1"><span class="text-sm text-stone-600">${escapeHtml(countText(matches.length, query, onlyActive))}</span></div>`;
      syncUrl(query, onlyActive);
      if (!matches.length) {
        results.insertAdjacentHTML("beforeend", '<div class="py-10 text-center text-sm text-stone-600">Ingen frivillige matchet dette søket.</div>');
        if (query) renderServerFallback(query, onlyActive);
        return;
      }
      serverFallback?.abort();
      renderMore();
    }

    input.addEventListener("input", render);
    activeToggle.addEventListener("change", render);
    form.addEventListener("submit", (event) => {
      if (!index) return; // No index yet: let the plain GET search run.
      event.preventDefault();
      render();
    });

    loadIndex(indexUrl)
      .then((loaded) => {
        if (!root.isConnected) return;
        index = loaded;
        root.dataset.instantSearch = "on";
        // Only re-render if the user already typed past the server render.
        if (normalize(input.value) !== normalize(root.dataset.initialQuery || "") ||
            activeToggle.checked !== (root.dataset.initialOnlyActive === "true")) {
          render();
        }
      })
      .catch(() => {
        // Index unavailable: fall back to a server request per change.
        let timer = null;
        const serverRender = () => {
          clearTimeout(timer);
          timer = setTimeout(() => {
            const query = normalize(input.value);
            syncUrl(query, activeToggle.checked);
            renderServerFallback(query, activeToggle.checked);
          }, 250);
        };
        input.addEventListener("input", serverRender);
        activeToggle.addEventListener("change", serverRender);
      });
  }

  function initAll() {
    document.querySelectorAll("[data-volunteer-instant-search]").forEach(init);
  }

  // Exposed for tests (tests/js/volunteer-instant-search.test.cjs).
  window.volunteerInstantSearch = { prepareIndex, search };

  document.addEventListener("DOMContentLoaded", initAll);
  document.addEventListener("htmx:after:settle", initAll);
  if (document.readyState !== "loading") initAll();
})();
