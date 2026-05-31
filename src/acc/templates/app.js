(function () {
  var node = document.getElementById("acc-data");
  var data = JSON.parse(node.textContent);
  var pathPrefix = (data.source && data.source.pathPrefix) || "";
  var truncated = !!(data.generator && data.generator.truncated);

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

  // ---- markdown → DOM (textContent-only; NO HTML-string sinks) ----
  // Every node is built via createElement + createTextNode, so hostile markup in
  // author content stays inert and the CI guard (which forbids the HTML-string
  // assignment properties) holds. Search highlight is folded in so markdown
  // spans and <mark> compose in one pass.

  // Mirror markdown.py:_safe_link — allow only http/https or repo-relative; a
  // leading "/" (root- or protocol-relative) and any non-http(s) scheme (e.g.
  // javascript:) are rejected so a link can never become a script sink.
  function safeUrl(url) {
    var s = String(url);
    // Browsers strip ASCII whitespace and C0/DEL control characters from an href
    // before resolving the scheme, so a "\x01javascript:" or "java<TAB>script:" URL
    // would smuggle a script scheme past a position-0 check. Reject any such char
    // (anywhere) plus a leading slash/backslash, then validate the scheme on the
    // exact value the browser would use. Markdown URLs never legitimately carry
    // these (RE_LINK already forbids whitespace in the URL token).
    if (/[\u0000-\u0020\u007f]/.test(s)) return false;
    if (s.charAt(0) === "/" || s.charAt(0) === "\\") return false;
    var m = /^([a-z][a-z0-9+.\-]*):/i.exec(s);
    if (m) return /^https?$/i.test(m[1]);
    return true;
  }

  // Append `logical` text into `target`, wrapping query matches in <mark>.
  function appendHighlighted(target, logical, qLower) {
    if (!qLower) { target.appendChild(document.createTextNode(logical)); return; }
    var hay = logical.toLowerCase(), from = 0, idx;
    while ((idx = hay.indexOf(qLower, from)) !== -1) {
      if (idx > from) target.appendChild(document.createTextNode(logical.slice(from, idx)));
      var mk = el("mark");
      mk.textContent = logical.slice(idx, idx + qLower.length);
      target.appendChild(mk);
      from = idx + qLower.length;
    }
    if (from < logical.length) target.appendChild(document.createTextNode(logical.slice(from)));
  }

  // Inner emphasis classes use [^*]/[^`] so a single scanner pass can't run away
  // on pathological input, and so snake_case (handled by asterisks-only) and
  // code never get mangled. Asterisks only — underscores are left literal so
  // identifiers like rate_limit_config render verbatim.
  var RE_CODE = /`([^`]+)`/;
  var RE_LINK = /\[([^\]]+)\]\(([^)\s]+)\)/;
  var RE_BOLD = /\*\*([^*]+?)\*\*/;
  var RE_ITALIC = /\*([^*]+?)\*/;

  // Render inline markdown of LOGICAL (already-unescaped) text into `parent`.
  function renderInlineInto(parent, text, qLower) {
    if (!text) return;
    var best = null;
    function consider(re, type) {
      var m = re.exec(text);
      if (m && (best === null || m.index < best.i)) best = { i: m.index, m: m, type: type };
    }
    consider(RE_CODE, "code");
    consider(RE_LINK, "link");
    consider(RE_BOLD, "bold");
    consider(RE_ITALIC, "italic");
    if (best === null) { appendHighlighted(parent, text, qLower); return; }
    if (best.i > 0) appendHighlighted(parent, text.slice(0, best.i), qLower);
    var m = best.m, rest = text.slice(best.i + m[0].length);
    if (best.type === "code") {
      var c = el("code");
      appendHighlighted(c, m[1], qLower);
      parent.appendChild(c);
    } else if (best.type === "link") {
      if (safeUrl(m[2])) {
        var a = el("a", "acc-mdlink");
        a.href = m[2];
        renderInlineInto(a, m[1], qLower);
        parent.appendChild(a);
      } else {
        // unsafe scheme: degrade to plain "label (url)" like markdown.py does
        renderInlineInto(parent, m[1] + " (" + m[2] + ")", qLower);
      }
    } else {
      var e = el(best.type === "bold" ? "strong" : "em");
      renderInlineInto(e, m[1], qLower);
      parent.appendChild(e);
    }
    renderInlineInto(parent, rest, qLower);
  }

  // Convenience: render an ESCAPED island string (unescape first, then tokenize).
  function mdInline(parent, escaped, qLower) {
    renderInlineInto(parent, htmlUnescape(escaped), qLower || "");
  }
  // expose the inline renderer for DOM tests
  window.__accRenderInline = function (parent, escaped, q) { mdInline(parent, escaped, q); };

  // A GFM table delimiter row is only pipes/colons/dashes/space and has both.
  function isTableDelim(s) {
    return s.indexOf("|") !== -1 && s.indexOf("-") !== -1 && /^[\s|:-]+$/.test(s);
  }
  function splitTableRow(s) {
    return s.trim().replace(/^\|/, "").replace(/\|$/, "")
      .split("|").map(function (c) { return c.trim(); });
  }

  // Render block-level markdown (headings, lists, fenced code, tables, paragraphs)
  // of an ESCAPED island string into `container`. Used for the inline reading pane.
  function renderBlocks(container, escaped, qLower) {
    var lines = htmlUnescape(escaped).split("\n");
    var i = 0, list = null;
    function flush() { if (list) { container.appendChild(list); list = null; } }
    while (i < lines.length) {
      var line = lines[i];
      if (/^\s*```/.test(line)) {
        flush();
        var buf = [];
        i++;
        while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i++; }
        i++; // skip closing fence
        var pre = el("pre"), code = el("code");
        code.textContent = buf.join("\n");
        pre.appendChild(code);
        container.appendChild(pre);
        continue;
      }
      var h = /^(#{1,6})\s+(.*)$/.exec(line);
      if (h) {
        flush();
        var hh = el("h" + h[1].length);
        renderInlineInto(hh, h[2], qLower || "");
        container.appendChild(hh);
        i++;
        continue;
      }
      var li = /^\s*[-*+]\s+(.*)$/.exec(line);
      if (li) {
        if (!list) list = el("ul");
        var item = el("li");
        renderInlineInto(item, li[1], qLower || "");
        list.appendChild(item);
        i++;
        continue;
      }
      // GFM table: a header row immediately followed by a |---|---| delimiter.
      if (line.indexOf("|") !== -1 && i + 1 < lines.length && isTableDelim(lines[i + 1])) {
        flush();
        var table = el("table", "acc-md-table");
        var thead = el("thead"), htr = el("tr");
        splitTableRow(line).forEach(function (cell) {
          var th = el("th");
          renderInlineInto(th, cell, qLower || "");
          htr.appendChild(th);
        });
        thead.appendChild(htr);
        table.appendChild(thead);
        i += 2; // consume header + delimiter
        var tbody = el("tbody");
        while (i < lines.length && lines[i].indexOf("|") !== -1 && lines[i].trim() !== "") {
          var tr = el("tr");
          splitTableRow(lines[i]).forEach(function (cell) {
            var td = el("td");
            renderInlineInto(td, cell, qLower || "");
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
          i++;
        }
        table.appendChild(tbody);
        container.appendChild(table);
        continue;
      }
      if (line.trim() === "") { flush(); i++; continue; }
      flush();
      var p = el("p");
      renderInlineInto(p, line, qLower || "");
      container.appendChild(p);
      i++;
    }
    flush();
  }

  // ---- rows ----
  function itemRow(opts) {
    var row = el("div", "acc-row acc-item");
    if (opts.id) row.dataset.id = opts.id;
    var head = el("div", "acc-rowhead");
    if (opts.provider) head.appendChild(el("span", "acc-chip acc-prov", opts.provider));
    if (opts.typeLabel) head.appendChild(el("span", "badge", opts.typeLabel));
    var titleEl = el("span", "acc-itemtitle");
    mdInline(titleEl, opts.title, "");
    head.appendChild(titleEl);

    var detail = null;
    if (opts.body) {
      var opened = false, built = false;
      var toggle = el("button", "acc-toggle");
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Toggle reading view");
      toggle.appendChild(el("span", "acc-caret", "›"));
      toggle.appendChild(el("span", "acc-toggle-label", "Read"));
      detail = el("div", "acc-detail acc-hidden");
      var openDetail = function () {
        if (!built) {
          renderBlocks(detail, opts.body, "");
          // Capped body: never end silently — link to the full source file.
          if (opts.bodyTruncated) {
            var more = el("div", "acc-detail-more");
            if (pathPrefix) {
              var a = el("a", "acc-mdlink", "Preview only — open the full file →");
              a.href = encodedRelHref(pathPrefix, opts.path);
              more.appendChild(a);
            } else {
              more.appendChild(document.createTextNode("Preview only — open " + opts.path + " for the full file."));
            }
            detail.appendChild(more);
          }
          built = true;
        }
        detail.classList.remove("acc-hidden");
        row.classList.add("acc-open");
        toggle.setAttribute("aria-expanded", "true");
        opened = true;
      };
      var closeDetail = function () {
        detail.classList.add("acc-hidden");
        row.classList.remove("acc-open");
        toggle.setAttribute("aria-expanded", "false");
        opened = false;
      };
      toggle.addEventListener("click", function (e) {
        e.stopPropagation();
        opened ? closeDetail() : openDetail();
      });
      head.appendChild(toggle);
      row.__accExpand = openDetail;  // for jump-to-expand from the omnibox
    }

    row.appendChild(head);
    if (opts.summary) {
      var s = el("div", "acc-summary");
      mdInline(s, opts.summary, "");
      row.appendChild(s);
    }
    if (pathPrefix) {
      var a = el("a", "path", opts.path);
      a.href = encodedRelHref(pathPrefix, opts.path);
      row.appendChild(a);
    } else {
      row.appendChild(el("span", "path", opts.path));
    }
    if (detail) row.appendChild(detail);
    row.dataset.search =
      (htmlUnescape(opts.title) + " " + (opts.path || "") + " " +
       htmlUnescape(opts.summary || "")).toLowerCase();
    return row;
  }

  function emptyNote(kind) {
    var msg;
    if (kind === "inventory") {
      msg = truncated
        ? "Inventory was trimmed from this summary view — regenerate on a smaller scope to read the agents, skills, commands, hooks and MCP servers."
        : "No agents, skills, commands, hooks, or MCP servers are configured in this repo.";
    } else if (kind === "docs") {
      msg = truncated
        ? "Referenced docs were trimmed from this summary view."
        : "No referenced docs (CLAUDE.md, AGENTS.md, ADRs, specs…) found in this repo.";
    } else {
      msg = truncated
        ? "Open TODOs were trimmed from this summary view."
        : "No open TODOs (‑ [ ] checkboxes) found in this repo.";
    }
    return el("div", "acc-empty", msg);
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
    var any = false;
    INV_ORDER.forEach(function (bucket) {
      var items = inv[bucket] || [];
      if (!items.length) return;
      any = true;
      var head = el("div", "acc-sublabel", INV_LABEL[bucket] + " (" + items.length + ")");
      head.id = "inv-" + bucket;
      host.appendChild(head);
      items.forEach(function (it) {
        host.appendChild(itemRow({
          id: it.id,
          provider: it.provider, typeLabel: it.typeLabel,
          title: it.title, path: it.path, summary: it.summary,
          body: it.body, bodyTruncated: it.bodyTruncated
        }));
      });
    });
    if (!any) host.appendChild(emptyNote("inventory"));
  }

  function topDir(path) {
    var i = path.indexOf("/");
    return i === -1 ? "(root)" : path.slice(0, i) + "/";
  }

  function renderDocs() {
    var host = document.getElementById("acc-docs");
    var groups = data.docs || {};
    var all = [];
    Object.keys(groups).forEach(function (g) {
      (groups[g] || []).forEach(function (d) { all.push(d); });
    });
    if (!all.length) { host.appendChild(emptyNote("docs")); return; }

    var byDir = {};
    all.forEach(function (d) {
      var k = topDir(d.path);
      (byDir[k] || (byDir[k] = [])).push(d);
    });
    var dirs = Object.keys(byDir).sort();
    var collapse = all.length > 40;  // big repos: groups collapsed by default

    dirs.forEach(function (dir) {
      var items = byDir[dir].sort(function (a, b) {
        return a.path < b.path ? -1 : a.path > b.path ? 1 : 0;
      });
      var wrap = el("div", "acc-group");
      items.forEach(function (doc) {
        wrap.appendChild(itemRow({
          id: doc.id, title: doc.title, path: doc.path,
          summary: doc.summary, body: doc.body, bodyTruncated: doc.bodyTruncated
        }));
      });
      if (collapse) {
        wrap.classList.add("acc-hidden");
        var btn = el("button", "acc-sublabel acc-grouptoggle");
        btn.type = "button";
        btn.setAttribute("aria-expanded", "false");
        btn.appendChild(el("span", "acc-caret", "›"));
        btn.appendChild(el("span", null, dir + " (" + items.length + ")"));
        btn.addEventListener("click", function () {
          var open = wrap.classList.toggle("acc-hidden");
          btn.setAttribute("aria-expanded", String(!open));
          btn.classList.toggle("acc-open", !open);
        });
        host.appendChild(btn);
      } else {
        host.appendChild(el("div", "acc-sublabel", dir + " (" + items.length + ")"));
      }
      host.appendChild(wrap);
    });
  }

  function renderTodos() {
    var host = document.getElementById("acc-todos");
    var todos = (data.project && data.project.openTodos) || [];
    if (!todos.length) { host.appendChild(emptyNote("todos")); return; }
    // Render EVERY TODO (so the omnibox can jump to any of them) inside a
    // height-capped scroll box, so a long list is bounded — not an endless wall.
    if (todos.length > 50) {
      host.appendChild(el("div", "acc-more",
        todos.length + " open TODOs — the list scrolls; press / to search across them."));
    }
    var box = el("div", "acc-todos");
    todos.forEach(function (t) {
      box.appendChild(itemRow({ id: t.id, title: t.text, path: t.path }));
    });
    host.appendChild(box);
  }

  function renderHead() {
    document.getElementById("acc-title").textContent = data.project.title;
    var s = data.source;

    var orient = document.getElementById("acc-orient");
    if (orient) {
      orient.textContent = "Offline map of " + htmlUnescape(s.repoName) +
        "'s AI layer — every card links to its source file. Press / to search.";
    }

    var meta = document.getElementById("acc-meta");
    meta.textContent = "";
    var manual = !s.vcs || s.vcs.kind === "none";
    var dot = el("span", "acc-dot " + (manual ? "acc-dot-manual" : "acc-dot-fresh"));
    dot.title = manual ? "freshness is manual — re-run the dashboard to refresh" : "tracked";
    meta.appendChild(dot);
    meta.appendChild(el("span", "acc-pill", "digest " + s.sourceDigest));
    meta.appendChild(el("span", "acc-pill", "schema v" + data.schemaVersion));
    meta.appendChild(el("span", "acc-pill acc-pill-good", "redaction on"));

    var trust = document.getElementById("acc-trust");
    if (trust) {
      var line = "Redaction runs at extraction and a tripwire re-scans the output; secrets never reach this file. " +
        "Freshness is manual — this is a snapshot at digest " + s.sourceDigest + ".";
      trust.appendChild(el("span", "acc-trust-text", line));
    }
  }

  function plural(n, word) { return n + " " + (n === 1 ? word.replace(/s$/, "") : word); }

  function card(title, target, cls) {
    var c = el("div", "acc-card" + (cls ? " " + cls : ""));
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
      var pc = card("Providers", null, "acc-card-providers");
      show.forEach(function (p) { pc.appendChild(el("span", "acc-chip", p.displayName)); });
      bento.appendChild(pc);
    }

    var inv = data.inventory || {};
    var nonEmpty = INV_ORDER.filter(function (b) { return (inv[b] || []).length; });
    if (nonEmpty.length) {
      var ic = card("Inventory", "inventory", "acc-card-inventory");
      var kpis = el("div", "acc-kpis");
      nonEmpty.forEach(function (b) {
        var k = el("div", "acc-kpi");
        k.appendChild(el("span", "acc-kpi-n", String(inv[b].length)));
        k.appendChild(el("span", "acc-kpi-l", INV_LABEL[b].toLowerCase()));
        kpis.appendChild(k);
      });
      ic.appendChild(kpis);
      bento.appendChild(ic);
    }

    var todos = (data.project && data.project.openTodos) || [];
    if (todos.length) {
      var tc = card("Open TODOs (" + todos.length + ")", "todos", "acc-card-todos");
      todos.slice(0, 3).forEach(function (t) {
        var line = el("div", "acc-card-line");
        mdInline(line, t.text, "");
        tc.appendChild(line);
      });
      // action handoff — a data-true, non-asserting next move
      var act = el("button", "acc-action");
      act.type = "button";
      act.textContent = todos.length === 1
        ? "Jump to the open TODO →"
        : "Start with the first of " + todos.length + " open TODOs →";
      act.addEventListener("click", function () { jumpTo(todos[0].id); });
      tc.appendChild(act);
      bento.appendChild(tc);
    }

    var docs = data.docs || {};
    var docCount = 0;
    Object.keys(docs).forEach(function (k) { docCount += (docs[k] || []).length; });
    if (docCount) {
      var dc = card("Docs", "docs", "acc-card-docs");
      dc.appendChild(el("div", "acc-card-line", docCount + " referenced"));
      bento.appendChild(dc);
    }

    var rels = data.relationships || [];
    if (rels.length) {
      var xc = card("Cross-references", "crossref", "acc-card-xref");
      xc.appendChild(el("div", "acc-card-line", plural(rels.length, "edges")));
      bento.appendChild(xc);
    }

    if (bento.children.length) host.appendChild(bento);
  }

  function renderBanner() {
    if (!truncated) return;
    var steps = (data.generator && data.generator.reducedSteps) || [];
    var dropped = [];
    if (steps.indexOf("bodies") !== -1) dropped.push("full doc/skill bodies");
    if (steps.indexOf("search-body") !== -1) dropped.push("body search");
    if (steps.indexOf("summaries-blanked") !== -1) dropped.push("summaries");
    var what = dropped.length ? dropped.join(" and ") : "some content";
    var msg = "Summary view — " + what + " " + (dropped.length === 1 ? "was" : "were") +
      " omitted to keep this file under the size budget. Open any item via its path link, " +
      "or re-run the dashboard on a subfolder for full bodies.";
    document.getElementById("acc-banner").appendChild(el("div", "acc-noticetext", msg));
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

  function jumpTo(id, expand) {
    var row = rowById.get(id);
    if (!row) return; // degrade: empty bucket skipped, or light/truncated mode
    // reveal a collapsed doc group so the row is actually visible
    var grp = row.closest && row.closest(".acc-group.acc-hidden");
    if (grp) grp.classList.remove("acc-hidden");
    if (expand && typeof row.__accExpand === "function") row.__accExpand();
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
    var t = el("span", "acc-rel-title");
    mdInline(t, meta.title, "");
    btn.appendChild(t);
    btn.addEventListener("click", function () { jumpTo(edge.otherId); });
    return btn;
  }

  function decorateRelated() {
    rowById.forEach(function (row, id) {
      var edges = edgesByEndpoint[id];
      if (!edges || !edges.length) return;
      var box = el("div", "acc-related");
      edges.forEach(function (e) {
        var n = relatedEntry(e);
        if (n) box.appendChild(n);
      });
      if (box.children.length) {
        // place related links above the reading pane, if any
        var detail = row.querySelector(".acc-detail");
        if (detail) row.insertBefore(box, detail);
        else row.appendChild(box);
      }
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
          mdInline(titleEl, rec.title || "", qLower);
          hit.appendChild(titleEl);
          hit.appendChild(el("span", "acc-chip", rec.typeLabel || t));
          hit.appendChild(el("span", "path", rec.path || ""));
          if ((rec.text || "") !== "") {
            var snipEl = el("span", "acc-omni-snippet");
            renderInlineInto(snipEl, snippetFor(rec, qLower), qLower);
            hit.appendChild(snipEl);
          }
          hit.addEventListener("click", function () { jumpTo(rec.id, true); });
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
        if (hits[pick]) jumpTo(hits[pick].id, true);
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

  // Scroll-spy: highlight the nav pill of the section currently in view.
  function wireScrollSpy() {
    var pills = {};
    document.querySelectorAll("nav.acc-nav a[data-spy]").forEach(function (a) {
      pills[a.getAttribute("data-spy")] = a;
    });
    var sections = Object.keys(pills)
      .map(function (id) { return document.getElementById(id); })
      .filter(Boolean);
    if (!("IntersectionObserver" in window) || !sections.length) return;
    var visible = {};
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { visible[en.target.id] = en.isIntersecting; });
      var current = sections.filter(function (s) { return visible[s.id]; })[0];
      Object.keys(pills).forEach(function (id) {
        var on = current && id === current.id;
        pills[id].classList.toggle("acc-nav-active", !!on);
        if (on) pills[id].setAttribute("aria-current", "location");
        else pills[id].removeAttribute("aria-current");
      });
    }, { rootMargin: "-96px 0px -65% 0px", threshold: 0 });
    sections.forEach(function (s) { obs.observe(s); });
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
  wireScrollSpy();
})();
