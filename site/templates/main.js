document.documentElement.classList.remove("no-js");

// Scroll-reveal for [data-reveal] elements, staggered by DOM order within
// their parent. Skips entirely under prefers-reduced-motion (CSS already
// shows everything by default in that case).
(function reveal() {
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var items = document.querySelectorAll("[data-reveal]");
  if (reduced || !("IntersectionObserver" in window)) {
    items.forEach(function (el) { el.classList.add("is-visible"); });
    return;
  }
  var groups = {};
  items.forEach(function (el) {
    var key = el.dataset.revealGroup || "default";
    (groups[key] = groups[key] || []).push(el);
  });
  Object.keys(groups).forEach(function (key) {
    groups[key].forEach(function (el, i) {
      el.style.transitionDelay = Math.min(i * 60, 420) + "ms";
    });
  });
  var io = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
  );
  items.forEach(function (el) { io.observe(el); });
})();
