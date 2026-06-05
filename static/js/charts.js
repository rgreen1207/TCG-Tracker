/* ── Sparkline charts via Chart.js ──────────────────────────
   Call renderSparkline(canvasId, itemType, itemId) after DOM load.
─────────────────────────────────────────────────────────── */

async function renderSparkline(canvasId, itemType, itemId, days = 30) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  try {
    const r = await fetch(`/api/prices/sparkline/${itemType}/${itemId}?days=${days}`);
    if (!r.ok) return;
    const data = await r.json();
    if (!data || data.length < 2) return;

    const labels = data.map(d => d.day);
    const values = data.map(d => d.min_usd);

    // Determine color based on trend
    const trend = values[values.length - 1] - values[0];
    const lineColor = trend <= 0 ? '#00e676' : '#ff4d6d';
    const fillColor = trend <= 0 ? 'rgba(0,230,118,0.08)' : 'rgba(255,77,109,0.08)';

    new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data: values,
          borderColor: lineColor,
          backgroundColor: fillColor,
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 3,
          fill: true,
          tension: 0.4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            label: ctx => `$${ctx.parsed.y.toFixed(2)}`,
          },
          backgroundColor: '#0c1018',
          borderColor: '#1a2640',
          borderWidth: 1,
          titleColor: '#6a86a6',
          bodyColor: '#d4e4f7',
        }},
        scales: {
          x: { display: false },
          y: {
            display: false,
            min: Math.min(...values) * 0.97,
            max: Math.max(...values) * 1.03,
          },
        },
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
      },
    });
  } catch (e) {
    console.warn('Sparkline failed for', canvasId, e);
  }
}
