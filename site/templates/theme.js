// Light/dark toggle. Explicit choices persist in localStorage and override
// the OS preference in either direction; with no stored choice, the OS
// setting (prefers-color-scheme, handled entirely in CSS) still applies.
(function () {
  var STORAGE_KEY = "theme";

  function systemPref() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function stored() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function resolved() {
    return stored() || systemPref();
  }

  function updateLabel(btn) {
    var theme = resolved();
    btn.textContent = theme === "dark" ? "LIGHT" : "DARK";
    btn.setAttribute("aria-label", "Switch to " + (theme === "dark" ? "light" : "dark") + " theme");
  }

  function apply(theme) {
    if (theme) {
      document.documentElement.setAttribute("data-theme", theme);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    updateLabel(btn);

    btn.addEventListener("click", function () {
      var next = resolved() === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (e) {}
      apply(next);
      updateLabel(btn);
      window.dispatchEvent(new Event("themechange"));
    });

    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
      if (!stored()) updateLabel(btn);
    });
  });
})();
