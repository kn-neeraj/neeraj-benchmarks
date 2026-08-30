// Renders the results chart with Observable Plot (loaded via CDN). SVG
// output, so it inherits the page's fonts/colors instead of looking like an
// embedded canvas widget. Reads data from the #results-data JSON script tag
// so the same script works for any experiment page.
(function () {
  var dataEl = document.getElementById("results-data");
  if (!dataEl || typeof Plot === "undefined") return;
  var data = JSON.parse(dataEl.textContent);
  var box = document.getElementById("results-chart");
  if (!box) return;

  var rows = data.labels.map(function (label, i) {
    return {
      label: label,
      mean: data.means[i],
      ci_low: data.ci_low[i],
      ci_high: data.ci_high[i],
      n: data.ns[i],
    };
  });

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function render() {
    box.innerHTML = "";
    var fontBody = css("--font-body") || "sans-serif";
    var fontMono = css("--font-mono") || "monospace";
    var ink = css("--ink");
    var inkFaint = css("--ink-faint");
    var grid = css("--chart-grid");
    var bar = css("--chart-bar-alpha") || css("--chart-bar");
    var ciColor = css("--chart-ci");

    var plot = Plot.plot({
      width: box.clientWidth || 640,
      height: rows.length * 64 + 40,
      marginLeft: 132,
      marginRight: 24,
      style: { background: "transparent", fontFamily: fontMono, fontSize: 12, color: inkFaint },
      x: {
        domain: [0, data.axisMax],
        grid: true,
        label: null,
        ticks: 5,
      },
      y: { domain: rows.map(function (r) { return r.label; }), label: null },
      marks: [
        Plot.gridX({ stroke: grid, strokeOpacity: 1 }),
        Plot.barX(rows, {
          x: "mean",
          y: "label",
          fill: bar,
          rx: 3,
          insetTop: 10,
          insetBottom: 10,
        }),
        Plot.ruleY(rows, {
          y: "label",
          x1: "ci_low",
          x2: "ci_high",
          stroke: ciColor,
          strokeOpacity: 0.65,
          strokeWidth: 2,
        }),
        Plot.tickX(rows, { y: "label", x: "ci_low", stroke: ciColor, strokeOpacity: 0.65, strokeWidth: 2 }),
        Plot.tickX(rows, { y: "label", x: "ci_high", stroke: ciColor, strokeOpacity: 0.65, strokeWidth: 2 }),
        Plot.text(rows, {
          x: "mean",
          y: "label",
          text: function (r) { return r.mean.toFixed(3); },
          dx: 14,
          fill: ink,
          fontFamily: fontMono,
          fontWeight: 600,
          fontSize: 13,
          textAnchor: "start",
        }),
        Plot.tip(
          rows,
          Plot.pointer({
            x: "mean",
            y: "label",
            title: function (r) {
              return (
                data.metricName + ": " + r.mean.toFixed(3) +
                "\n95% CI: [" + r.ci_low.toFixed(3) + ", " + r.ci_high.toFixed(3) + "]" +
                "\nn = " + r.n
              );
            },
          })
        ),
      ],
    });

    plot.style.fontFamily = fontBody;
    box.appendChild(plot);
  }

  render();
  window.addEventListener("resize", debounce(render, 200));
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);

  function debounce(fn, ms) {
    var t;
    return function () {
      clearTimeout(t);
      t = setTimeout(fn, ms);
    };
  }
})();
