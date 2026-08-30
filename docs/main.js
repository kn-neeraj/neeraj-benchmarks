document.documentElement.classList.remove("no-js");

// Scroll-reveal for [data-reveal] elements (index rows, methodology steps).
// These are visible by default in CSS; this only adds a fade-up
// enhancement, and only once an IntersectionObserver is actually about to
// watch each element -- so there is never a window where content is
// hidden without something committed to eventually showing it.
(function reveal() {
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var items = document.querySelectorAll("[data-reveal]");
  if (reduced || !items.length || !("IntersectionObserver" in window)) return;

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

  items.forEach(function (el) {
    el.classList.add("js-reveal-ready");
    io.observe(el);
  });
})();
