/* Shopphi: khung chatbot. Lịch sử hội thoại được lưu và nạp lại từ PostgreSQL (bảng ChatLog). */
(function () {
  "use strict";
  var box = document.getElementById("chat");
  if (!box) return;
  var log = document.getElementById("chat-log"), form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input"), ctx = document.getElementById("chat-ctx");
  var product = null, loaded = false;
  var csrf = (document.querySelector('meta[name="csrf"]') || {}).content || "";

  function add(text, who) {
    var d = document.createElement("div");
    d.className = "bubble bubble--" + who;
    d.textContent = text;           // textContent: không chèn HTML từ máy chủ
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function loadHistory() {
    if (loaded) return;
    loaded = true;
    fetch(box.dataset.history, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        (d.messages || []).forEach(function (m) { add(m.q, "me"); add(m.a, "bot"); });
        if (!log.children.length) add("Xin chào! Mình có thể giúp bạn xem giá, tồn kho, thông số hoặc gợi ý sản phẩm.", "bot");
      }).catch(function () { add("Không tải được lịch sử hội thoại.", "bot"); });
  }

  function open(btn) {
    box.hidden = false;
    var pid = btn && btn.dataset ? btn.dataset.product : null;
    product = pid || null;
    if (product) { ctx.hidden = false; ctx.textContent = "Đang hỏi về: " + btn.dataset.name; } else { ctx.hidden = true; }
    loadHistory();
    input.focus();
  }

  document.querySelectorAll("[data-chat-open]").forEach(function (b) { b.addEventListener("click", function () { open(b); }); });
  document.getElementById("chat-close").addEventListener("click", function () { box.hidden = true; });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    add(msg, "me");
    var wait = add("Đang trả lời...", "bot");
    fetch(box.dataset.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ message: msg, product_id: product })
    }).then(function (r) { return r.json(); })
      .then(function (d) { wait.textContent = d.answer || d.error || "Có lỗi, vui lòng thử lại."; })
      .catch(function () { wait.textContent = "Hiện chatbot tạm thời chưa tư vấn được."; });
  });
})();
