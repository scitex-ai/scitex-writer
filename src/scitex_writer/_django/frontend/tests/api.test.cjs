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

function client(mode, token = "rendered-session-token") {
  const requests = [];
  const context = {
    exports: {},
    document: {
      querySelector(selector) {
        if (selector === ".writer-app") return { dataset: {
          appMode: mode, apiBase: "/plugin/writer/", projectDir: "/local/manuscript",
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
  assert.equal(requests[0].url, "/plugin/writer/api/file");
  assert.equal(requests[1].url, "/plugin/writer/api/claims/synthetic");
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
