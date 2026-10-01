const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const source = fs.readFileSync(path.join(__dirname, "../src/api.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function client(mode, token = "rendered-session-token", projectId = "alice/alpha", apiBase = "/plugin/writer/") {
  const requests = [];
  const context = {
    exports: {},
    URLSearchParams,
    document: {
      querySelector(selector) {
        if (selector === ".writer-app") return { dataset: {
          appMode: mode, apiBase, projectDir: "/local/manuscript", projectId,
        } };
        if (selector === 'meta[name="writer-csrf-token"]' && token) return { content: token };
        return null;
      },
    },
    async fetch(url, options) {
      requests.push({ url, options });
      return { ok: true, async json() { return { success: true }; } };
    },
  };
  vm.runInNewContext(compiled, context);
  return { api: context.exports, requests };
}

test("plugin writes send session CSRF and use the declared mount without working_dir", async () => {
  const { api, requests } = client("hub");
  await api.saveFile("synthetic.tex", "Synthetic content");
  await api.apiDelete("api/claims/synthetic");
  assert.equal(requests[0].url, "/plugin/writer/api/file?project=alice%2Falpha");
  assert.equal(requests[1].url, "/plugin/writer/api/claims/synthetic?project=alice%2Falpha");
  assert.equal(requests[0].options.headers["X-CSRFToken"], "rendered-session-token");
  assert.equal(requests[1].options.headers["X-CSRFToken"], "rendered-session-token");
  assert.equal(requests[0].options.credentials, "same-origin");
  assert.equal(requests[1].options.method, "DELETE");
});

test("standalone retains local directory selection and sends CSRF", async () => {
  const { api, requests } = client("standalone");
  await api.getFile("synthetic.tex");
  await api.saveFile("synthetic.tex", "Synthetic content");
  assert.equal(new URL(requests[0].url, "http://localhost").searchParams.get("working_dir"), "/local/manuscript");
  assert.equal(new URL(requests[1].url, "http://localhost").searchParams.get("working_dir"), "/local/manuscript");
  assert.equal(requests[1].options.headers["X-CSRFToken"], "rendered-session-token");
});

test("a missing page token refuses a write before fetch", async () => {
  const { api, requests } = client("hub", "");
  await assert.rejects(api.saveFile("synthetic.tex", "X"), /CSRF token missing/);
  await assert.rejects(api.apiDelete("api/claims/synthetic"), /CSRF token missing/);
  assert.equal(requests.length, 0);
});


test("resources keep the rendered canonical identity independent of later navigation", async () => {
  const { api, requests } = client("hub");
  await api.projectInfo();
  await api.getFile("abstract.tex");
  for (const request of requests) {
    const url = new URL(request.url, "http://localhost");
    assert.equal(url.searchParams.get("project"), "alice/alpha");
    assert.equal(url.searchParams.has("working_dir"), false);
  }
});

test("missing page identity refuses generic reads and writes before fetch", async () => {
  const { api, requests } = client("hub", "rendered-session-token", "");
  await assert.rejects(api.projectInfo(), /project identity missing/);
  await assert.rejects(api.saveFile("abstract.tex", "X"), /project identity missing/);
  assert.equal(requests.length, 0);
});

test("conflicting selectors cannot replace a rendered page project", async () => {
  const { api, requests } = client("hub");
  await assert.rejects(api.apiGet("api/file?project=bob/beta"), /conflicts/);
  await assert.rejects(api.apiGet("api/file?project=alice/alpha&project=bob/beta"), /conflicts/);
  assert.equal(requests.length, 0);
});

test("numeric compatibility paths retain explicit URL selectors without a conflicting page query", async () => {
  const { api, requests } = client("hub");
  await api.apiGet("api/project/17/section/abstract/");
  await api.apiGet("api/project/17/manuscript-status/");
  assert.equal(requests[0].url, "/plugin/writer/api/project/17/section/abstract/");
  assert.equal(requests[1].url, "/plugin/writer/api/project/17/manuscript-status/");
});


test("PDF, DAG and downloads retain the declared custom prefix and canonical project", () => {
  const { api } = client("hub", "rendered-session-token", "alice/alpha", "/nested/custom/writer/");
  for (const endpoint of ["api/pdf?doc_type=manuscript", "api/dag?claim=synthetic", "api/pdf?download=1"]) {
    const url = new URL(api.resourceUrl(endpoint), "http://localhost");
    assert.ok(url.pathname.startsWith("/nested/custom/writer/api/"));
    assert.equal(url.searchParams.get("project"), "alice/alpha");
    assert.equal(url.searchParams.has("working_dir"), false);
  }
});
