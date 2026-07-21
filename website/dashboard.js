/* ==========================================
   MIXUP FUNCTIONAL ANALYTICS DASHBOARD ENGINE
   v2.0 - Fetches real data from backend API
   ========================================== */

// Backend API base URL - auto-detect local vs production
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? `${window.location.protocol}//${window.location.hostname}:8081`
  : 'https://ai-telephony-agent.onrender.com';

let mainChart = null;
let allCallLogs = [];

document.addEventListener('DOMContentLoaded', () => {
  fetchDashboardData();
  setupEvents();
});

// ========================================
// DATA FETCHING
// ========================================

async function fetchDashboardData() {
  try {
    // Fetch analytics data from backend
    const [analyticsRes, logsRes] = await Promise.allSettled([
      fetch(`${API_BASE}/api/analytics`),
      fetch(`${API_BASE}/api/call-logs`)
    ]);

    let analytics = null;
    let logs = [];

    if (analyticsRes.status === 'fulfilled' && analyticsRes.value.ok) {
      analytics = await analyticsRes.value.json();
    }

    if (logsRes.status === 'fulfilled' && logsRes.value.ok) {
      logs = await logsRes.value.json();
    }

    allCallLogs = logs;
    updateKPIs(analytics, logs);
    initChart(logs);
    renderFeed(logs);
    updateSourceBreakdown(analytics);

  } catch (err) {
    console.error('Failed to fetch dashboard data:', err);
    showEmptyStates();
  }
}

function refreshDashboard() {
  const btn = document.querySelector('.dash-refresh-btn');
  if (btn) {
    btn.classList.add('spinning');
    setTimeout(() => btn.classList.remove('spinning'), 1000);
  }
  fetchDashboardData();
}

// ========================================
// KPI UPDATES
// ========================================

function updateKPIs(analytics, logs) {
  const totalCalls = analytics ? analytics.total_calls : logs.length;
  const successRate = analytics ? analytics.success_rate : 0;
  const sentiment = analytics ? analytics.sentiment_score : 0;
  const avgDuration = analytics ? analytics.avg_duration : '--';

  document.getElementById('kpiCalls').innerText = totalCalls.toLocaleString();
  document.getElementById('kpiSuccessRate').innerText = `${successRate}%`;
  document.getElementById('kpiAvgTime').innerText = avgDuration;
  document.getElementById('kpiSentiment').innerText = `${sentiment}%`;

  // Update badges
  const callsBadge = document.getElementById('kpiCallsBadge');
  const successBadge = document.getElementById('kpiSuccessBadge');
  const sentimentBadge = document.getElementById('kpiSentimentBadge');

  if (callsBadge) {
    callsBadge.innerText = totalCalls > 0 ? `${totalCalls} total` : 'No data';
  }
  if (successBadge) {
    const completed = logs.filter(l => l.status === 'completed').length;
    successBadge.innerText = completed > 0 ? `${completed} done` : 'No data';
  }
  if (sentimentBadge) {
    sentimentBadge.innerText = sentiment > 0 ? `Score ${sentiment}` : 'No data';
  }
}

function updateSourceBreakdown(analytics) {
  const ctaEl = document.getElementById('ctaCallCount');
  const instantEl = document.getElementById('instantCallCount');

  if (analytics) {
    if (ctaEl) ctaEl.innerText = analytics.cta_calls || 0;
    if (instantEl) instantEl.innerText = analytics.instant_calls || 0;
  }
}

// ========================================
// CHART
// ========================================

function initChart(logs) {
  const canvas = document.getElementById('simpleChart');
  const emptyState = document.getElementById('chartEmptyState');
  if (!canvas) return;

  if (!logs || logs.length === 0) {
    canvas.style.display = 'none';
    if (emptyState) emptyState.style.display = 'flex';
    return;
  }

  canvas.style.display = 'block';
  if (emptyState) emptyState.style.display = 'none';

  // Group calls by date
  const callsByDate = {};
  logs.forEach(log => {
    const date = new Date(log.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    callsByDate[date] = (callsByDate[date] || 0) + 1;
  });

  const labels = Object.keys(callsByDate).reverse().slice(-14); // last 14 dates
  const data = labels.map(d => callsByDate[d] || 0);

  const ctx = canvas.getContext('2d');

  const gradCalls = ctx.createLinearGradient(0, 0, 0, 300);
  gradCalls.addColorStop(0, 'rgba(255, 80, 101, 0.25)');
  gradCalls.addColorStop(1, 'rgba(255, 80, 101, 0.0)');

  if (mainChart) {
    mainChart.data.labels = labels;
    mainChart.data.datasets[0].data = data;
    mainChart.update();
    return;
  }

  mainChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Calls',
          data: data,
          borderColor: '#ff5065',
          backgroundColor: gradCalls,
          borderWidth: 3,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#ff5065',
          pointHoverRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          align: 'end',
          labels: {
            boxWidth: 12,
            font: { family: 'Sora', size: 12, weight: '600' },
            color: '#666666'
          }
        },
        tooltip: {
          backgroundColor: '#0e0f10',
          titleFont: { family: 'Sora', size: 13, weight: '700' },
          bodyFont: { family: 'JetBrains Mono', size: 12 },
          padding: 12,
          cornerRadius: 10
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Sora', size: 12 }, color: '#7a7b7c' }
        },
        y: {
          grid: { color: 'rgba(0, 0, 0, 0.05)' },
          ticks: {
            font: { family: 'JetBrains Mono', size: 11 },
            color: '#7a7b7c',
            stepSize: 1
          },
          beginAtZero: true
        }
      }
    }
  });
}

// ========================================
// CALL FEED
// ========================================

function renderFeed(logs) {
  const container = document.getElementById('callFeed');
  const emptyState = document.getElementById('feedEmptyState');
  if (!container) return;

  if (!logs || logs.length === 0) {
    container.innerHTML = '';
    if (emptyState) emptyState.style.display = 'flex';
    return;
  }

  if (emptyState) emptyState.style.display = 'none';
  container.innerHTML = '';

  const recentCalls = logs.slice(0, 20); // Show last 20

  recentCalls.forEach(call => {
    const name = call.name || 'Unknown Caller';
    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    const phone = call.phone || '--';
    const source = call.source === 'cta_form' ? 'CTA Form' : 'Instant Call';
    const sentiment = call.sentiment || 'Completed';
    const tagClass = sentiment === 'Delighted' ? 'dash-tag-delighted' :
                     sentiment === 'Interested' ? 'dash-tag-interested' :
                     'dash-tag-completed';
    const timeAgo = getTimeAgo(call.timestamp);
    const duration = call.duration || '1m 00s';

    const div = document.createElement('div');
    div.className = 'dash-feed-item';
    div.onclick = () => openModal(call);
    div.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px;">
        <div class="dash-avatar">${initials}</div>
        <div class="dash-caller-info">
          <span class="dash-caller-name">${escapeHtml(name)}</span>
          <span class="dash-caller-meta">${escapeHtml(phone)} &middot; ${escapeHtml(source)}</span>
        </div>
      </div>
      <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
        <span class="${tagClass}">${escapeHtml(sentiment)}</span>
        <span style="font-size: 11px; color: #7a7b7c; font-family: 'JetBrains Mono', monospace;">${escapeHtml(timeAgo)}</span>
      </div>
    `;
    container.appendChild(div);
  });
}

// ========================================
// CALL DETAIL MODAL
// ========================================

function openModal(call) {
  const modal = document.getElementById('callModal');
  if (!modal) return;

  const name = call.name || 'Unknown Caller';
  const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
  const phone = call.phone || '--';
  const source = call.source === 'cta_form' ? 'CTA Form' : 'Instant Call';
  const duration = call.duration || '1m 00s';

  document.getElementById('modalAvatar').innerText = initials;
  document.getElementById('modalName').innerText = name;
  document.getElementById('modalMeta').innerText = `${phone} \u2022 ${source} \u2022 Duration: ${duration}`;

  const chatList = document.getElementById('modalChatList');

  if (call.transcript && call.transcript.length > 0) {
    chatList.innerHTML = call.transcript.map(msg => {
      const isAgent = msg.speaker === 'agent';
      const speakerIcon = isAgent
        ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
        : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
      const speakerName = msg.name || (isAgent ? 'AI Agent' : name);
      return `
        <div class="dash-bubble ${isAgent ? 'agent' : 'customer'}">
          <span class="dash-bubble-speaker">${speakerIcon} ${escapeHtml(speakerName)}</span>
          ${escapeHtml(msg.text)}
        </div>
      `;
    }).join('');
  } else {
    chatList.innerHTML = `
      <div class="dash-empty-state" style="padding: 20px;">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-slate, #7a7b7c)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <p>No transcript available for this call.</p>
      </div>
    `;
  }

  modal.classList.add('active');
}

function closeModal() {
  const modal = document.getElementById('callModal');
  if (modal) modal.classList.remove('active');
}

// Close modal on outside click
document.addEventListener('click', (e) => {
  const modal = document.getElementById('callModal');
  if (modal && modal.classList.contains('active') && e.target === modal) {
    closeModal();
  }
});

// ========================================
// EMPTY STATES
// ========================================

function showEmptyStates() {
  const chartCanvas = document.getElementById('simpleChart');
  const chartEmpty = document.getElementById('chartEmptyState');
  const feedEmpty = document.getElementById('feedEmptyState');

  if (chartCanvas) chartCanvas.style.display = 'none';
  if (chartEmpty) chartEmpty.style.display = 'flex';
  if (feedEmpty) feedEmpty.style.display = 'flex';

  document.getElementById('kpiCalls').innerText = '0';
  document.getElementById('kpiSuccessRate').innerText = '0%';
  document.getElementById('kpiAvgTime').innerText = '--';
  document.getElementById('kpiSentiment').innerText = '0%';
}

// ========================================
// EVENTS
// ========================================

function setupEvents() {
  // Time filter buttons (for now, all show the same data since backend doesn't filter by time)
  document.querySelectorAll('.dash-filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.dash-filter-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');

      const range = e.target.getAttribute('data-range');
      filterByTimeRange(range);
    });
  });
}

function filterByTimeRange(range) {
  if (!allCallLogs || allCallLogs.length === 0) return;

  const now = new Date();
  let filtered = allCallLogs;

  if (range === 'today') {
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    filtered = allCallLogs.filter(l => new Date(l.timestamp) >= todayStart);
  } else if (range === '7d') {
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    filtered = allCallLogs.filter(l => new Date(l.timestamp) >= weekAgo);
  } else if (range === '30d') {
    const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    filtered = allCallLogs.filter(l => new Date(l.timestamp) >= monthAgo);
  }
  // 'all' shows everything

  // Update KPIs for filtered data
  const totalCalls = filtered.length;
  const completed = filtered.filter(l => l.status === 'completed').length;
  const successRate = totalCalls > 0 ? Math.round((completed / totalCalls) * 100 * 10) / 10 : 0;
  const delighted = filtered.filter(l => l.sentiment === 'Delighted').length;
  const interested = filtered.filter(l => l.sentiment === 'Interested').length;
  const sentiment = totalCalls > 0 ? Math.min(Math.round(((delighted + interested * 0.7) / totalCalls) * 100 * 10) / 10, 100) : 0;

  document.getElementById('kpiCalls').innerText = totalCalls.toLocaleString();
  document.getElementById('kpiSuccessRate').innerText = `${successRate}%`;
  document.getElementById('kpiSentiment').innerText = `${sentiment}%`;

  const callsBadge = document.getElementById('kpiCallsBadge');
  const successBadge = document.getElementById('kpiSuccessBadge');
  const sentimentBadge = document.getElementById('kpiSentimentBadge');

  if (callsBadge) callsBadge.innerText = totalCalls > 0 ? `${totalCalls} total` : 'No data';
  if (successBadge) successBadge.innerText = completed > 0 ? `${completed} done` : 'No data';
  if (sentimentBadge) sentimentBadge.innerText = sentiment > 0 ? `Score ${sentiment}` : 'No data';

  // Update source breakdown
  const ctaEl = document.getElementById('ctaCallCount');
  const instantEl = document.getElementById('instantCallCount');
  if (ctaEl) ctaEl.innerText = filtered.filter(l => l.source === 'cta_form').length;
  if (instantEl) instantEl.innerText = filtered.filter(l => l.source === 'instant_call').length;

  // Update chart
  initChart(filtered);
  renderFeed(filtered);
}

// ========================================
// UTILITIES
// ========================================

function getTimeAgo(timestamp) {
  if (!timestamp) return '--';
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return then.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// Auto-refresh every 30 seconds
setInterval(() => {
  fetchDashboardData();
}, 30000);
