/* Writer collab-pane presence client (slice 1, operator 2026-10-24).
 *
 * Hub-mounted mode only: heartbeats the Hub session backend
 * (/apps/writer/collaboration/presence/*) and renders who is here.
 * Standalone never calls this module — it keeps the push-to-Hub pointer.
 *
 * Polling, not WebSocket, mirroring the Hub WriterPresence model (active =
 * heartbeat within minutes). No fake presence: fetch failures render an
 * "unavailable" note, never invented names. The loop is generation-gated:
 * every rail switch bumps the epoch via stopPresence(), so a stale loop
 * from a previous collab visit can never paint over the new view.
 */

const HEARTBEAT_MS = 25000;
const HEARTBEAT_PATH = "/apps/writer/collaboration/presence/heartbeat/";
const ACTIVE_PATH = "/apps/writer/collaboration/presence/active/";

let epoch = 0;

export function stopPresence(): void {
  epoch++;
}

/** Hub project ref from the page URL (?project=owner/slug). Null when the
 *  page carries no Hub project identity — heartbeat is then impossible. */
export function projectRefFromLocation(): string | null {
  const ref = new URLSearchParams(location.search).get("project");
  return ref && ref.includes("/") ? ref : null;
}

function csrfFromCookie(): string {
  const hit = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith("csrftoken="));
  return hit ? decodeURIComponent(hit.slice("csrftoken=".length)) : "";
}

interface ActiveUser {
  username: string;
  section: string;
}

function renderUsers(panel: HTMLElement, users: ActiveUser[]): void {
  const names = users
    .map(
      (u) =>
        `<li><span class="presence-user">${escapeHtml(u.username)}</span>${
          u.section
            ? ` <span class="presence-section">${escapeHtml(u.section)}</span>`
            : ""
        }</li>`,
    )
    .join("");
  const list = panel.querySelector<HTMLElement>("[data-presence-list]");
  if (list) {
    list.innerHTML =
      names ||
      `<li class="insert-panel-empty">Only you here right now.</li>`;
  }
  const count = panel.querySelector<HTMLElement>("[data-presence-count]");
  if (count) count.textContent = users.length ? ` (${users.length})` : "";
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

/** Start heartbeating + rendering into the collab panel body. The panel
 *  must contain [data-presence-list] and [data-presence-count] slots. */
export function startPresence(
  panel: HTMLElement,
  projectRef: string,
  section: string,
): void {
  const my = ++epoch;
  const beat = async (): Promise<void> => {
    if (my !== epoch) return;
    try {
      const token = csrfFromCookie();
      const hb = await fetch(HEARTBEAT_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "X-CSRFToken": token } : {}),
        },
        body: JSON.stringify({ project: projectRef, section }),
      });
      if (!hb.ok) throw new Error(`heartbeat ${hb.status}`);
      const res = await fetch(
        `${ACTIVE_PATH}?project=${encodeURIComponent(projectRef)}`,
        { credentials: "same-origin" },
      );
      if (!res.ok) throw new Error(`active ${res.status}`);
      const data = (await res.json()) as {
        success: boolean;
        users: ActiveUser[];
      };
      if (my === epoch && data.success) renderUsers(panel, data.users);
    } catch {
      if (my !== epoch) return;
      const list = panel.querySelector<HTMLElement>("[data-presence-list]");
      if (list && !list.hasChildNodes()) {
        list.innerHTML = `<li class="insert-panel-empty">Presence unavailable — Hub session backend unreachable.</li>`;
      }
    }
    if (my === epoch) window.setTimeout(beat, HEARTBEAT_MS);
  };
  void beat();
}
