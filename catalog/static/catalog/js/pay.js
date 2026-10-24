/* Thanh toán trực tuyến: trang ZaloPay mở ở tab mới, tab này tự hỏi server "đã thanh toán chưa" mỗi vài giây.
   Nhờ vậy dù trang ZaloPay bị treo / không chuyển khách về, tab này vẫn tự sang trang kết quả khi tiền đã về. */
(function () {
  "use strict";
  var INTERVAL = 4000, MAX_MS = 16 * 60 * 1000;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function start(form) {
    var url = form.getAttribute("data-status-url");
    if (!url || form.dataset.waiting) return;
    form.dataset.waiting = "1";
    var btn = form.querySelector("button[type=submit]");
    if (btn) btn.disabled = true;

    var box = el("div", "paywait");
    box.setAttribute("role", "status");
    var msg = el("p", "paywait__msg", "Đang chờ ZaloPay xác nhận thanh toán. Trang này tự cập nhật khi thanh toán xong. " +
      "Nếu tab ZaloPay bị treo, bạn có thể đóng tab đó, hệ thống vẫn tự kiểm tra.");
    var actions = el("div", "paywait__actions");
    var check = el("button", "btn btn--small", "Kiểm tra ngay");
    check.type = "button";
    var retry = el("button", "btn btn--small btn--ghost", "Thanh toán lại");
    retry.type = "button";
    retry.addEventListener("click", function () { window.location.reload(); });
    actions.appendChild(check);
    actions.appendChild(retry);
    box.appendChild(msg);
    box.appendChild(actions);
    form.parentNode.insertBefore(box, form.nextSibling);

    var started = Date.now(), timer = null, busy = false, stopped = false;

    function stop(text) {
      stopped = true;
      clearInterval(timer);
      msg.textContent = text;
      check.hidden = true;
      if (btn) btn.disabled = false;
    }

    function poll() {
      if (busy || stopped) return;
      if (Date.now() - started > MAX_MS) {
        stop("Đã hết thời gian chờ. Nếu bạn đã thanh toán, hãy mở Đơn hàng của tôi để xem kết quả.");
        return;
      }
      busy = true;
      fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          busy = false;
          if (!d) return;
          if (d.state === "paid") {
            stop("Thanh toán thành công, đang chuyển trang...");
            window.location.href = d.url;
          } else if (d.state === "failed") {
            stop("ZaloPay báo thanh toán chưa thành công hoặc đã hủy. Bạn có thể bấm Thanh toán lại trong hạn giữ kho.");
          } else if (d.state === "canceled") {
            stop("Đơn đã bị hủy (quá hạn giữ kho). Nếu bạn đã thanh toán, số tiền sẽ được hoàn lại.");
          }
        })
        .catch(function () { busy = false; });
    }

    check.addEventListener("click", poll);
    timer = setInterval(poll, INTERVAL);
  }

  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (f && f.matches && f.matches("form[data-pay]")) {
      // đợi trình duyệt mở tab mới rồi mới vô hiệu nút (nếu vô hiệu ngay, một số trình duyệt bỏ qua việc gửi form)
      setTimeout(function () { start(f); }, 400);
    }
  });
})();
