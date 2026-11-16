(function() {
'use strict';
const API_BASE = (document.body && document.body.dataset.apiBase) || '/';


// ===== State =====
const state = {
    editor: null,
    openTabs: [],
    activeTab: null,
    pdfDoc: null,
    pdfPage: 1,
    pdfScale: 0,
    compiling: false,
    pollTimer: null
};

// ===== Init =====
document.addEventListener('DOMContentLoaded', function() {
    loadFileTree();
    loadBibEntries();
    setupResizers();
    setupToolbar();
    setupKeyboard();
    setupPreviewTabs();
    loadClaims();
    initClaims();
});

// ===== File Tree =====
function loadFileTree() {
    fetch(API_BASE + 'api/files')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            renderFileTree(data.tree, document.getElementById('file-tree'), 0);
        })
        .catch(function() {
            document.getElementById('file-tree').innerHTML =
                '<div class="loading">Error loading files</div>';
        });
}

function renderFileTree(items, container, depth) {
    container.innerHTML = '';
    items.forEach(function(item) {
        if (item.type === 'directory') {
            var dirEl = document.createElement('div');
            dirEl.className = 'tree-dir';

            var toggle = document.createElement('div');
            toggle.className = 'tree-item';
            toggle.setAttribute('data-depth', depth);
            toggle.innerHTML = '<span class="icon">&#9654;</span>' +
                '<span class="name">' + escapeHtml(item.name) + '</span>';

            var children = document.createElement('div');
            children.className = 'tree-children';

            toggle.addEventListener('click', (function(ch, tg) {
                return function() {
                    var isOpen = ch.classList.toggle('open');
                    tg.querySelector('.icon').innerHTML = isOpen ? '&#9660;' : '&#9654;';
                };
            })(children, toggle));

            if (depth === 0) {
                children.classList.add('open');
                toggle.querySelector('.icon').innerHTML = '&#9660;';
            }

            dirEl.appendChild(toggle);
            dirEl.appendChild(children);
            container.appendChild(dirEl);
            renderFileTree(item.children || [], children, depth + 1);
        } else {
            var fileEl = document.createElement('div');
            fileEl.className = 'tree-item';
            fileEl.setAttribute('data-depth', depth);
            fileEl.setAttribute('data-path', item.path);
            fileEl.innerHTML = '<span class="icon">' + getFileIcon(item.extension) +
                '</span><span class="name">' + escapeHtml(item.name) + '</span>';
            fileEl.addEventListener('click', (function(p, n) {
                return function() { openFile(p, n); };
            })(item.path, item.name));
            container.appendChild(fileEl);
        }
    });
}

function getFileIcon(ext) {
    var icons = {
        '.tex': '&#120029;', '.bib': '&#128218;', '.sty': '&#9881;',
        '.cls': '&#9881;', '.pdf': '&#128196;', '.png': '&#128247;',
        '.jpg': '&#128247;', '.svg': '&#128247;', '.csv': '&#128202;',
        '.yaml': '&#9881;', '.yml': '&#9881;', '.md': '&#128221;',
        '.txt': '&#128196;', '.py': '&#128013;', '.sh': '&#9881;'
    };
    return icons[ext] || '&#128196;';
}

// ===== File Open/Save =====
function openFile(path, name) {
    var existingIdx = -1;
    for (var i = 0; i < state.openTabs.length; i++) {
        if (state.openTabs[i].path === path) { existingIdx = i; break; }
    }
    if (existingIdx >= 0) { switchTab(existingIdx); return; }

    fetch(API_BASE + 'api/file?path=' + encodeURIComponent(path))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) { alert(data.error); return; }
            state.openTabs.push({
                path: data.path, name: data.name,
                content: data.content, original: data.content, modified: false
            });
            switchTab(state.openTabs.length - 1);
            renderTabs();
        });
}

function switchTab(idx) {
    if (idx < 0 || idx >= state.openTabs.length) return;

    if (state.activeTab !== null && state.editor && state.openTabs[state.activeTab]) {
        state.openTabs[state.activeTab].content = state.editor.getValue();
    }

    state.activeTab = idx;
    var tab = state.openTabs[idx];

    document.querySelectorAll('.tree-item.active').forEach(function(el) {
        el.classList.remove('active');
    });
    var treeItem = document.querySelector('.tree-item[data-path="' + tab.path + '"]');
    if (treeItem) treeItem.classList.add('active');

    document.getElementById('current-file').textContent = tab.path;

    var welcomeMsg = document.getElementById('welcome-message');
    if (welcomeMsg) welcomeMsg.style.display = 'none';

    if (!state.editor) {
        state.editor = CodeMirror(document.getElementById('editor-container'), {
            value: tab.content,
            mode: getMode(tab.name),
            lineNumbers: true,
            lineWrapping: true,
            matchBrackets: true,
            autoCloseBrackets: true,
            foldGutter: true,
            gutters: ['CodeMirror-linenumbers', 'CodeMirror-foldgutter'],
            indentUnit: 4, tabSize: 4, indentWithTabs: false,
            extraKeys: {
                'Ctrl-S': function() { saveCurrentFile(); },
                'Cmd-S': function() { saveCurrentFile(); },
                'Tab': function(cm) {
                    if (cm.somethingSelected()) cm.indentSelection('add');
                    else cm.replaceSelection('    ', 'end');
                }
            }
        });
        state.editor.on('change', function() {
            if (state.activeTab !== null) {
                var t = state.openTabs[state.activeTab];
                t.content = state.editor.getValue();
                var wasModified = t.modified;
                t.modified = (t.content !== t.original);
                if (wasModified !== t.modified) renderTabs();
            }
        });
    } else {
        state.editor.setValue(tab.content);
        state.editor.setOption('mode', getMode(tab.name));
        state.editor.clearHistory();
    }
    state.editor.refresh();
    renderTabs();
}

function getMode(filename) {
    if (/\.(tex|sty|cls|bib)$/.test(filename)) return 'stex';
    return 'text/plain';
}

function closeTab(idx, event) {
    if (event) { event.stopPropagation(); event.preventDefault(); }
    var tab = state.openTabs[idx];
    if (tab.modified && !confirm('Unsaved changes in ' + tab.name + '. Discard?')) return;

    state.openTabs.splice(idx, 1);

    if (state.openTabs.length === 0) {
        state.activeTab = null;
        if (state.editor) {
            state.editor.toTextArea();
            state.editor = null;
            var ta = document.querySelector('#editor-container textarea');
            if (ta) ta.remove();
        }
        document.getElementById('current-file').textContent = 'No file open';
        var wm = document.getElementById('welcome-message');
        if (wm) wm.style.display = '';
        document.querySelectorAll('.tree-item.active').forEach(function(el) {
            el.classList.remove('active');
        });
    } else if (state.activeTab >= state.openTabs.length) {
        switchTab(state.openTabs.length - 1);
    } else if (state.activeTab === idx) {
        switchTab(Math.min(idx, state.openTabs.length - 1));
    } else if (state.activeTab > idx) {
        state.activeTab--;
    }
    renderTabs();
}

function saveCurrentFile() {
    if (state.activeTab === null || !state.editor) return;
    var tab = state.openTabs[state.activeTab];
    tab.content = state.editor.getValue();

    var statusEl = document.getElementById('save-status');
    statusEl.textContent = 'Saving...';
    statusEl.className = 'save-status saving';

    fetch(API_BASE + 'api/file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: tab.path, content: tab.content })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            tab.original = tab.content;
            tab.modified = false;
            statusEl.textContent = 'Saved';
            statusEl.className = 'save-status saved';
            renderTabs();
            setTimeout(function() {
                statusEl.textContent = '';
                statusEl.className = 'save-status';
            }, 2000);
        } else {
            statusEl.textContent = 'Error: ' + (data.error || 'Unknown');
            statusEl.className = 'save-status error';
        }
    })
    .catch(function() {
        statusEl.textContent = 'Save failed';
        statusEl.className = 'save-status error';
    });
}

// ===== Tabs Rendering =====
function renderTabs() {
    var container = document.getElementById('file-tabs');
    container.innerHTML = '';
    state.openTabs.forEach(function(tab, idx) {
        var tabEl = document.createElement('div');
        tabEl.className = 'file-tab' +
            (idx === state.activeTab ? ' active' : '') +
            (tab.modified ? ' modified' : '');
        tabEl.innerHTML = '<span class="tab-name">' + escapeHtml(tab.name) +
            '</span><span class="tab-close">&times;</span>';
        tabEl.addEventListener('click', function() { switchTab(idx); });
        tabEl.querySelector('.tab-close').addEventListener('click', function(e) {
            closeTab(idx, e);
        });
        container.appendChild(tabEl);
    });
}

// ===== Utilities =====
function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ===== Compilation =====
function startCompile() {
    if (state.compiling) return;

    // Save current file first
    if (state.activeTab !== null && state.editor) {
        var tab = state.openTabs[state.activeTab];
        tab.content = state.editor.getValue();
        if (tab.modified) {
            fetch(API_BASE + 'api/file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: tab.path, content: tab.content })
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (data.success) {
                    tab.original = tab.content;
                    tab.modified = false;
                    renderTabs();
                }
            });
        }
    }

    var docType = document.getElementById('doc-type-select').value;
    state.compiling = true;
    document.body.classList.add('compiling');
    document.getElementById('btn-compile').disabled = true;
    document.getElementById('log-content').textContent = 'Starting compilation...\n';
    document.getElementById('log-panel').style.display = '';

    fetch(API_BASE + 'api/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_type: docType })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) {
            document.getElementById('log-content').textContent += 'Error: ' + data.error + '\n';
            state.compiling = false;
            document.body.classList.remove('compiling');
            document.getElementById('btn-compile').disabled = false;
            return;
        }
        pollCompilation();
    })
    .catch(function(err) {
        document.getElementById('log-content').textContent +=
            'Request failed: ' + err + '\n';
        state.compiling = false;
        document.body.classList.remove('compiling');
        document.getElementById('btn-compile').disabled = false;
    });
}

function pollCompilation() {
    state.pollTimer = setInterval(function() {
        fetch(API_BASE + 'api/compile/status')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.log) {
                    document.getElementById('log-content').textContent = data.log;
                }
                if (!data.compiling) {
                    clearInterval(state.pollTimer);
                    state.compiling = false;
                    document.body.classList.remove('compiling');
                    document.getElementById('btn-compile').disabled = false;
                    if (data.result && data.result.success) {
                        document.getElementById('log-content').textContent +=
                            '\n\nCompilation successful!';
                        loadPdf();
                    } else {
                        var err = data.result ?
                            (data.result.error || 'Unknown error') : 'Unknown error';
                        document.getElementById('log-content').textContent +=
                            '\n\nCompilation failed: ' + err;
                    }
                }
            });
    }, 1000);
}

// ===== PDF Viewer =====
function loadPdf() {
    var docType = document.getElementById('doc-type-select').value;
    var url = API_BASE + 'api/pdf?doc_type=' + docType + '&t=' + Date.now();

    pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    pdfjsLib.getDocument(url).promise
        .then(function(pdf) {
            state.pdfDoc = pdf;
            state.pdfPage = 1;
            document.getElementById('pdf-placeholder').style.display = 'none';
            document.getElementById('pdf-canvas').style.display = '';
            document.getElementById('pdf-controls').style.display = '';
            renderPdfPage();
        })
        .catch(function(err) {
            document.getElementById('pdf-placeholder').innerHTML =
                '<p>Failed to load PDF</p><p class="hint">' +
                escapeHtml(String(err)) + '</p>';
            document.getElementById('pdf-placeholder').style.display = '';
        });
}

function renderPdfPage() {
    if (!state.pdfDoc) return;
    state.pdfDoc.getPage(state.pdfPage).then(function(page) {
        var canvas = document.getElementById('pdf-canvas');
        var ctx = canvas.getContext('2d');

        var container = document.getElementById('pdf-container');
        var containerWidth = container.clientWidth - 32;
        var unscaledViewport = page.getViewport({ scale: 1.0 });
        var fitScale = containerWidth / unscaledViewport.width;

        var scale = state.pdfScale === 0 ? fitScale : state.pdfScale;
        var viewport = page.getViewport({ scale: scale });

        var dpr = window.devicePixelRatio || 1;
        canvas.width = viewport.width * dpr;
        canvas.height = viewport.height * dpr;
        canvas.style.width = viewport.width + 'px';
        canvas.style.height = viewport.height + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        page.render({ canvasContext: ctx, viewport: viewport });

        document.getElementById('pdf-page-info').textContent =
            state.pdfPage + ' / ' + state.pdfDoc.numPages;
        var pctText = state.pdfScale === 0 ?
            'Fit' : Math.round(state.pdfScale * 100) + '%';
        document.getElementById('pdf-zoom-level').textContent = pctText;
    });
}

// ===== Bibliography =====
function loadBibEntries() {
    fetch(API_BASE + 'api/bib/entries')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var container = document.getElementById('bib-list');
            if (!data.entries || data.entries.length === 0) {
                container.innerHTML =
                    '<div class="loading">No bibliography entries found.</div>';
                return;
            }
            container.innerHTML = '';
            data.entries.forEach(function(entry) {
                var el = document.createElement('div');
                el.className = 'bib-entry';
                el.innerHTML = '<span class="bib-key">' +
                    escapeHtml(entry.citation_key) + '</span>' +
                    '<span class="bib-type">' +
                    escapeHtml(entry.entry_type) + '</span>' +
                    '<span class="bib-file">' +
                    escapeHtml(entry.bibfile) + '</span>';
                el.addEventListener('click', function() {
                    if (state.editor) {
                        state.editor.replaceSelection(
                            '\\cite{' + entry.citation_key + '}');
                        state.editor.focus();
                    }
                });
                container.appendChild(el);
            });
        })
        .catch(function() {
            document.getElementById('bib-list').innerHTML =
                '<div class="loading">Error loading bibliography.</div>';
        });
}

// ===== Preview Tabs =====
function setupPreviewTabs() {
    document.querySelectorAll('.preview-tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            var view = this.getAttribute('data-view');
            document.querySelectorAll('.preview-tab').forEach(function(t) {
                t.classList.remove('active');
            });
            this.classList.add('active');
            document.querySelectorAll('.preview-view').forEach(function(v) {
                v.classList.remove('active');
            });
            document.getElementById(view + '-view').classList.add('active');
        });
    });
}

// ===== Toolbar =====
function setupToolbar() {
    document.getElementById('btn-compile').addEventListener('click', startCompile);

    document.getElementById('btn-toggle-log').addEventListener('click', function() {
        var logPanel = document.getElementById('log-panel');
        logPanel.style.display = logPanel.style.display === 'none' ? '' : 'none';
    });

    document.getElementById('btn-close-log').addEventListener('click', function() {
        document.getElementById('log-panel').style.display = 'none';
    });

    document.getElementById('btn-toggle-theme').addEventListener('click', toggleTheme);
    document.getElementById('btn-refresh-pdf').addEventListener('click', loadPdf);

    document.getElementById('btn-collapse-sidebar').addEventListener('click', function() {
        var sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('collapsed');
        var resizer = document.getElementById('sidebar-resizer');
        resizer.style.display = sidebar.classList.contains('collapsed') ? 'none' : '';
    });

    // PDF controls
    document.getElementById('btn-pdf-prev').addEventListener('click', function() {
        if (state.pdfPage > 1) { state.pdfPage--; renderPdfPage(); }
    });
    document.getElementById('btn-pdf-next').addEventListener('click', function() {
        if (state.pdfDoc && state.pdfPage < state.pdfDoc.numPages) {
            state.pdfPage++; renderPdfPage();
        }
    });
    document.getElementById('btn-pdf-zoom-in').addEventListener('click', function() {
        if (state.pdfScale === 0) state.pdfScale = 1.0;
        state.pdfScale = Math.min(state.pdfScale + 0.25, 4.0);
        renderPdfPage();
    });
    document.getElementById('btn-pdf-zoom-out').addEventListener('click', function() {
        if (state.pdfScale === 0) state.pdfScale = 1.0;
        state.pdfScale = Math.max(state.pdfScale - 0.25, 0.25);
        renderPdfPage();
    });
    document.getElementById('btn-pdf-fit').addEventListener('click', function() {
        state.pdfScale = 0;
        renderPdfPage();
    });

    document.getElementById('doc-type-select').addEventListener('change', loadPdf);
    loadPdf();
}

// ===== Theme Toggle =====
function toggleTheme() {
    var html = document.documentElement;
    var current = html.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    document.getElementById('theme-icon').innerHTML =
        next === 'dark' ? '&#9788;' : '&#9789;';
    localStorage.setItem('scitex-writer-theme', next);
    if (state.editor) state.editor.refresh();
}

// Restore saved theme
(function() {
    var saved = localStorage.getItem('scitex-writer-theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('theme-icon').innerHTML =
                saved === 'dark' ? '&#9788;' : '&#9789;';
        });
    }
})();

// ===== Keyboard Shortcuts =====
function setupKeyboard() {
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'B') {
            e.preventDefault(); startCompile();
        }
        if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === 's') {
            e.preventDefault(); saveCurrentFile();
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 'w') {
            e.preventDefault();
            if (state.activeTab !== null) closeTab(state.activeTab);
        }
    });
}

// ===== Panel Resizers =====
function setupResizers() {
    document.querySelectorAll('.resizer').forEach(function(resizer) {
        var startX, startWidth, target, direction;

        resizer.addEventListener('mousedown', function(e) {
            e.preventDefault();
            var targetId = resizer.getAttribute('data-target');
            target = document.getElementById(targetId);
            direction = resizer.getAttribute('data-direction');
            startX = e.clientX;
            startWidth = target.offsetWidth;
            resizer.classList.add('active');
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        function onMouseMove(e) {
            var delta = direction === 'left' ?
                e.clientX - startX : startX - e.clientX;
            target.style.width = Math.max(40, startWidth + delta) + 'px';
        }

        function onMouseUp() {
            resizer.classList.remove('active');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            if (state.editor) state.editor.refresh();
        }
    });
}

// ===== Claims =====

// Initialize Mermaid (called once after page load)
var mermaidReady = false;
function initMermaid() {
    if (typeof mermaid !== 'undefined' && !mermaidReady) {
        mermaid.initialize({
            startOnLoad: false,
            theme: document.documentElement.getAttribute('data-theme') === 'dark'
                    ? 'dark' : 'default',
            securityLevel: 'loose'
        });
        mermaidReady = true;
    }
}

// Render Mermaid code to SVG, inject into container element
async function renderMermaidDiagram(code, container) {
    initMermaid();
    if (!mermaidReady) {
        container.innerHTML = '<span class="ct-muted">Mermaid not loaded</span>';
        return;
    }
    try {
        var id = 'mermaid-' + Date.now();
        var result = await mermaid.render(id, code);
        container.innerHTML = result.svg;
        // Make SVG responsive
        var svg = container.querySelector('svg');
        if (svg) {
            svg.style.maxWidth = '100%';
            svg.style.height = 'auto';
        }
    } catch (e) {
        container.innerHTML = '<span class="ct-muted">Diagram error: ' + e.message + '</span>';
    }
}

// ---- Claims Panel ----

function loadClaims() {
    var list = document.getElementById('claims-list');
    var countEl = document.getElementById('claims-count');
    if (!list) return;
    list.innerHTML = '<div class="loading">Loading claims...</div>';

    fetch(API_BASE + 'api/claims')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) {
                list.innerHTML = '<div class="claims-empty">Error: ' + (data.error || 'unknown') + '</div>';
                return;
            }
            if (data.count === 0) {
                list.innerHTML = '<div class="claims-empty">' +
                    '<p>No claims defined yet.</p>' +
                    '<p class="hint">Register claims with the MCP tool <code>writer_claim_add</code><br>' +
                    'or <code>scitex_writer.claim.add()</code> (stored in scitex-clew).</p>' +
                    '</div>';
                if (countEl) countEl.textContent = '';
                return;
            }
            if (countEl) countEl.textContent = data.count + ' claim' + (data.count !== 1 ? 's' : '');
            list.innerHTML = '';
            data.claims.forEach(function(claim) {
                list.appendChild(buildClaimCard(claim));
            });
        })
        .catch(function(e) {
            list.innerHTML = '<div class="claims-empty">Failed to load claims: ' + e + '</div>';
        });
}

function buildClaimCard(claim) {
    var card = document.createElement('div');
    card.className = 'claim-card';
    card.setAttribute('data-claim-id', claim.claim_id);

    var provenanceBadge = claim.has_provenance
        ? '<span class="claim-badge claim-badge-provenance" title="Has provenance">&#9679;</span>'
        : '<span class="claim-badge claim-badge-noprov" title="No provenance">&#9675;</span>';

    var typeBadge = '<span class="claim-type-badge claim-type-' + claim.type + '">'
        + claim.type + '</span>';

    card.innerHTML =
        '<div class="claim-card-header">' +
            '<span class="claim-card-id">' + escapeHtml(claim.claim_id) + '</span>' +
            typeBadge +
            provenanceBadge +
        '</div>' +
        '<div class="claim-card-preview">' + escapeHtml(claim.preview_nature) + '</div>' +
        (claim.context
            ? '<div class="claim-card-context">' + escapeHtml(claim.context) + '</div>'
            : '') +
        '<div class="claim-card-actions">' +
            '<button class="btn btn-sm btn-secondary claim-btn-inspect" ' +
                    'data-id="' + escapeHtml(claim.claim_id) + '"' +
                    'title="Inspect claim + chain">&#128270; Inspect</button>' +
            '<button class="btn btn-sm claim-btn-insert" ' +
                    'data-id="' + escapeHtml(claim.claim_id) + '" ' +
                    'title="Insert \\vclaim{id} at cursor">&#8628; Insert</button>' +
        '</div>';

    // Inspect button → show tooltip panel inline (expanded card)
    card.querySelector('.claim-btn-inspect').addEventListener('click', function() {
        var id = this.getAttribute('data-id');
        showInspectPanel(id, card);
    });

    // Insert button → paste \vclaim{id} into editor
    card.querySelector('.claim-btn-insert').addEventListener('click', function() {
        var id = this.getAttribute('data-id');
        if (state.editor) {
            state.editor.replaceSelection('\\vclaim{' + id + '}');
            state.editor.focus();
        }
    });

    return card;
}

function showInspectPanel(claimId, card) {
    // Remove any existing inline inspect panels
    document.querySelectorAll('.claim-inspect-panel').forEach(function(el) {
        el.remove();
    });

    var panel = document.createElement('div');
    panel.className = 'claim-inspect-panel';
    panel.innerHTML = '<div class="claim-inspect-loading">Loading chain...</div>';
    card.appendChild(panel);

    fetch(API_BASE + 'api/claims/' + encodeURIComponent(claimId) + '/chain')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) {
                panel.innerHTML = '<div class="ct-muted">Error: ' + data.error + '</div>';
                return;
            }
            var html = buildInspectPanelHTML(data);
            panel.innerHTML = html;

            // Render chain diagram if Mermaid code available
            if (data.mermaid) {
                var diagramEl = panel.querySelector('.inspect-chain-diagram');
                if (diagramEl) {
                    renderMermaidDiagram(data.mermaid, diagramEl);
                }
            }
        })
        .catch(function(e) {
            panel.innerHTML = '<div class="ct-muted">Failed: ' + e + '</div>';
        });
}

function buildInspectPanelHTML(data) {
    var p = data.previews || {};
    var claim = data.claim || {};
    var html = '<div class="inspect-styles">';
    html += '<div class="inspect-row"><span class="ct-label">Nature</span>' +
            '<span class="ct-value ct-latex">' + escapeHtml(p.nature || '') + '</span></div>';
    html += '<div class="inspect-row"><span class="ct-label">APA</span>' +
            '<span class="ct-value ct-latex">' + escapeHtml(p.apa || '') + '</span></div>';
    html += '<div class="inspect-row"><span class="ct-label">Plain</span>' +
            '<span class="ct-value">' + escapeHtml(p.plain || '') + '</span></div>';
    if (claim.context) {
        html += '<div class="inspect-row"><span class="ct-label">Context</span>' +
                '<span class="ct-value ct-muted">' + escapeHtml(claim.context) + '</span></div>';
    }
    if (claim.session_id || claim.output_file) {
        html += '<div class="inspect-row"><span class="ct-label">Session</span>' +
                '<span class="ct-value ct-mono ct-muted">' +
                escapeHtml(claim.session_id || '—') + '</span></div>';
        if (claim.output_file) {
            html += '<div class="inspect-row"><span class="ct-label">Source</span>' +
                    '<span class="ct-value ct-mono ct-muted">' +
                    escapeHtml(claim.output_file) + '</span></div>';
        }
    }
    html += '</div>';

    if (data.mermaid) {
        var badge = data.clew_available
            ? '<span class="ct-clew-badge ct-clew-ok">clew ✓</span>'
            : '';
        html += '<div class="inspect-chain-section">' +
                '<div class="ct-label">Verification Chain ' + badge + '</div>' +
                '<div class="inspect-chain-diagram"></div>' +
                '</div>';
    } else if (data.has_provenance && !data.clew_available) {
        html += '<div class="inspect-chain-section">' +
                '<div class="ct-muted inspect-no-clew">' +
                '&#9888; Provenance stored but <code>scitex.clew</code> not installed. ' +
                'Install scitex to visualize the chain.</div>' +
                '</div>';
    } else if (!data.has_provenance) {
        html += '<div class="inspect-chain-section">' +
                '<div class="ct-muted inspect-no-clew">' +
                'No provenance data. Add <code>session_id</code> or <code>output_file</code> ' +
                'to link this claim to a Clew-tracked computation.</div>' +
                '</div>';
    }

    return html;
}

// ---- Hover Tooltip ----

var _tooltipTimer = null;
var _activeTooltipId = null;

function findClaimIdAtPos(line, ch) {
    // Match \vclaim{id} or \vclaim[style]{id}
    var re = /\\vclaim(?:\[[^\]]*\])?\{([^}]+)\}/g;
    var match;
    while ((match = re.exec(line)) !== null) {
        if (ch >= match.index && ch <= match.index + match[0].length) {
            return match[1];
        }
    }
    return null;
}

function setupClaimHover() {
    // Wait until editor is created, then attach listener
    var checkInterval = setInterval(function() {
        if (!state.editor) return;
        clearInterval(checkInterval);

        state.editor.getWrapperElement().addEventListener('mousemove', function(e) {
            if (!state.editor) return;
            try {
                var pos = state.editor.coordsChar({ left: e.clientX, top: e.clientY });
                var line = state.editor.getLine(pos.line) || '';
                var claimId = findClaimIdAtPos(line, pos.ch);
                if (claimId) {
                    if (claimId !== _activeTooltipId) {
                        clearTimeout(_tooltipTimer);
                        _tooltipTimer = setTimeout(function() {
                            showHoverTooltip(claimId, e.clientX, e.clientY);
                        }, 300); // 300ms debounce
                        _activeTooltipId = claimId;
                    }
                } else {
                    clearTimeout(_tooltipTimer);
                    _activeTooltipId = null;
                    // Give time for user to move mouse into tooltip
                    setTimeout(function() {
                        var tooltip = document.getElementById('claim-tooltip');
                        if (tooltip && !tooltip.matches(':hover')) {
                            hideClaimTooltip();
                        }
                    }, 400);
                }
            } catch(e) { /* coordsChar can throw on edge cases */ }
        });

        state.editor.getWrapperElement().addEventListener('mouseleave', function() {
            clearTimeout(_tooltipTimer);
            _activeTooltipId = null;
            setTimeout(function() {
                var tooltip = document.getElementById('claim-tooltip');
                if (tooltip && !tooltip.matches(':hover')) {
                    hideClaimTooltip();
                }
            }, 500);
        });
    }, 200);

    // Tooltip stays visible while hovered
    var tooltip = document.getElementById('claim-tooltip');
    if (tooltip) {
        tooltip.addEventListener('mouseleave', function() {
            hideClaimTooltip();
        });
        document.getElementById('ct-close').addEventListener('click', function() {
            hideClaimTooltip();
        });
    }
}

function showHoverTooltip(claimId, mouseX, mouseY) {
    var tooltip = document.getElementById('claim-tooltip');
    if (!tooltip) return;

    // Reset tooltip content
    document.getElementById('ct-id').textContent = claimId;
    document.getElementById('ct-type').textContent = '';
    document.getElementById('ct-nature').textContent = '';
    document.getElementById('ct-apa').textContent = '';
    document.getElementById('ct-plain').textContent = '';
    document.getElementById('ct-context-section').style.display = 'none';
    document.getElementById('ct-provenance-section').style.display = 'none';
    document.getElementById('ct-chain-section').style.display = 'none';
    document.getElementById('ct-chain-diagram').innerHTML =
        '<div class="ct-chain-loading">Loading chain...</div>';

    // Position tooltip near mouse, keeping in viewport
    tooltip.style.display = 'block';
    var vw = window.innerWidth, vh = window.innerHeight;
    var tw = Math.min(tooltip.offsetWidth || 400, 420);
    var left = Math.min(mouseX + 12, vw - tw - 12);
    var top = mouseY + 20;
    if (top + 300 > vh) top = mouseY - 320;
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';

    // Fetch claim + chain data
    fetch(API_BASE + 'api/claims/' + encodeURIComponent(claimId) + '/chain')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) {
                document.getElementById('ct-nature').textContent = 'Claim not found';
                return;
            }
            populateTooltip(data);
        })
        .catch(function(e) {
            document.getElementById('ct-nature').textContent = 'Error: ' + e;
        });
}

function populateTooltip(data) {
    var claim = data.claim || {};
    var previews = data.previews || {};

    document.getElementById('ct-type').textContent = claim.type || '';
    document.getElementById('ct-nature').textContent = previews.nature || '';
    document.getElementById('ct-apa').textContent = previews.apa || '';
    document.getElementById('ct-plain').textContent = previews.plain || '';

    if (claim.context) {
        document.getElementById('ct-context').textContent = claim.context;
        document.getElementById('ct-context-section').style.display = '';
    }

    if (claim.session_id || claim.output_file) {
        var prov = [];
        if (claim.session_id) prov.push('session: ' + claim.session_id);
        if (claim.output_file) prov.push('file: ' + claim.output_file);
        document.getElementById('ct-provenance').textContent = prov.join('\n');
        document.getElementById('ct-provenance-section').style.display = '';
    }

    if (data.mermaid) {
        var chainSection = document.getElementById('ct-chain-section');
        chainSection.style.display = '';
        var badge = document.getElementById('ct-clew-badge');
        badge.textContent = data.clew_available ? 'clew ✓' : '';
        badge.className = 'ct-clew-badge' + (data.clew_available ? ' ct-clew-ok' : '');
        var diagramEl = document.getElementById('ct-chain-diagram');
        renderMermaidDiagram(data.mermaid, diagramEl);
    } else if (data.has_provenance) {
        var chainSection2 = document.getElementById('ct-chain-section');
        chainSection2.style.display = '';
        document.getElementById('ct-chain-diagram').innerHTML =
            '<span class="ct-muted">Install scitex to visualize the chain.</span>';
    }
}

function hideClaimTooltip() {
    var tooltip = document.getElementById('claim-tooltip');
    if (tooltip) tooltip.style.display = 'none';
    _activeTooltipId = null;
}

// ---- Init ----

function initClaims() {
    // Refresh claims button
    var btnRefresh = document.getElementById('btn-refresh-claims');
    if (btnRefresh) btnRefresh.addEventListener('click', loadClaims);

    // Render .tex button
    var btnRender = document.getElementById('btn-render-claims');
    if (btnRender) {
        btnRender.addEventListener('click', function() {
            btnRender.disabled = true;
            btnRender.textContent = 'Rendering...';
            fetch(API_BASE + 'api/claims/render', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    btnRender.disabled = false;
                    btnRender.innerHTML = '&#9881; Render .tex';
                    if (data.success) {
                        btnRender.title = 'Rendered ' + data.claims_count + ' claims';
                    }
                })
                .catch(function() {
                    btnRender.disabled = false;
                    btnRender.innerHTML = '&#9881; Render .tex';
                });
        });
    }

    // Setup hover detection
    setupClaimHover();
    initMermaid();
}

})();
