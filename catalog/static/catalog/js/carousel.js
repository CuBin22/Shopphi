(function () {
  "use strict";
  document.querySelectorAll("[data-carousel]").forEach(function (carousel) {
    var slides = Array.from(carousel.querySelectorAll("[data-slide]"));
    if (slides.length < 2) return;
    var dots = Array.from(carousel.querySelectorAll("[data-carousel-dot]"));
    var pause = carousel.querySelector("[data-carousel-pause]");
    var motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    var index = 0, timer = null, paused = motion.matches, hovering = false;

    function show(next) {
      index = (next + slides.length) % slides.length;
      slides.forEach(function (slide, i) { slide.hidden = i !== index; });
      dots.forEach(function (dot, i) { dot.setAttribute("aria-current", String(i === index)); });
    }

    function schedule() {
      clearInterval(timer);
      var playing = !paused && !hovering && !document.hidden && !carousel.contains(document.activeElement);
      carousel.querySelector(".carousel__slides").setAttribute("aria-live", playing ? "off" : "polite");
      if (playing) timer = setInterval(function () { show(index + 1); }, 5000);
      pause.textContent = paused ? "Tự chuyển" : "Tạm dừng";
      pause.setAttribute("aria-label", paused ? "Bật tự chuyển banner" : "Tạm dừng tự chuyển banner");
    }

    carousel.querySelector("[data-carousel-controls]").hidden = false;
    carousel.querySelector("[data-carousel-prev]").addEventListener("click", function () { show(index - 1); schedule(); });
    carousel.querySelector("[data-carousel-next]").addEventListener("click", function () { show(index + 1); schedule(); });
    dots.forEach(function (dot, i) { dot.addEventListener("click", function () { show(i); schedule(); }); });
    pause.addEventListener("click", function () { paused = !paused; schedule(); });
    carousel.addEventListener("mouseenter", function () { hovering = true; schedule(); });
    carousel.addEventListener("mouseleave", function () { hovering = false; schedule(); });
    carousel.addEventListener("focusin", schedule);
    carousel.addEventListener("focusout", function () { setTimeout(schedule, 0); });
    document.addEventListener("visibilitychange", schedule);
    motion.addEventListener("change", function () { paused = motion.matches; schedule(); });
    schedule();
  });
})();
