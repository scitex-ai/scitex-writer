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


// Real module source is transpiled; these fixtures bound host DOM/fetch only.
// They do not establish browser focus, image decoding, live routes or producer provenance.
const insertSource = fs.readFileSync(path.join(__dirname, "../src/insert-panel.ts"), "utf8");
const insertCompiled = ts.transpileModule(insertSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function decodeHtmlAttribute(value) {
  return value.replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

function classListFixture() {
  const classes = new Set();
  return {
    add(value) { classes.add(value); },
    remove(value) { classes.delete(value); },
    toggle(value, enabled) { if (enabled) classes.add(value); else classes.delete(value); },
  };
}

function insertClient(mode, kind) {
  const apiBase = "/science/custom/writer/v2/";
  const alphaDirectory = "/local/alpha manuscript & inputs";
  const betaDirectory = "/local/beta manuscript";
  const root = { dataset: {
    appMode: mode, apiBase, projectDir: alphaDirectory, projectId: "17",
  } };
  const requests = [];
  const insertions = [];
  const mediaPath = `01_manuscript/contents/${kind}/caption_and_media/01 result & proof.${kind === "figures" ? "png" : "csv"}`;
  // This is the actual media.py wire schema; quote() preserves '/' separators.
  const encodedPath = mediaPath.split("/").map(encodeURIComponent).join("/");
  const label = kind === "figures" ? "fig:nonempty" : "tab:nonempty";
  const entry = {
    name: "01 result & proof",
    path: `01_manuscript/contents/${kind}/caption_and_media/01 result & proof.tex`,
    label, insert: `\\ref{${label}}`, media_path: mediaPath,
    media_ext: kind === "figures" ? ".png" : ".csv",
    thumbnail_url: `/api/thumbnail?kind=${kind}&path=${encodedPath}`,
  };
  const apiContext = {
    exports: {}, URLSearchParams,
    document: { querySelector(selector) {
      if (selector === ".writer-app") return root;
      return null;
    } },
    async fetch(url, options) {
      requests.push({ url, options });
      const parsed = new URL(url, "http://testserver");
      if (parsed.pathname !== `${apiBase}api/${kind}`) {
        throw new Error(`Unexpected media-list URL: ${parsed.pathname}`);
      }
      return { ok: true, async json() {
        return { doc_type: "manuscript", [kind]: [entry] };
      } };
    },
  };
  vm.runInNewContext(compiled, apiContext);
  const insertContext = {
    exports: {},
    require(name) {
      if (name === "./api") return apiContext.exports;
      if (name === "./citations-panel") return { CitationsPanel: class {
        constructor() { throw new Error("CitationsPanel is outside this media control"); }
      } };
      throw new Error(`Unexpected InsertPanel dependency: ${name}`);
    },
  };
  vm.runInNewContext(insertCompiled, insertContext);
  const items = [];
  let markup = "";
  const panel = {
    classList: classListFixture(),
    get innerHTML() { return markup; },
    set innerHTML(value) {
      markup = value;
      items.length = 0;
      // Observe literal attributes emitted by the real renderList, not invented insert HTML.
      const pattern = /<div class="insert-item[^"]*"\s+data-index="([^"]*)"\s+data-insert="([^"]*)">/g;
      for (const match of value.matchAll(pattern)) {
        const listeners = new Map();
        items.push({
          dataset: { index: match[1], insert: decodeHtmlAttribute(match[2]) },
          addEventListener(type, listener) { listeners.set(type, listener); },
          click() {
            const listener = listeners.get("click");
            if (!listener) throw new Error("Real media item has no click listener");
            listener();
          },
        });
      }
    },
    querySelectorAll(selector) {
      if (selector !== ".insert-item") throw new Error(`Unexpected panel selector: ${selector}`);
      return items;
    },
  };
  const buttons = ["fig", "table"].map(pane => ({
    dataset: { pane }, classList: classListFixture(), addEventListener() {},
  }));
  const bar = { querySelectorAll(selector) {
    if (selector !== "[data-pane]") throw new Error(`Unexpected bar selector: ${selector}`);
    return buttons;
  } };
  const controller = new insertContext.exports.InsertPanel({
    bar, panel, getDocType: () => "manuscript",
    insertAtCursor(snippet) { insertions.push(snippet); },
  });
  return { root, requests, insertions, panel, items, controller, entry,
    apiBase, alphaDirectory, betaDirectory, mediaPath, encodedPath };
}

for (const mode of ["hub", "standalone"]) {
  for (const kind of ["figures", "tables"]) {
    test(`nonempty ${kind} InsertPanel retains ${mode} mount and Alpha resource identity`, { timeout: 2_000 }, async () => {
      // Arrange: modules capture Alpha before another navigation changes the root data.
      const fixture = insertClient(mode, kind);
      fixture.root.dataset.projectId = "21";
      fixture.root.dataset.projectDir = fixture.betaDirectory;
      const selector = mode === "hub"
        ? "project=17"
        : `working_dir=${encodeURIComponent(fixture.alphaDirectory)}`;
      const expectedList = `${fixture.apiBase}api/${kind}?doc_type=manuscript&${selector}`;
      const expectedImage = `${fixture.apiBase}api/thumbnail?kind=${kind}&path=${fixture.encodedPath}&${selector}`;
      // Act: real public pane opening executes real renderFig/renderTable and renderList.
      fixture.controller.open(kind === "figures" ? "fig" : "table");
      await new Promise(resolve => setImmediate(resolve));
      const image = fixture.panel.innerHTML.match(/<img class="insert-item-thumb" src="([^"]+)"/);
      if (!image) throw new Error(`Real nonempty ${kind} render produced no thumbnail: ${fixture.panel.innerHTML}`);
      const actualImage = decodeHtmlAttribute(image[1]);
      fixture.items[0].click();
      // Assert: rendered URL, list identity and actual registered insertion callback are observed together.
      assert.deepEqual({
        listUrls: fixture.requests.map(request => request.url),
        imageUrl: actualImage,
        decodedMediaPath: new URL(actualImage, "http://testserver").searchParams.get("path"),
        insertions: fixture.insertions,
      }, {
        listUrls: [expectedList], imageUrl: expectedImage,
        decodedMediaPath: fixture.mediaPath, insertions: [fixture.entry.insert],
      });
    });
  }
}
