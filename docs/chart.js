// Renders one Chart.js bar chart per [data-chart-data] script tag on the
// page (paired with its canvas via a matching data-chart-canvas="<id>"
// attribute), with a small custom plugin drawing 95%-CI whiskers on top of
// each bar. A page can have any number of these - e.g. a "reasoning off" /
// "reasoning on" pair of charts - each gets its own independent instance.
(function () {
  if (typeof Chart === "undefined") return;

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function makeCiWhiskerPlugin(data) {
    return {
      id: "ciWhisker",
      afterDatasetsDraw: function (chart) {
        var styles = getComputedStyle(document.documentElement);
        var css = function (name) { return styles.getPropertyValue(name).trim(); };
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
  }

  function buildChart(canvas, data) {
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
      plugins: [makeCiWhiskerPlugin(data)],
    });
  }

  var instances = [];
  document.querySelectorAll("[data-chart-data]").forEach(function (dataEl) {
    var id = dataEl.getAttribute("data-chart-data");
    var canvas = document.querySelector('[data-chart-canvas="' + id + '"]');
    if (!canvas) return;
    var data = JSON.parse(dataEl.textContent);
    instances.push({ canvas: canvas, data: data, chart: buildChart(canvas, data) });
  });

  // Chart.js bakes colors in at construction time, so a theme switch needs
  // a full rebuild rather than a live restyle. Covers both the OS setting
  // changing and the manual toggle in theme.js (which fires "themechange").
  function rebuildAll() {
    instances.forEach(function (inst) {
      inst.chart.destroy();
      inst.chart = buildChart(inst.canvas, inst.data);
    });
  }
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rebuildAll);
  window.addEventListener("themechange", rebuildAll);
})();
