const DATA_URL = "data/schedule.json";

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

const state = {
  data: null,
  activeRinks: new Set(),
  view: "today",
  anchor: new Date(),
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

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function groupSessionsByDate(sessions, activeRinks) {
  const map = new Map();
  for (const session of sessions) {
    if (!activeRinks.has(session.rink)) continue;
    if (!map.has(session.date)) map.set(session.date, []);
    map.get(session.date).push(session);
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.startTime.localeCompare(b.startTime));
  }
  return map;
}

function renderLegend() {
  const el = document.getElementById("legend");
  el.innerHTML = Object.entries(SESSION_CLASSES)
    .map(([name, cls]) => `<span class="legend-item"><span class="dot ${cls}"></span>${escapeHtml(name)}</span>`)
    .join("");
}

function renderRinkFilters() {
  const container = document.getElementById("rink-filters");
  container.innerHTML = state.data.rinks
    .map((rink) => {
      const active = state.activeRinks.has(rink.name);
      const flagged = rink.status === "error" || rink.status === "stale";
      const title = flagged && rink.error ? ` title="${escapeHtml(rink.error)}"` : "";
      return `<button class="rink-chip${active ? " active" : ""}" data-rink="${escapeHtml(rink.name)}"${title}>${escapeHtml(rink.name)}${flagged ? " &#9888;" : ""}</button>`;
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
      renderCalendar();
    });
  });
}

function renderEvent(session) {
  const cls = SESSION_CLASSES[session.type] || "public";
  return `<div class="cal-event"><span class="dot ${cls}"></span>${formatClock(session.startTime)} <strong>${escapeHtml(session.rinkShort || session.rink)}</strong></div>`;
}

function renderDayCell(date, sessionsByDate, { muted } = {}) {
  const iso = toISODate(date);
  const todayIso = toISODate(new Date());
  const events = sessionsByDate.get(iso) || [];
  const classes = ["cal-cell"];
  if (muted) classes.push("muted");
  if (iso === todayIso) classes.push("today");
  const eventsHtml = events.map(renderEvent).join("");
  return `
    <div class="${classes.join(" ")}">
      <div class="cal-daynum">${date.getDate()}</div>
      <div class="cal-events">${eventsHtml}</div>
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

function renderTodayView(sessionsByDate) {
  const today = stripTime(new Date());
  const events = sessionsByDate.get(toISODate(today)) || [];
  const label = today.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  if (!events.length) {
    return `
      <div class="today-view">
        <p class="today-date">${label}</p>
        <p class="empty-state">No skating scheduled today. &#10052;&#65039;</p>
      </div>
    `;
  }

  const rows = events
    .map((session) => `
      <div class="today-row">
        <span class="today-time">
          <span class="dot ${SESSION_CLASSES[session.type] || "public"}"></span>
          ${formatClock(session.startTime)}&ndash;${formatClock(session.endTime)}
        </span>
        <span class="today-meta"><strong>${escapeHtml(session.rink)}</strong> &middot; ${escapeHtml(session.type)}</span>
      </div>
    `)
    .join("");

  return `<div class="today-view"><p class="today-date">${label}</p>${rows}</div>`;
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
  const sessionsByDate = groupSessionsByDate(state.data.sessions, state.activeRinks);
  if (state.view === "today") {
    container.innerHTML = renderTodayView(sessionsByDate);
  } else if (state.view === "week") {
    container.innerHTML = renderWeekView(sessionsByDate);
  } else {
    container.innerHTML = renderMonthView(sessionsByDate);
  }
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

  const when = formatTimestamp(data.generated_at);
  generatedAtEl.textContent = when ? `Last updated ${when}` : "";

  const attributionEl = document.getElementById("attribution");
  if (data.attribution && data.attribution.length) {
    attributionEl.textContent = data.attribution.join(" ");
  }

  renderLegend();
  renderRinkFilters();

  document.querySelectorAll(".tab").forEach((btn) => {
    if (btn.dataset.view === "today") btn.classList.add("active");
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
      if (state.view === "today") state.anchor = new Date();
      document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
      renderCalendar();
    });
  });

  document.getElementById("nav-prev").addEventListener("click", () => {
    state.anchor = state.view === "week" ? addDays(state.anchor, -7) : addMonths(state.anchor, -1);
    renderCalendar();
  });
  document.getElementById("nav-next").addEventListener("click", () => {
    state.anchor = state.view === "week" ? addDays(state.anchor, 7) : addMonths(state.anchor, 1);
    renderCalendar();
  });

  renderCalendar();
}

main();
