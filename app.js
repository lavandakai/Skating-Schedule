const DATA_URL = "data/schedule.json";

function formatTimestamp(isoString) {
  if (!isoString) return null;
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function renderStatusNote(rink) {
  if (rink.status === "ok") return "";
  if (rink.status === "stale") {
    const when = formatTimestamp(rink.scraped_at);
    return `<p class="status-note stale">&#9888; Couldn't refresh this schedule${
      when ? ` &mdash; showing the last successful copy from ${when}` : ""
    }.</p>`;
  }
  if (rink.status === "error") {
    return `<p class="status-note error">&#9888; Couldn't load a schedule for this rink yet. Check the source page directly.</p>`;
  }
  if (rink.status === "pending") {
    return `<p class="status-note pending">Waiting on the first scrape for this rink.</p>`;
  }
  return "";
}

const DAY_ABBREV = {
  Monday: "Mon", Tuesday: "Tue", Wednesday: "Wed", Thursday: "Thu",
  Friday: "Fri", Saturday: "Sat", Sunday: "Sun",
};

const SESSION_CLASSES = {
  "Public Skating": "public",
  "Family Skating": "family",
  "Adult Skating (18+)": "adult",
};

function renderTable(table) {
  const days = table.days && table.days.length ? table.days : [];

  const rows = table.sessions
    .map((session) => {
      const chips = days
        .filter((day) => session.days[day])
        .map((day) => `<span class="time-chip"><span class="day">${DAY_ABBREV[day] || day}</span>${escapeHtml(session.days[day])}</span>`)
        .join("");
      if (!chips) return "";
      const pillClass = SESSION_CLASSES[session.name] || "public";
      return `
        <div class="session-row">
          <span class="session-pill ${pillClass}">${escapeHtml(session.name)}</span>
          ${chips}
        </div>
      `;
    })
    .join("");

  const caption = table.caption
    ? `<p class="table-caption">${escapeHtml(table.caption)}</p>`
    : "";

  return `<div class="schedule-block">${caption}${rows}</div>`;
}

function renderCancellations(cancellations) {
  if (!cancellations || cancellations.length === 0) return "";
  const items = cancellations
    .map((entry) => {
      const notes = entry.notes && entry.notes.length
        ? `: ${entry.notes.map(escapeHtml).join("; ")}`
        : "";
      return `<li><span class="date">${escapeHtml(entry.date || "")}</span>${notes}</li>`;
    })
    .join("");
  return `
    <div class="cancellations">
      <h3>Schedule changes</h3>
      <ul>${items}</ul>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderRink(rink) {
  const tablesHtml = rink.tables && rink.tables.length
    ? rink.tables.map(renderTable).join("")
    : `<p class="empty-state">No schedule available.</p>`;

  return `
    <section class="rink-card">
      <h2><a href="${rink.url}" target="_blank" rel="noopener">${escapeHtml(rink.name)}</a></h2>
      ${renderStatusNote(rink)}
      ${tablesHtml}
      ${renderCancellations(rink.cancellations)}
    </section>
  `;
}

async function main() {
  const container = document.getElementById("rinks");
  const generatedAtEl = document.getElementById("generated-at");

  let data;
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    data = await response.json();
  } catch (err) {
    container.innerHTML = `<p class="empty-state">Couldn't load schedule data.</p>`;
    return;
  }

  const when = formatTimestamp(data.generated_at);
  generatedAtEl.textContent = when ? `Last updated ${when}` : "";

  container.innerHTML = data.rinks.map(renderRink).join("");

  const attributionEl = document.getElementById("attribution");
  if (data.attribution && data.attribution.length) {
    attributionEl.textContent = data.attribution.join(" ");
  }
}

main();
