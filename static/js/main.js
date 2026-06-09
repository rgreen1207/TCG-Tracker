/* ── Sidebar mobile toggle ─────────────────────────────────── */
const sidebar  = document.querySelector('.sidebar');
const overlay  = document.querySelector('.sidebar-overlay');
const navToggle = document.querySelector('.nav-toggle');

if (navToggle) {
  navToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
  });
}
if (overlay) {
  overlay.addEventListener('click', () => {
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
  });
}

/* ── Poller status indicator ───────────────────────────────── */
const dot       = document.getElementById('status-dot');
const statusTxt = document.getElementById('status-label');
const pollInfo  = document.getElementById('poll-info');

async function refreshStatus() {
  try {
    const r = await fetch('/api/prices/status');
    if (!r.ok) throw new Error();
    const d = await r.json();

    if (dot) {
      dot.className = 'status-indicator ' + (d.running ? 'polling' : 'online');
    }
    if (statusTxt) {
      statusTxt.textContent = d.running ? 'Polling…' : 'Online';
    }
    if (pollInfo) {
      const nextRun = d.next_run ? new Date(d.next_run).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '—';
      const lastRun = d.last_run ? new Date(d.last_run).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : 'never';
      pollInfo.textContent = `Last: ${lastRun} · Next: ${nextRun}`;
    }
  } catch {
    if (dot) dot.className = 'status-indicator error';
    if (statusTxt) statusTxt.textContent = 'Error';
  }
}

refreshStatus();
setInterval(refreshStatus, 30_000);

/* ── Manual poll trigger ───────────────────────────────────── */
const triggerBtn = document.getElementById('btn-poll-now');
if (triggerBtn) {
  triggerBtn.addEventListener('click', async () => {
    triggerBtn.disabled = true;
    triggerBtn.textContent = '⟳ Polling…';
    try {
      await fetch('/api/prices/poll/trigger', { method: 'POST' });
      setTimeout(() => { triggerBtn.disabled = false; triggerBtn.textContent = '⟳ Poll Now'; refreshStatus(); }, 3000);
    } catch {
      triggerBtn.disabled = false;
      triggerBtn.textContent = '⟳ Poll Now';
    }
  });
}

/* ── Generic modal helpers ─────────────────────────────────── */
window.openModal = (id) => {
  const m = document.getElementById(id);
  if (m) m.classList.add('open');
};
window.closeModal = (id) => {
  const m = document.getElementById(id);
  if (m) m.classList.remove('open');
};
document.querySelectorAll('.modal-backdrop').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
});


/* ── Flash messages (auto-dismiss) ─────────────────────────── */
document.querySelectorAll('.flash').forEach(el => {
  setTimeout(() => el.remove(), 4000);
});
