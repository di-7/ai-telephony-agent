/* ==========================================
   MIXUP CLEAN ANALYTICS DASHBOARD ENGINE
   ========================================== */

const DATA_SETS = {
  today: {
    calls: '1,420',
    qualRate: '74.2%',
    avgTime: '3m 12s',
    sentiment: '96.1%',
    labels: ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00'],
    chartCalls: [180, 310, 450, 620, 890, 1180, 1420],
    chartQual: [130, 230, 340, 460, 650, 880, 1053]
  },
  '7d': {
    calls: '24,850',
    qualRate: '72.5%',
    avgTime: '3m 34s',
    sentiment: '95.0%',
    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    chartCalls: [2900, 3400, 3100, 4200, 4800, 3200, 3250],
    chartQual: [2100, 2450, 2250, 3050, 3500, 2300, 2350]
  },
  '30d': {
    calls: '148,920',
    qualRate: '71.8%',
    avgTime: '3m 48s',
    sentiment: '94.2%',
    labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
    chartCalls: [31000, 36500, 39200, 42220],
    chartQual: [22320, 26280, 28145, 30345]
  },
  all: {
    calls: '420,150',
    qualRate: '73.1%',
    avgTime: '3m 42s',
    sentiment: '95.4%',
    labels: ['Q1', 'Q2', 'Q3', 'Q4'],
    chartCalls: [85000, 102000, 115000, 118150],
    chartQual: [62050, 74560, 84060, 86360]
  }
};

const SAMPLE_CALLS = [
  { id: '1', name: 'David Miller', phone: '+1 (555) 234-8901', campaign: 'SaaS Lead Gen', duration: '4m 12s', sentiment: 'Delighted', tagClass: 'dash-tag-delighted', time: '5 mins ago' },
  { id: '2', name: 'Amanda Chen', phone: '+1 (555) 876-1234', campaign: 'E-Commerce Winback', duration: '2m 45s', sentiment: 'Interested', tagClass: 'dash-tag-interested', time: '12 mins ago' },
  { id: '3', name: 'Marcus Vance', phone: '+1 (555) 432-9087', campaign: 'Healthcare Scheduler', duration: '3m 18s', sentiment: 'Delighted', tagClass: 'dash-tag-delighted', time: '24 mins ago' },
  { id: '4', name: 'Jessica Taylor', phone: '+1 (555) 789-3412', campaign: 'Real Estate Outreach', duration: '5m 02s', sentiment: 'Interested', tagClass: 'dash-tag-interested', time: '38 mins ago' },
  { id: '5', name: 'Sophia Martinez', phone: '+1 (555) 321-6549', campaign: 'SaaS Lead Gen', duration: '4m 30s', sentiment: 'Delighted', tagClass: 'dash-tag-delighted', time: '1 hour ago' }
];

let mainChart = null;

document.addEventListener('DOMContentLoaded', () => {
  initChart();
  renderFeed();
  setupEvents();
});

function initChart() {
  const ctx = document.getElementById('simpleChart').getContext('2d');
  
  const gradCalls = ctx.createLinearGradient(0, 0, 0, 300);
  gradCalls.addColorStop(0, 'rgba(255, 80, 101, 0.25)');
  gradCalls.addColorStop(1, 'rgba(255, 80, 101, 0.0)');

  const gradQual = ctx.createLinearGradient(0, 0, 0, 300);
  gradQual.addColorStop(0, 'rgba(16, 185, 129, 0.2)');
  gradQual.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

  mainChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: DATA_SETS['30d'].labels,
      datasets: [
        {
          label: 'Total AI Calls',
          data: DATA_SETS['30d'].chartCalls,
          borderColor: '#ff5065',
          backgroundColor: gradCalls,
          borderWidth: 3,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#ff5065'
        },
        {
          label: 'Qualified Leads',
          data: DATA_SETS['30d'].chartQual,
          borderColor: '#10b981',
          backgroundColor: gradQual,
          borderWidth: 3,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#10b981'
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
          ticks: { font: { family: 'JetBrains Mono', size: 11 }, color: '#7a7b7c' }
        }
      }
    }
  });
}

function setTimeRange(key, btnEl) {
  document.querySelectorAll('.dash-filter-btn').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');

  const data = DATA_SETS[key] || DATA_SETS['30d'];
  document.getElementById('kpiCalls').innerText = data.calls;
  document.getElementById('kpiQualRate').innerText = data.qualRate;
  document.getElementById('kpiAvgTime').innerText = data.avgTime;
  document.getElementById('kpiSentiment').innerText = data.sentiment;

  if (mainChart) {
    mainChart.data.labels = data.labels;
    mainChart.data.datasets[0].data = data.chartCalls;
    mainChart.data.datasets[1].data = data.chartQual;
    mainChart.update();
  }
}

function renderFeed() {
  const container = document.getElementById('callFeed');
  if (!container) return;

  container.innerHTML = '';
  SAMPLE_CALLS.forEach(call => {
    const initials = call.name.split(' ').map(n => n[0]).join('');
    const div = document.createElement('div');
    div.className = 'dash-feed-item';
    div.onclick = () => openModal(call);
    div.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px;">
        <div class="dash-avatar">${initials}</div>
        <div class="dash-caller-info">
          <span class="dash-caller-name">${call.name}</span>
          <span class="dash-caller-meta">${call.phone} • ${call.campaign}</span>
        </div>
      </div>
      <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
        <span class="${call.tagClass}">${call.sentiment}</span>
        <span style="font-size: 11px; color: #7a7b7c; font-family: 'JetBrains Mono', monospace;">${call.duration}</span>
      </div>
    `;
    container.appendChild(div);
  });
}

function openModal(call) {
  const modal = document.getElementById('callModal');
  if (!modal) return;

  document.getElementById('modalName').innerText = call.name;
  document.getElementById('modalMeta').innerText = `${call.phone} • ${call.campaign} • Duration: ${call.duration}`;
  
  const chatList = document.getElementById('modalChatList');
  chatList.innerHTML = `
    <div class="dash-bubble agent">
      <span class="dash-bubble-speaker">🤖 Sarah (Mixup AI)</span>
      Hello ${call.name.split(' ')[0]}! I'm calling from Mixup regarding your recent inquiry about our AI telephony agent platform. Are you looking to scale your lead qualification process?
    </div>
    <div class="dash-bubble customer">
      <span class="dash-bubble-speaker">👤 ${call.name}</span>
      Yes, absolutely! We currently have a 3-hour response lag with our manual sales reps. We want instant outbound dialers that can book appointments straight into our Salesforce calendar.
    </div>
    <div class="dash-bubble agent">
      <span class="dash-bubble-speaker">🤖 Sarah (Mixup AI)</span>
      That is exactly what Mixup specializes in! Our AI agents connect within 2 seconds of web form submissions and automatically schedule confirmed appointments. Let's get you set up for a live architecture review.
    </div>
  `;

  modal.classList.add('active');
}

function closeModal() {
  const modal = document.getElementById('callModal');
  if (modal) modal.classList.remove('active');
}

function setupEvents() {
  document.querySelectorAll('.dash-filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const key = e.target.getAttribute('data-range');
      setTimeRange(key, e.target);
    });
  });
}
