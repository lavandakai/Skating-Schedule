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

function renderTable(table) {
  const days = table.days && table.days.length ? table.days : [];
  const rows = table.sessions
    .map((session) => {
      const cells = days
        .map((day) => `<td>${session.days[day] ? escapeHtml(session.days[day]) : ""}</td>`)
        .join("");
      return `<tr><th scope="row">${escapeHtml(session.name)}</th>${cells}</tr>`;
    })
    .join("");

  const headerCells = days.map((day) => `<th scope="col">${escapeHtml(day)}</th>`).join("");

  const caption = table.caption
    ? `<p class="table-caption">${escapeHtml(table.caption)}</p>`
    : "";

  return `
    ${caption}
    <table class="schedule">
      <thead><tr><th scope="col"></th>${headerCells}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
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
}

main();
