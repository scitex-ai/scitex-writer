/**
 * Shared claims-list module — Living Paper (#133).
 *
 * Renders claim cards with verification badges and DAG click-through, used
 * by both the editor's Claims tab and the read-only viewer. Keeps the two
 * views visually and behaviourally consistent.
 */
import { resourceUrl, apiGet } from "./api";

export interface ClaimRow {
  claim_id: string;
  type: string;
  context?: string;
  preview_nature?: string;
  has_provenance?: boolean;
  verification?: { state: string; error?: string };
}

export interface ClaimsMetadataResponse {
  success: boolean;
  count: number;
  claims: ClaimRow[];
}

interface DagResponse {
  success: boolean;
  mermaid?: string;
  error?: string;
}

export async function loadClaims(): Promise<ClaimRow[]> {
  try {
    const response = await apiGet<ClaimsMetadataResponse>(
      "api/claims-metadata",
    );
    return response.claims || [];
  } catch (err) {
    console.error("[claims-list] loadClaims failed", err);
    return [];
  }
}

export function verificationBadge(claim: ClaimRow): string {
  const state = claim.verification?.state || "UNKNOWN";
  return `<span class="claim-badge badge-${state.toLowerCase()}" title="Verification state">${escapeHtml(state)}</span>`;
}

export function renderClaimDetails(claim: ClaimRow): string {
  const rows: Array<[string, string]> = [
    ["Type", claim.type],
    ["Context", claim.context || "—"],
    ["Preview", claim.preview_nature || "—"],
    ["State", claim.verification?.state || "UNKNOWN"],
  ];
  if (claim.verification?.error) {
    rows.push(["Error", claim.verification.error]);
  }
  return rows
    .map(
      ([label, value]) => `
      <div class="claim-detail-row">
        <div class="claim-detail-label">${escapeHtml(label)}</div>
        <div class="claim-detail-value">${escapeHtml(value)}</div>
      </div>`,
    )
    .join("");
}

export function renderClaimsList(
  container: HTMLElement,
  claims: ClaimRow[],
  onSelect: (claim: ClaimRow, row: HTMLElement) => void,
): void {
  if (claims.length === 0) {
    container.innerHTML = `<p class="insert-panel-empty">No claims registered.</p>`;
    return;
  }
  container.innerHTML = claims
    .map(
      (claim) => `
      <div class="claim-row" data-claim-id="${escapeAttr(claim.claim_id)}">
        <div class="claim-row-header">
          <span class="claim-row-id"><code>${escapeHtml(claim.claim_id)}</code></span>
          ${verificationBadge(claim)}
        </div>
        <div class="claim-row-preview">${escapeHtml(claim.preview_nature || "")}</div>
        <div class="claim-row-context">${escapeHtml(claim.context || "")}</div>
        <button class="btn btn-secondary btn-sm claim-row-dag"
                title="Show verification DAG">
          <i class="fas fa-project-diagram"></i> DAG
        </button>
      </div>`,
    )
    .join("");
  container.querySelectorAll<HTMLElement>(".claim-row").forEach((row) => {
    const id = row.dataset.claimId;
    if (!id) return;
    const claim = claims.find((c) => c.claim_id === id);
    if (!claim) return;
    row.addEventListener("click", () => onSelect(claim, row));
    row
      .querySelector<HTMLElement>(".claim-row-dag")
      ?.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelect(claim, row);
      });
  });
}

/**
 * Load a mermaid DAG for a claim and render it into `container`.
 *
 * Falls back to `<pre>`-formatted mermaid source when the mermaid library
 * isn't loaded (keeps the viewer usable without the CDN dependency).
 */
export async function renderDagFor(
  claim: ClaimRow,
  container: HTMLElement,
): Promise<void> {
  container.innerHTML = `<p class="insert-panel-empty">Loading DAG…</p>`;
  const url =
    resourceUrl(`api/dag?claim=${encodeURIComponent(claim.claim_id)}`);
  try {
    const response = await fetch(url);
    const data = (await response.json()) as DagResponse;
    if (!data.success || !data.mermaid) {
      container.innerHTML = `<p class="insert-panel-error">${escapeHtml(data.error || "No DAG available.")}</p>`;
      return;
    }
    const mermaid = (
      window as Window & {
        mermaid?: {
          render: (
            id: string,
            code: string,
          ) => Promise<{ svg: string; bindFunctions?: (el: Element) => void }>;
        };
      }
    ).mermaid;
    if (!mermaid) {
      container.innerHTML = `<pre class="claim-dag-raw">${escapeHtml(data.mermaid)}</pre>`;
      return;
    }
    const { svg } = await mermaid.render(`dag-${Date.now()}`, data.mermaid);
    container.innerHTML = svg;
  } catch (err) {
    container.innerHTML = `<p class="insert-panel-error">DAG load failed: ${escapeHtml(String(err))}</p>`;
  }
}

function escapeHtml(text: string): string {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(text: string): string {
  return escapeHtml(text).replace(/'/g, "&#39;");
}
