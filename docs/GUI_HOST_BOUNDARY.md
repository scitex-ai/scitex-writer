# Writer standalone and plugin host boundary

The GUI requires the consolidated SDK 0.3.0 contract. The SDK physically owns
`scitex_sdk.app` and `scitex_sdk.ui`, their Django registrations and the resources
under `scitex_sdk/app/` and `scitex_sdk/ui/`. Writer requires the SDK directly and
has no App/UI distribution dependency. This candidate remains held until the
actual consolidated core wheel passes its installed-consumer checks. Manifest
versions come from installed metadata, not hard-coded JSON.

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
this candidate on the existing public viewer. Legacy section management/Git/collaboration
APIs, initialization, host job queues, project-scoped provenance/store access,
external assets/library authorization and the host-specific picker still require
parity work before legacy routes can be removed. These changes do not sandbox
TeX compilation or certify scientific content.

Use `scitex_sdk.ui.mount` (or its direct UI aliases) for UI mount metadata;
`scitex_sdk.app.embed.mount_prefix` has a different contract. The SDK has no
`ui.scope` or `ui.context_processors` surface yet. Settings use the canonical SDK UI context processor paths.

## Numeric section and readiness compatibility

The leaf now handles the existing HTTP paths
`api/project/<id>/section/<section>/` (GET/POST) and
`api/project/<id>/manuscript-status/` (GET), including their existing URL names
`api_section` and `api_manuscript_status` under the leaf's `writer` namespace.
The host's legacy `writer_app` reverse namespace is not yet supplied. Existing
legacy routes must remain until that namespace and all operation parity gates
are closed; adding these leaf routes does not activate a Hub cutover.

In plugin mode, the numeric URL ID is passed as an explicit selector to the
SDK through a shallow request adapter. Authentication, the original session,
project provider and storage permissions remain the host's. A conflicting
`?project=` is refused before resolution; the path does not authorize a project
or fall back to the stored choice. CSRF runs before unsafe selection. Every
save rechecks literal-True storage write permission. Caller working directories
and body project IDs do not redirect mounted requests.

Standalone keeps the existing explicit local `working_dir`/environment
selection; the URL number has no local database mapping. This remains a trusted
single-user local interface, not multi-user storage authorization.

Section reads observe the existing workspace without attaching Writer,
scaffolding templates, linking Scholar, executing a job or compiling TeX. The
three document directories required by Writer's attach contract establish
`workspace_ready`. An absent/incomplete workspace returns renderable empty
content with `workspace_ready: false`; writes return 409. A missing section in
a ready workspace returns empty content and `missing: true`, while a written
empty file returns `missing: false`. Actual filesystem/text read failures stay
errors. All section paths remain within the authorized workspace.

Readiness depends on the storage capability supplying an authorized root. The
current Hub provider returns no root when the project directory is absent, and
the SDK then refuses the request with 404 before these views run. Empty unready
content is proven for an existing root or an explicit authorized expected-root
capability; full parity for a registered project with no directory remains open.
The leaf does not guess a path, bypass this refusal or create the directory.

Manuscript status retains `success`, `exists` and `has_pdf`, observing the
existing `.preview`, document-PDF and `preview_output` locations. It does not
create or compile a PDF. Invalid names and outbound PDF links are never reported
as available. The manuscript-directory presence flag matches the existing Hub
status contract; it is distinct from complete section workspace readiness.

POST persists the section file and its content response. It does not yet
reproduce the legacy service's automatic Git commit/history side effect.
Virtual `compiled_tex`/`compiled_pdf` sections explicitly return 501. Section
create/delete/move/exclude, initialization, batch save, Git, host jobs,
collaboration and public viewer capabilities remain separate migration gates.
The unchanged legacy TypeScript client hardcodes the default mount, so its
custom-prefix routing is not claimed. Templates and compiled frontend assets
are unchanged by this bounded compatibility patch.


The standalone UI registration is `scitex_sdk.ui`; Writer keeps its own
`writer_editor` Django label and `writer` URL namespace. Shared template slots
and DOM identifiers retain their existing names. Numeric URL selectors require
matching host-authorized project IDs. Current Hub lists `owner/slug` keys and
does not map an integer PK to that key; SDK 404 refusal remains an open generic
identity contract, separate from the already documented absent-root refusal.
