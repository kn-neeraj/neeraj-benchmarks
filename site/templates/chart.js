// Renders the results bar chart using Chart.js (loaded via CDN), with a
// small custom plugin drawing 95%-CI whiskers on top of each bar. Reads
// data from the #results-data JSON script tag so the same script works for
// any experiment page.
(function () {
  window.__chartDiag = { step: "start" };
  try {
    __chartInit();
  } catch (e) {
    window.__chartDiag.error = e.message + "\n" + e.stack;
  }

  function __chartInit() {
  window.__chartDiag.step = "guard-check";
  var dataEl = document.getElementById("results-data");
  window.__chartDiag.hasDataEl = !!dataEl;
  window.__chartDiag.chartType = typeof Chart;
  if (!dataEl || typeof Chart === "undefined") return;
  var data = JSON.parse(dataEl.textContent);
  var canvas = document.getElementById("results-chart");
  if (!canvas) return;
  window.__chartDiag.step = "guards-passed";

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var styles = getComputedStyle(document.documentElement);
  var css = function (name) { return styles.getPropertyValue(name).trim(); };

  var ciWhiskerPlugin = {
    id: "ciWhisker",
    afterDatasetsDraw: function (chart) {
      var meta = chart.getDatasetMeta(0);
      var ctx = chart.ctx;
      var xScale = chart.scales.x;
      var ciColor = css("--chart-ci") || "#131311";
      ctx.save();
      ctx.strokeStyle = ciColor;
      ctx.globalAlpha = 0.65;
      ctx.lineWidth = 2;
      meta.data.forEach(function (bar, i) {
        var low = xScale.getPixelForValue(data.ci_low[i]);
        var high = xScale.getPixelForValue(data.ci_high[i]);
        var y = bar.y;
        var capHalf = 5;
        ctx.beginPath();
        ctx.moveTo(low, y);
        ctx.lineTo(high, y);
        ctx.moveTo(low, y - capHalf);
        ctx.lineTo(low, y + capHalf);
        ctx.moveTo(high, y - capHalf);
        ctx.lineTo(high, y + capHalf);
        ctx.stroke();
      });
      ctx.restore();
    },
  };

  function buildChart() {
    var s = getComputedStyle(document.documentElement);
    var get = function (name) { return s.getPropertyValue(name).trim(); };
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: data.metricName,
            data: data.means,
            backgroundColor: get("--chart-bar-alpha") || get("--chart-bar"),
            borderRadius: 3,
            barThickness: 26,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: reducedMotion ? false : { duration: 550, easing: "easeOutQuart" },
        layout: { padding: { right: 12 } },
        scales: {
          x: {
            min: 0,
            max: data.axisMax,
            grid: { color: get("--chart-grid"), drawTicks: false },
            border: { display: false },
            ticks: { color: get("--ink-faint"), font: { family: get("--font-mono"), size: 11 } },
          },
          y: {
            grid: { display: false },
            border: { display: false },
            ticks: { color: get("--ink"), font: { family: get("--font-mono"), size: 12, weight: "600" } },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: get("--surface"),
            titleColor: get("--ink"),
            bodyColor: get("--ink-muted"),
            borderColor: get("--border"),
            borderWidth: 1,
            padding: 10,
            titleFont: { family: get("--font-mono"), size: 12 },
            bodyFont: { family: get("--font-mono"), size: 11 },
            callbacks: {
              label: function (ctx) {
                var i = ctx.dataIndex;
                return [
                  data.metricName + ": " + data.means[i].toFixed(3),
                  "95% CI: [" + data.ci_low[i].toFixed(3) + ", " + data.ci_high[i].toFixed(3) + "]",
                  "n = " + data.ns[i],
                ];
              },
              title: function () { return ""; },
            },
          },
        },
      },
      plugins: [ciWhiskerPlugin],
    });
  }

  window.__chartDiag.step = "before-build";
  var chart = buildChart();
  window.__chartDiag.step = "after-build";
  window.__chartDiag.instanceId = chart && chart.id;

  // Chart.js bakes colors in at construction time, so a light/dark toggle
  // needs a full rebuild rather than a live restyle.
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
    chart.destroy();
    chart = buildChart();
  });
  window.__chartDiag.step = "done";
  }
})();
