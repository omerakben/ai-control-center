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

  renderHead();
  renderBanner();
  renderOverview();
  renderInventory();
  renderDocs();
  renderTodos();
  wireSearch();
})();
