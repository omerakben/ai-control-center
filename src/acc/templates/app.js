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

  function encodedRelHref(prefix, path) {
    var raw = (prefix === "." ? path : prefix + "/" + path);
    return raw.split("/").map(function (seg) {
      return seg === "." || seg === ".." ? seg : encodeURIComponent(seg);
    }).join("/");
  }

  function itemRow(opts) {
    var row = el("div", "acc-row acc-item");
    var head = el("div", "acc-rowhead");
    if (opts.provider) head.appendChild(el("span", "acc-chip", opts.provider));
    if (opts.typeLabel) head.appendChild(el("span", "badge", opts.typeLabel));
    head.appendChild(el("span", "acc-itemtitle", opts.title));
    row.appendChild(head);
    if (opts.summary) row.appendChild(el("div", "acc-summary", opts.summary));
    if (pathPrefix) {
      var a = el("a", "path", opts.path);
      a.href = encodedRelHref(pathPrefix, opts.path);
      row.appendChild(a);
    } else {
      row.appendChild(el("span", "path", opts.path));
    }
    row.dataset.search =
      (opts.title + " " + opts.path + " " + (opts.summary || "")).toLowerCase();
    return row;
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
          typeLabel: g, title: doc.title, path: doc.path, summary: doc.summary
        }));
      });
    });
  }

  function renderTodos() {
    var host = document.getElementById("acc-todos");
    (data.project.openTodos || []).forEach(function (t) {
      host.appendChild(itemRow({ title: t.text, path: t.path }));
    });
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
  renderDocs();
  renderTodos();
  wireSearch();
})();
