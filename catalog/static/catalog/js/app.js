/* Shopphi: gợi ý từ khóa tức thời, chọn biến thể và số lượng ở trang chi tiết. */
(function () {
  "use strict";

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function plain(s) {
    return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
  }

  // Tô đậm phần người dùng đã gõ (so khớp không dấu, giữ nguyên chữ có dấu khi hiển thị).
  function highlight(text, typed) {
    var t = plain(typed.trim());
    var idx = t ? plain(text).indexOf(t) : -1;
    if (idx < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, idx)) + "<mark>" + escapeHtml(text.slice(idx, idx + t.length)) + "</mark>" +
      escapeHtml(text.slice(idx + t.length));
  }

  function initSearch(form) {
    var input = form.querySelector('input[name="q"]');
    var flag = form.querySelector('input[name="goi_y"]');
    var box = form.querySelector(".suggest");
    var url = form.getAttribute("data-url");
    var timer = null, controller = null, items = [], active = -1;

    function close() {
      box.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function setActive(i) {
      var lis = box.querySelectorAll("li");
      lis.forEach(function (li, n) { li.setAttribute("aria-selected", n === i ? "true" : "false"); });
      active = i;
      if (i >= 0) input.setAttribute("aria-activedescendant", lis[i].id);
    }

    function choose(i) {
      input.value = items[i];
      flag.value = "1";
      close();
      form.submit();
    }

    function render(list) {
      items = list;
      if (!list.length) { close(); return; }
      var typed = input.value;
      box.innerHTML = list.map(function (p, i) {
        return '<li role="option" id="' + box.id + "-" + i + '" aria-selected="false" data-i="' + i + '">' +
          highlight(p, typed) + "</li>";
      }).join("");
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
      active = -1;
    }

    function fetchSuggest() {
      var q = input.value.trim();
      if (!q) { close(); return; }
      if (controller) controller.abort();
      controller = new AbortController();
      fetch(url + "?q=" + encodeURIComponent(q), { signal: controller.signal, headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (d) { render(d.suggestions || []); })
        .catch(function () { /* hủy hoặc lỗi mạng: bỏ qua, người dùng vẫn gửi truy vấn bình thường */ });
    }

    input.addEventListener("input", function () {
      flag.value = "0";
      clearTimeout(timer);
      timer = setTimeout(fetchSuggest, 80);
    });

    input.addEventListener("keydown", function (e) {
      if (box.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive((active + 1) % items.length); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive((active - 1 + items.length) % items.length); }
      else if (e.key === "Enter" && active >= 0) { e.preventDefault(); choose(active); }
      else if (e.key === "Escape") { close(); }
    });

    box.addEventListener("mousedown", function (e) {
      var li = e.target.closest("li");
      if (li) { e.preventDefault(); choose(parseInt(li.getAttribute("data-i"), 10)); }
    });

    document.addEventListener("click", function (e) { if (!form.contains(e.target)) close(); });
  }

  function initBuy() {
    var form = document.getElementById("buy");
    if (!form) return;
    var price = document.getElementById("price");
    var stock = document.getElementById("stock");
    var qty = document.getElementById("qty");
    var add = document.getElementById("add");

    function current() { return form.querySelector('input[name="variant"]:checked'); }

    function sync() {
      var v = current();
      if (!v) return;
      var s = parseInt(v.getAttribute("data-stock"), 10);
      price.textContent = v.getAttribute("data-price");
      stock.textContent = s > 0 ? "Còn " + s + " sản phẩm" : "Hết hàng";
      stock.classList.toggle("is-out", s <= 0);
      add.disabled = s <= 0;
      qty.max = s > 0 ? s : 1;
      if (parseInt(qty.value, 10) > s && s > 0) qty.value = s;
    }

    form.querySelectorAll('input[name="variant"]').forEach(function (r) { r.addEventListener("change", sync); });
    form.querySelectorAll("[data-qty]").forEach(function (b) {
      b.addEventListener("click", function () {
        var n = (parseInt(qty.value, 10) || 1) + parseInt(b.getAttribute("data-qty"), 10);
        var max = parseInt(qty.max, 10) || 1;
        qty.value = Math.min(Math.max(1, n), max);
      });
    });
    sync();
  }

  document.querySelectorAll("[data-search]").forEach(initSearch);
  initBuy();
})();
