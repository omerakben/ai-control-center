(function () {
  var node = document.getElementById("acc-data");
  var data = JSON.parse(node.textContent);
  var pathPrefix = (data.source && data.source.pathPrefix) || "";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // Decode the five entities html.escape (Python) produces. Applied ONLY at
  // textContent display and when building the omnibox match key, so search and
  // display see logical text (AT&T, not AT&amp;T) without an HTML sink — the
  // decoded value still reaches the DOM via textContent and stays inert.
  // Order matters: decode &amp; LAST so "&amp;lt;" does not double-decode.
  function htmlUnescape(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#x27;/g, "'")
      .replace(/&#39;/g, "'")
      .replace(/&amp;/g, "&");
  }
  // expose for DOM tests; harmless in production (no behavior, just a handle)
  window.__accHtmlUnescape = htmlUnescape;

  function encodedRelHref(prefix, path) {
    var raw = (prefix === "." ? path : prefix + "/" + path);
    return raw.split("/").map(function (seg) {
      return seg === "." || seg === ".." ? seg : encodeURIComponent(seg);
    }).join("/");
  }

  function itemRow(opts) {
    var row = el("div", "acc-row acc-item");
    if (opts.id) row.dataset.id = opts.id;
    var head = el("div", "acc-rowhead");
    if (opts.provider) head.appendChild(el("span", "acc-chip", opts.provider));
    if (opts.typeLabel) head.appendChild(el("span", "badge", opts.typeLabel));
    head.appendChild(el("span", "acc-itemtitle", htmlUnescape(opts.title)));
    row.appendChild(head);
    if (opts.summary) row.appendChild(el("div", "acc-summary", htmlUnescape(opts.summary)));
    if (pathPrefix) {
      var a = el("a", "path", opts.path);
      a.href = encodedRelHref(pathPrefix, opts.path);
      row.appendChild(a);
    } else {
      row.appendChild(el("span", "path", opts.path));
    }
    row.dataset.search =
      (htmlUnescape(opts.title) + " " + opts.path + " " +
       htmlUnescape(opts.summary || "")).toLowerCase();
    return row;
  }

  // Display order (deliberate; differs from _INV_BUCKETS storage order in
  // base.py, which has skills before commands). The renderer owns its order.
  var INV_ORDER = ["agents", "commands", "skills", "hooks", "mcpServers", "rules"];
  var INV_LABEL = {
    agents: "Agents", commands: "Commands", skills: "Skills",
    hooks: "Hooks", mcpServers: "MCP servers", rules: "Rules"
  };

  function renderInventory() {
    var host = document.getElementById("acc-inventory");
    var inv = data.inventory || {};
    INV_ORDER.forEach(function (bucket) {
      var items = inv[bucket] || [];
      if (!items.length) return;
      host.appendChild(el("div", "acc-sublabel",
        INV_LABEL[bucket] + " (" + items.length + ")"));
      items.forEach(function (it) {
        host.appendChild(itemRow({
          id: it.id,
          provider: it.provider, typeLabel: it.typeLabel,
          title: it.title, path: it.path, summary: it.summary
        }));
      });
    });
  }

  function renderHead() {
    document.getElementById("acc-title").textContent = data.project.title;
    var m = data.source;
    document.getElementById("acc-meta").textContent =
      "stamped · digest " + m.sourceDigest + " · vcs: " + m.vcs.kind + " · freshness is manual";
  }

  function renderDocs() {
    var host = document.getElementById("acc-docs");
    var groups = data.docs;
    Object.keys(groups).sort().forEach(function (g) {
      groups[g].forEach(function (doc) {
        host.appendChild(itemRow({
          id: doc.id,
          typeLabel: g, title: doc.title, path: doc.path, summary: doc.summary
        }));
      });
    });
  }

  function renderTodos() {
    var host = document.getElementById("acc-todos");
    (data.project.openTodos || []).forEach(function (t) {
      host.appendChild(itemRow({ id: t.id, title: t.text, path: t.path }));
    });
  }

  function plural(n, word) { return n + " " + (n === 1 ? word.replace(/s$/, "") : word); }

  function card(title, target) {
    var c = el("div", "acc-card");
    if (target) {
      var a = el("a", "acc-card-h", title);
      a.href = "#" + target;
      c.appendChild(a);
    } else {
      c.appendChild(el("div", "acc-card-h", title));
    }
    return c;
  }

  function renderOverview() {
    var host = document.getElementById("acc-overview");
    var bento = el("div", "acc-bento");

    // providers always includes generic; show excludes it when first-class providers exist
    var provs = data.providers || [];
    var firstClass = provs.filter(function (p) { return p.id !== "generic"; });
    var show = firstClass.length ? firstClass : provs;
    if (show.length) {
      var pc = card("Providers");
      show.forEach(function (p) { pc.appendChild(el("span", "acc-chip", p.displayName)); });
      bento.appendChild(pc);
    }

    var inv = data.inventory || {};
    var nonEmpty = INV_ORDER.filter(function (b) { return (inv[b] || []).length; });
    if (nonEmpty.length) {
      var ic = card("Inventory", "inventory");
      nonEmpty.forEach(function (b) {
        ic.appendChild(el("div", null, plural(inv[b].length, INV_LABEL[b].toLowerCase())));
      });
      bento.appendChild(ic);
    }

    var todos = (data.project && data.project.openTodos) || [];
    if (todos.length) {
      var tc = card("Open TODOs (" + todos.length + ")", "todos");
      todos.slice(0, 3).forEach(function (t) { tc.appendChild(el("div", null, t.text)); });
      bento.appendChild(tc);
    }

    var docs = data.docs || {};
    var docCount = 0;
    Object.keys(docs).forEach(function (k) { docCount += (docs[k] || []).length; });
    if (docCount) {
      var dc = card("Docs", "docs");
      dc.appendChild(el("div", null, docCount + " referenced"));
      bento.appendChild(dc);
    }

    var rels = data.relationships || [];
    if (rels.length) {
      var xc = card("Cross-references", "crossref");
      xc.appendChild(el("div", null, plural(rels.length, "edges")));
      bento.appendChild(xc);
    }

    if (bento.children.length) host.appendChild(bento);
  }

  function renderBanner() {
    if (!(data.generator && data.generator.truncated)) return;
    document.getElementById("acc-banner").appendChild(el("div", "acc-noticetext",
      "This dashboard was reduced to a summary because the full output exceeded the size budget."));
  }

  function wireSearch() {
    var box = document.getElementById("acc-search");
    box.addEventListener("input", function () {
      var q = box.value.toLowerCase();
      document.querySelectorAll(".acc-item").forEach(function (row) {
        var hit = !q || (row.dataset.search || "").indexOf(q) !== -1;
        row.classList.toggle("acc-hidden", !hit);
      });
    });
  }

  var rowById = new Map();

  function buildRowIndex() {
    rowById.clear();
    document.querySelectorAll(".acc-item[data-id]").forEach(function (row) {
      // first rendered row wins for a given id (ids are stable + unique anyway)
      if (!rowById.has(row.dataset.id)) rowById.set(row.dataset.id, row);
    });
  }

  function jumpTo(id) {
    var row = rowById.get(id);
    if (!row) return; // degrade: empty bucket skipped, or light/truncated mode
    row.scrollIntoView({ block: "center" });
    row.classList.remove("acc-flash");
    // reflow so re-adding the class restarts the flash animation
    void row.offsetWidth;
    row.classList.add("acc-flash");
    window.setTimeout(function () { row.classList.remove("acc-flash"); }, 1600);
  }
  window.__accJump = jumpTo;

  var metaById = {};
  function buildMeta() {
    var inv = data.inventory || {};
    Object.keys(inv).forEach(function (b) {
      (inv[b] || []).forEach(function (it) {
        metaById[it.id] = { title: it.title, typeLabel: it.typeLabel, path: it.path };
      });
    });
    var docs = data.docs || {};
    Object.keys(docs).forEach(function (g) {
      (docs[g] || []).forEach(function (d) {
        metaById[d.id] = { title: d.title, typeLabel: g, path: d.path };
      });
    });
    (data.project.openTodos || []).forEach(function (t) {
      metaById[t.id] = { title: t.text, typeLabel: "TODO", path: t.path };
    });
  }

  var edgesByEndpoint = {};
  function buildEdgeIndex() {
    (data.relationships || []).forEach(function (e) {
      (edgesByEndpoint[e.from] || (edgesByEndpoint[e.from] = []))
        .push({ otherId: e.to, dir: "out", type: e.type, evidence: e.evidence });
      (edgesByEndpoint[e.to] || (edgesByEndpoint[e.to] = []))
        .push({ otherId: e.from, dir: "in", type: e.type, evidence: e.evidence });
    });
  }

  var REL_VERB = {
    "reference|out": "references", "reference|in": "referenced by",
    "declares|out": "declares", "declares|in": "declared in"
  };

  function relatedEntry(edge) {
    var verb = REL_VERB[edge.type + "|" + edge.dir] || edge.type;
    var meta = metaById[edge.otherId];
    if (edge.type === "declares" && edge.dir === "in") {
      var label = el("span", "acc-rel-line");
      label.appendChild(el("span", "acc-rel-verb", verb));
      label.appendChild(el("span", "path", edge.evidence));
      return label;
    }
    if (!meta) return null;
    var btn = el("button", "acc-rel-line");
    btn.type = "button";
    btn.appendChild(el("span", "acc-rel-verb", verb));
    btn.appendChild(el("span", "acc-chip", meta.typeLabel));
    btn.appendChild(el("span", "acc-rel-title", htmlUnescape(meta.title)));
    btn.addEventListener("click", function () { jumpTo(edge.otherId); });
    return btn;
  }

  function decorateRelated() {
    rowById.forEach(function (row, id) {
      var edges = edgesByEndpoint[id];
      if (!edges || !edges.length) return;
      var box = el("div", "acc-related");
      edges.forEach(function (e) {
        var node = relatedEntry(e);
        if (node) box.appendChild(node);
      });
      if (box.children.length) row.appendChild(box);
    });
  }

  function sourceLabel(fromId, sampleEdge) {
    var meta = metaById[fromId];
    if (meta) return { title: htmlUnescape(meta.title), type: meta.typeLabel, sort: meta.path || meta.title };
    return { title: sampleEdge.evidence, type: "config", sort: sampleEdge.evidence };
  }

  function renderCrossReferences() {
    var host = document.getElementById("acc-crossref");
    if (!host) return;
    var edges = data.relationships || [];
    if (!edges.length) {
      host.appendChild(el("div", "acc-xref-empty", "No cross-references found"));
      return;
    }
    var bySource = {};
    edges.forEach(function (e) { (bySource[e.from] || (bySource[e.from] = [])).push(e); });
    var groups = Object.keys(bySource).map(function (fromId) {
      return { fromId: fromId, label: sourceLabel(fromId, bySource[fromId][0]), edges: bySource[fromId] };
    });
    groups.sort(function (a, b) { return a.label.sort < b.label.sort ? -1 : a.label.sort > b.label.sort ? 1 : 0; });
    groups.forEach(function (g) {
      var head = el("div", "acc-xref-source");
      head.appendChild(el("span", "acc-chip", g.label.type));
      head.appendChild(el("span", "acc-xref-srctitle", g.label.title));
      host.appendChild(head);
      var targets = g.edges.map(function (e) {
        var m = metaById[e.to] || {};
        return { e: e, title: htmlUnescape(m.title || ""), type: m.typeLabel || "", sort: (m.path || m.title || "") };
      });
      targets.sort(function (a, b) { return a.sort < b.sort ? -1 : a.sort > b.sort ? 1 : 0; });
      targets.forEach(function (t) {
        var btn = el("button", "acc-xref-edge");
        btn.type = "button";
        btn.appendChild(el("span", "acc-rel-verb", t.e.type === "declares" ? "declares" : "references"));
        btn.appendChild(el("span", "acc-chip", t.type));
        btn.appendChild(el("span", "acc-rel-title", t.title));
        btn.appendChild(el("span", "path", t.e.evidence));
        btn.addEventListener("click", function () { jumpTo(t.e.to); });
        host.appendChild(btn);
      });
    });
  }

  var OMNI_GROUP_CAP = 8;
  var INV_TYPE_ORDER = ["agent", "command", "skill", "hook", "mcpServer", "rule", "doc", "todo"];

  function searchRecords() { return data.search || []; }

  function matchKey(rec) {
    if (rec.__key == null) {
      rec.__key = htmlUnescape(
        (rec.title || "") + " " + (rec.path || "") + " " + (rec.text || "")
      ).toLowerCase();
    }
    return rec.__key;
  }

  function isLightIndex() {
    var recs = searchRecords();
    return recs.length > 0 && recs.every(function (r) { return (r.text || "") === ""; });
  }

  // Append text + <mark> nodes by splitting the logical string on the query.
  // No HTML strings — every node is built via textContent / createElement.
  function appendHighlighted(target, logical, qLower) {
    if (!qLower) { target.appendChild(document.createTextNode(logical)); return; }
    var hay = logical.toLowerCase();
    var from = 0, idx;
    while ((idx = hay.indexOf(qLower, from)) !== -1) {
      if (idx > from) target.appendChild(document.createTextNode(logical.slice(from, idx)));
      var m = document.createElement("mark");
      m.textContent = logical.slice(idx, idx + qLower.length);
      target.appendChild(m);
      from = idx + qLower.length;
    }
    if (from < logical.length) target.appendChild(document.createTextNode(logical.slice(from)));
  }

  function snippetFor(rec, qLower) {
    var logical = htmlUnescape(rec.text || "");
    var idx = logical.toLowerCase().indexOf(qLower);
    if (idx === -1) return logical.slice(0, 120);
    var start = Math.max(0, idx - 40);
    var end = Math.min(logical.length, idx + qLower.length + 80);
    return (start > 0 ? "…" : "") + logical.slice(start, end) + (end < logical.length ? "…" : "");
  }

  function wireOmnibox() {
    var box = document.getElementById("acc-omnibox");
    var panel = document.getElementById("acc-omnibox-results");
    if (!box || !panel) return;
    var hits = [];
    var active = -1;
    var timer = null;

    function close() { panel.hidden = true; panel.textContent = ""; hits = []; active = -1; }

    function setActive(i) {
      var nodes = panel.querySelectorAll(".acc-omni-hit");
      if (active >= 0 && nodes[active]) nodes[active].classList.remove("acc-omni-active");
      active = i;
      if (active >= 0 && nodes[active]) {
        nodes[active].classList.add("acc-omni-active");
        nodes[active].scrollIntoView({ block: "nearest" });
      }
    }

    function render(q) {
      panel.textContent = "";
      hits = [];
      active = -1;
      var qLower = q.toLowerCase();
      if (!qLower) { close(); return; }
      panel.hidden = false;

      if (isLightIndex()) {
        panel.appendChild(el("div", "acc-omni-note",
          "Body search is off (index reduced for size); searching names and paths only."));
      }

      var byType = {};
      searchRecords().forEach(function (rec) {
        if (matchKey(rec).indexOf(qLower) === -1) return;
        (byType[rec.type] || (byType[rec.type] = [])).push(rec);
      });
      var types = INV_TYPE_ORDER.filter(function (t) { return byType[t]; });
      Object.keys(byType).forEach(function (t) {
        if (types.indexOf(t) === -1) types.push(t);
      });

      if (!types.length) {
        panel.appendChild(el("div", "acc-omni-note", "No matches"));
        return;
      }

      types.forEach(function (t) {
        var recs = byType[t];
        var group = el("div", "acc-omni-group");
        group.appendChild(el("div", "acc-omni-grouphead",
          (recs[0].typeLabel || t) + " (" + recs.length + ")"));
        recs.slice(0, OMNI_GROUP_CAP).forEach(function (rec) {
          var hit = el("div", "acc-omni-hit");
          hit.dataset.id = rec.id;
          var titleEl = el("span", "acc-omni-title");
          appendHighlighted(titleEl, htmlUnescape(rec.title || ""), qLower);
          hit.appendChild(titleEl);
          hit.appendChild(el("span", "acc-chip", rec.typeLabel || t));
          hit.appendChild(el("span", "path", rec.path || ""));
          if ((rec.text || "") !== "") {
            var snipEl = el("span", "acc-omni-snippet");
            appendHighlighted(snipEl, snippetFor(rec, qLower), qLower);
            hit.appendChild(snipEl);
          }
          hit.addEventListener("click", function () { jumpTo(rec.id); });
          group.appendChild(hit);
          hits.push(rec);
        });
        if (recs.length > OMNI_GROUP_CAP) {
          group.appendChild(el("div", "acc-omni-more",
            "+" + (recs.length - OMNI_GROUP_CAP) + " more"));
        }
        panel.appendChild(group);
      });
    }

    box.addEventListener("input", function () {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(function () { render(box.value); }, 60);
    });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { box.value = ""; close(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); if (hits.length) setActive(Math.min(active + 1, hits.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); if (hits.length) setActive(Math.max(active - 1, 0)); }
      else if (e.key === "Enter") {
        e.preventDefault();
        var pick = active >= 0 ? active : 0;
        if (hits[pick]) jumpTo(hits[pick].id);
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "/") return;
      var a = document.activeElement;
      var tag = a && a.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (a && a.isContentEditable)) return;
      e.preventDefault();
      box.focus();
    });
  }

  buildMeta();
  buildEdgeIndex();
  renderHead();
  renderBanner();
  renderOverview();
  renderInventory();
  renderDocs();
  renderTodos();
  buildRowIndex();
  decorateRelated();
  renderCrossReferences();
  wireOmnibox();
  wireSearch();
})();
