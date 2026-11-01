---
description: |
  [TOPIC] Mounted Writer editor
  [DETAILS] Diagnose project context, presence, preview controls, and deployed frontend behavior.
tags: [scitex-writer-mounted-editor]
---

# Mounted Writer editor

Use this note when diagnosing `/apps/writer/` or verifying its editor controls.
For the host capability contract and its historical migration slices, read
`docs/GUI_HOST_BOUNDARY.md` in the source checkout.

The host owns authentication, project authorization and storage. Writer's
`_django/_host_boundary.py` calls SDK `host.project_access`; the rendered
`.writer-app[data-project-id]` is that authorized selection. From 2.43.18,
`frontend/src/presence.ts` prefers this identity over a URL query because the
host can remember a picker selection in the session. A missing `?project=`
does not establish standalone mode. The mode is `data-app-mode`, populated
from the host's `SCITEX_APP_MODE` setting.

Collaboration currently polls the Hub presence heartbeat/active endpoints.
Verify their responses and the displayed users before claiming it works.
Presence does not establish real-time co-editing or inline comments. History
still displays an explicit future-integration placeholder.

The preview rail has PDF, Cite, Fig, Table, Collab and History. From 2.43.18,
PDF is active on first paint and Ctrl+wheel over Monaco changes the toolbar
font size through a capture listener. The shared theme control should update
Monaco immediately. Figure/table entries display supported thumbnails;
clicking an item must leave the manuscript unchanged. Insertion uses an
intentional drag into the editor. Verify changes in a disposable manuscript,
not an existing user's research text.

For a reproducible GUI check, identify the deployed leaf version, use a real
authorized example project, exercise the actual controls, and inspect a
screenshot. Source changes and passing Python view tests alone do not prove
that collected frontend assets are current. The relevant source is
`_django/frontend/src/index.ts`, `host-theme-fallback.ts`, `insert-panel.ts`,
and `_django/templates/writer/editor.html`.

Writer still owns its mounted `PDFViewer`. LivePaper's renderer, overlay and
comment ports are a separate provider surface; do not infer Writer/Journal
adoption from provider availability. Shared `example-project-mnist` claims
may be labeled demo/registered and are not evidence of scientific verification.
