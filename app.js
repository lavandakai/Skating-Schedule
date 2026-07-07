const DATA_URL = "data/schedule.json";
const RINK_FILTER_STORAGE_KEY = "skating-schedule:activeRinks";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_LABELS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const SESSION_CLASSES = {
  "Public Skating": "public",
  "Family Skating": "family",
  "Adult Skating (18+)": "adult",
};
const LEGEND_LABELS = {
  "Public Skating": "Public",
  "Family Skating": "Family",
  "Adult Skating (18+)": "Adult (18+)",
};

const state = {
  data: null,
  activeRinks: new Set(),
  activeTypes: new Set(Object.keys(SESSION_CLASSES)),
  view: "today",
  anchor: new Date(),
  selectedDate: null,
};

function pad(n) {
  return String(n).padStart(2, "0");
}

function toISODate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function addMonths(d, n) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

function startOfWeek(d) {
  const r = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  r.setDate(r.getDate() - r.getDay());
  return r;
}

function startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function stripTime(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function formatClock(timeStr) {
  const [h, m] = timeStr.split(":").map(Number);
  const period = h < 12 ? "am" : "pm";
  const h12 = h % 12 || 12;
  return m === 0 ? `${h12}${period}` : `${h12}:${pad(m)}${period}`;
}

function formatTimestamp(isoString) {
  if (!isoString) return null;
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function loadSavedActiveRinks() {
  try {
    const saved = JSON.parse(localStorage.getItem(RINK_FILTER_STORAGE_KEY));
    return Array.isArray(saved) ? saved : null;
  } catch (err) {
    return null;
  }
}

function saveActiveRinks() {
  try {
    localStorage.setItem(RINK_FILTER_STORAGE_KEY, JSON.stringify([...state.activeRinks]));
  } catch (err) {
    // localStorage unavailable (private browsing, quota, etc.) — not worth surfacing to the user
  }
}

function updateUrlForSelection() {
  const url = new URL(window.location.href);
  if (state.selectedDate) {
    url.searchParams.set("date", state.selectedDate);
  } else {
    url.searchParams.delete("date");
  }
  history.replaceState(null, "", url);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function groupSessionsByDate(sessions, activeRinks, activeTypes) {
  const map = new Map();
  for (const session of sessions) {
    if (!activeRinks.has(session.rink)) continue;
    if (!activeTypes.has(session.type)) continue;
    if (!map.has(session.date)) map.set(session.date, []);
    map.get(session.date).push(session);
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.startTime.localeCompare(b.startTime));
  }
  return map;
}

function renderAttribution(strings) {
  return strings
    .map((text) => {
      if (text.includes("github.com/ottrec/scraper")) {
        return `Compiled data &copy; Patrick Gaskin's <a href="https://github.com/ottrec/scraper" target="_blank" rel="noopener">ottrec/scraper (GitHub)</a>.`;
      }
      if (text.includes("ottawa.ca/en/recreation-and-parks/facilities/place-listing")) {
        return `Facility information and schedules &copy; <a href="https://ottawa.ca/en/recreation-and-parks/facilities/place-listing" target="_blank" rel="noopener">City of Ottawa &ndash; Recreation Facilities</a>.`;
      }
      return escapeHtml(text);
    })
    .join(" ");
}

function renderLegend() {
  const el = document.getElementById("legend");
  el.innerHTML = Object.entries(SESSION_CLASSES)
    .map(([name, cls]) => {
      const active = state.activeTypes.has(name);
      return `<button type="button" class="legend-item${active ? "" : " inactive"}" data-type="${escapeHtml(name)}"><span class="dot ${cls}"></span>${escapeHtml(LEGEND_LABELS[name] || name)}</button>`;
    })
    .join("");

  el.querySelectorAll(".legend-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.type;
      if (state.activeTypes.has(name)) {
        state.activeTypes.delete(name);
      } else {
        state.activeTypes.add(name);
      }
      btn.classList.toggle("inactive");
      renderCalendar();
    });
  });
}

function renderRinkFilters() {
  const container = document.getElementById("rink-filters");
  container.innerHTML = state.data.rinks
    .map((rink) => {
      const active = state.activeRinks.has(rink.name);
      const flagged = rink.status === "error" || rink.status === "stale";
      const title = flagged && rink.error ? ` title="${escapeHtml(rink.error)}"` : "";
      const label = escapeHtml(rink.shortName || rink.name);
      return `<button class="rink-chip${active ? " active" : ""}" data-rink="${escapeHtml(rink.name)}"${title}>${label}${flagged ? " &#9888;" : ""}</button>`;
    })
    .join("");

  container.querySelectorAll(".rink-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.rink;
      if (state.activeRinks.has(name)) {
        state.activeRinks.delete(name);
      } else {
        state.activeRinks.add(name);
      }
      btn.classList.toggle("active");
      saveActiveRinks();
      renderCalendar();
    });
  });
}

function renderDayEvents(events) {
  if (!events.length) return "";
  const items = events
    .map((session) => {
      const cls = SESSION_CLASSES[session.type] || "public";
      return `
        <div class="cal-event">
          <span class="dot ${cls}"></span>
          <span class="cal-time">${formatClock(session.startTime)}</span>
          <span class="cal-rink">${escapeHtml(session.rinkShort || session.rink)}</span>
        </div>
      `;
    })
    .join("");
  return `<div class="cal-events">${items}</div>`;
}

function renderDayCell(date, sessionsByDate, { muted } = {}) {
  const iso = toISODate(date);
  const todayIso = toISODate(new Date());
  const events = sessionsByDate.get(iso) || [];
  const classes = ["cal-cell"];
  if (muted) classes.push("muted");
  if (iso === todayIso) classes.push("today");
  if (iso === state.selectedDate) classes.push("selected");
  return `
    <div class="${classes.join(" ")}" data-date="${iso}" role="button" tabindex="0">
      <span class="cal-daynum">${date.getDate()}</span>
      ${renderDayEvents(events)}
    </div>
  `;
}

function renderWeekView(sessionsByDate) {
  const start = startOfWeek(state.anchor);
  const days = Array.from({ length: 7 }, (_, i) => addDays(start, i));
  const header = days.map((d) => `<div class="cal-headcell">${WEEKDAY_LABELS[d.getDay()]}</div>`).join("");
  const cells = days.map((d) => renderDayCell(d, sessionsByDate)).join("");
  return `
    <div class="cal-grid week">
      <div class="cal-headrow">${header}</div>
      <div class="cal-body">${cells}</div>
    </div>
  `;
}

function renderMonthView(sessionsByDate) {
  const monthStart = startOfMonth(state.anchor);
  const gridStart = startOfWeek(monthStart);
  const daysInMonth = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0).getDate();
  const totalCells = Math.ceil((monthStart.getDay() + daysInMonth) / 7) * 7;
  const days = Array.from({ length: totalCells }, (_, i) => addDays(gridStart, i));
  const header = WEEKDAY_LABELS.map((l) => `<div class="cal-headcell">${l}</div>`).join("");
  const cells = days
    .map((d) => renderDayCell(d, sessionsByDate, { muted: d.getMonth() !== monthStart.getMonth() }))
    .join("");
  return `
    <div class="cal-grid month">
      <div class="cal-headrow">${header}</div>
      <div class="cal-body">${cells}</div>
    </div>
  `;
}

function renderSessionRow(session) {
  return `
    <a class="today-row" href="${escapeHtml(session.rinkUrl || "#")}" target="_blank" rel="noopener">
      <span class="today-time">
        <span class="dot ${SESSION_CLASSES[session.type] || "public"}"></span>
        ${formatClock(session.startTime)}&ndash;${formatClock(session.endTime)}
      </span>
      <span class="today-meta"><strong>${escapeHtml(session.rinkShort || session.rink)}</strong> &middot; ${escapeHtml(session.type)}</span>
    </a>
  `;
}

function renderDaySessions(label, events) {
  if (!events.length) {
    return `<p class="today-date">${label}</p><p class="empty-state">No skating scheduled &#128035;</p>`;
  }
  return `<p class="today-date">${label}</p>${events.map(renderSessionRow).join("")}`;
}

function renderTodayView(sessionsByDate) {
  const today = stripTime(new Date());
  const events = sessionsByDate.get(toISODate(today)) || [];
  const label = today.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  return `<div class="today-view">${renderDaySessions(label, events)}</div>`;
}

function renderDayDetail(sessionsByDate) {
  const el = document.getElementById("day-detail");
  if (state.view === "today") {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");

  if (!state.selectedDate) {
    el.innerHTML = `<p class="day-detail-hint">Tap a day above to see its skating times.</p>`;
    return;
  }

  const events = sessionsByDate.get(state.selectedDate) || [];
  const label = new Date(`${state.selectedDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long", month: "long", day: "numeric",
  });
  const body = events.length
    ? events.map(renderSessionRow).join("")
    : `<p class="empty-state">No skating scheduled &#128035;</p>`;
  const shareButton = events.length
    ? `<button type="button" class="share-btn" id="share-day-btn">&#128279; Copy link</button>`
    : "";

  el.innerHTML = `
    <div class="day-detail-header">
      <p class="today-date">${label}</p>
      ${shareButton}
    </div>
    ${body}
  `;

  const shareBtn = document.getElementById("share-day-btn");
  if (shareBtn) {
    shareBtn.addEventListener("click", async (e) => {
      const url = new URL(window.location.href);
      url.searchParams.set("date", state.selectedDate);
      const btn = e.currentTarget;
      try {
        await navigator.clipboard.writeText(url.toString());
        btn.textContent = "Copied!";
      } catch (err) {
        btn.textContent = "Couldn't copy";
      }
      setTimeout(() => {
        btn.innerHTML = "&#128279; Copy link";
      }, 1500);
    });
  }
}

function updateNav() {
  const navRow = document.getElementById("nav-row");
  if (state.view === "today") {
    navRow.classList.add("hidden");
    return;
  }
  navRow.classList.remove("hidden");
  const label = document.getElementById("nav-label");

  if (state.view === "week") {
    const start = startOfWeek(state.anchor);
    const end = addDays(start, 6);
    const startLabel = `${MONTH_LABELS[start.getMonth()].slice(0, 3)} ${start.getDate()}`;
    const endLabel = start.getMonth() === end.getMonth()
      ? `${end.getDate()}`
      : `${MONTH_LABELS[end.getMonth()].slice(0, 3)} ${end.getDate()}`;
    label.textContent = `${startLabel}–${endLabel}, ${end.getFullYear()}`;
  } else {
    label.textContent = `${MONTH_LABELS[state.anchor.getMonth()]} ${state.anchor.getFullYear()}`;
  }
}

function renderCalendar() {
  updateNav();
  const container = document.getElementById("calendar");
  const sessionsByDate = groupSessionsByDate(state.data.sessions, state.activeRinks, state.activeTypes);
  if (state.view === "today") {
    container.innerHTML = renderTodayView(sessionsByDate);
  } else {
    container.innerHTML = state.view === "week" ? renderWeekView(sessionsByDate) : renderMonthView(sessionsByDate);
    container.querySelectorAll(".cal-cell[data-date]").forEach((cell) => {
      const select = () => {
        state.selectedDate = cell.dataset.date;
        updateUrlForSelection();
        renderCalendar();
      };
      cell.addEventListener("click", select);
      cell.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          select();
        }
      });
    });
  }
  renderDayDetail(sessionsByDate);
}

async function main() {
  const generatedAtEl = document.getElementById("generated-at");

  let data;
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    data = await response.json();
  } catch (err) {
    document.getElementById("calendar").innerHTML = `<p class="empty-state">Couldn't load schedule data.</p>`;
    return;
  }

  state.data = data;
  state.activeRinks = new Set(data.rinks.map((r) => r.name));
  const savedRinks = loadSavedActiveRinks();
  if (savedRinks) {
    const validNames = new Set(data.rinks.map((r) => r.name));
    state.activeRinks = new Set(savedRinks.filter((name) => validNames.has(name)));
  }

  const when = formatTimestamp(data.generated_at);
  generatedAtEl.textContent = when ? `Last updated ${when}` : "";

  const attributionEl = document.getElementById("attribution");
  if (data.attribution && data.attribution.length) {
    attributionEl.innerHTML = renderAttribution(data.attribution);
  }

  renderLegend();
  renderRinkFilters();

  // A shared "?date=YYYY-MM-DD" link opens straight to that day, selected, in Month view.
  const sharedDate = new URLSearchParams(window.location.search).get("date");
  if (sharedDate && /^\d{4}-\d{2}-\d{2}$/.test(sharedDate)) {
    const parsed = new Date(`${sharedDate}T00:00:00`);
    if (!Number.isNaN(parsed.getTime())) {
      state.view = "month";
      state.anchor = parsed;
      state.selectedDate = sharedDate;
    }
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === state.view);
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
      state.anchor = new Date();
      state.selectedDate = state.view === "today" ? null : toISODate(new Date());
      updateUrlForSelection();
      document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
      renderCalendar();
    });
  });

  document.getElementById("nav-prev").addEventListener("click", () => {
    state.anchor = state.view === "week" ? addDays(state.anchor, -7) : addMonths(state.anchor, -1);
    state.selectedDate = null;
    updateUrlForSelection();
    renderCalendar();
  });
  document.getElementById("nav-next").addEventListener("click", () => {
    state.anchor = state.view === "week" ? addDays(state.anchor, 7) : addMonths(state.anchor, 1);
    state.selectedDate = null;
    updateUrlForSelection();
    renderCalendar();
  });

  renderCalendar();
}

main();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  });
}
