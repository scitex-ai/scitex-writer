# Writer standalone and plugin host boundary

The GUI requires the SDK 0.3.0 host/UI contract. The SDK used for this change
is an unpublished local candidate; do not assume a released install can satisfy
the new floor yet. Its tested peers are App 0.26.2 and UI 0.23.1. The SDK is a
base dependency so plugin discovery retains SDK metadata without an extra;
AppConfig import errors no longer substitute a plain Django base. Manifest
versions are derived from installed package metadata, not hard-coded JSON.

Standalone settings explicitly declare `SCITEX_APP_MODE = "standalone"`.
Local `working_dir` selection and `SCITEX_WRITER_WORKING_DIR` remain available.
The editor and viewer render a CSRF token; unsafe requests must send it as
`X-CSRFToken`. This also works with HTTP-only CSRF cookies and session storage.

A plugin host installs `WriterEditorConfig`, includes the leaf URLconf, and
declares `SCITEX_APP_MODE = "hub"`. It supplies authenticated `request.user`,
`SCITEX_PROJECT_PROVIDER` and `SCITEX_PROJECT_STORAGE` through the SDK contract.
Project identity comes from authorized `?project=` or the provider's stored
selection. Caller `working_dir` values and local environment defaults have no
authority in this mode. Every request checks permissions, including requests
that reuse cached editor state. Storage writes require literal `True` permission,
as enforced by the SDK. Invalid mode declarations fail with 503 before handlers.
Workspace symlinks must stay inside the authorized project. Loading host state
does not create or replace a Scholar library link.

The standard URLconf supplies its own mount and API base. A host retaining
separate page/API aliases can declare trusted view kwargs:

```python
path("writer/editor-v2/", editor_page, {
    "view_path": "editor-v2/", "api_base": "/writer/v2/",
})
path("writer/viewer-v2/", viewer_page, {
    "view_path": "viewer-v2/", "api_base": "/writer/v2/",
})
```

Existing nonstandard aliases still accept the host's API-base context processor
until it is replaced with explicit kwargs. Those values never come from HTTP
query input. Keep existing Hub wrappers/routes during review.

This boundary covers authenticated private project mounts. An anonymous public
live-paper viewer needs a separate host-authorized, read-only project capability;
the current SDK session project contract does not provide it. Do not activate
this candidate on the existing public viewer. Legacy section/Git/collaboration
APIs, initialization, host job queues, project-scoped provenance/store access,
external assets/library authorization and the host-specific picker still require
parity work before legacy routes can be removed. These changes do not sandbox
TeX compilation or certify scientific content.

Use `scitex_sdk.ui.mount` (or its direct UI aliases) for UI mount metadata;
`scitex_sdk.app.embed.mount_prefix` has a different contract. The SDK has no
`ui.scope` or `ui.context_processors` surface yet. Settings retain the existing
public scitex-ui context processor paths; do not replace them with private APIs.
