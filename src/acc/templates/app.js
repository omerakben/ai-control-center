(function () {
  var node = document.getElementById("acc-data");
  var data = JSON.parse(node.textContent);

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
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
        var row = el("div", "acc-row acc-item");
        row.appendChild(el("span", null, doc.title));
        row.appendChild(document.createTextNode(" "));
        row.appendChild(el("span", "badge", g));
        row.appendChild(document.createTextNode(" "));
        row.appendChild(el("span", "path", doc.path));
        row.dataset.search = (doc.title + " " + doc.path + " " + (doc.summary || "")).toLowerCase();
        host.appendChild(row);
      });
    });
  }

  function renderTodos() {
    var host = document.getElementById("acc-todos");
    (data.project.openTodos || []).forEach(function (t) {
      var row = el("div", "acc-row acc-item", t.text + "  —  " + t.path);
      row.dataset.search = (t.text + " " + t.path).toLowerCase();
      host.appendChild(row);
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
