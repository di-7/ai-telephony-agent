/* ==========================================
   MIXUP ANALYTICS DASHBOARD INTERACTIVE ENGINE
   ========================================== */

// --- Datasets for Scenarios ---
const SCENARIO_DATA = {
  all: {
    title: "All Campaigns (Overview)",
    kpis: {
      totalCalls: "148,920",
      totalCallsTrend: "+24.5%",
      qualRate: "71.8%",
      qualRateTrend: "+12.4%",
      avgDuration: "3m 48s",
      sentimentScore: "94.2%",
      costSaved: "$64,250",
      latency: "210ms"
    },
    chartData: [4200, 5100, 6800, 7400, 8900, 11200, 14890],
    qualData: [2900, 3700, 4900, 5300, 6400, 8100, 10690],
    sentiment: [62, 24, 9, 5], // Delighted, Interested, Neutral, Objection
    callLogs: [
      { id: "CALL-8921", name: "David Miller", phone: "+1 (555) 234-8901", campaign: "Enterprise SaaS Lead", duration: "4m 12s", sentiment: "delighted", time: "2 mins ago", agent: "Sarah AI" },
      { id: "CALL-8920", name: "Amanda Chen", phone: "+1 (555) 876-1234", campaign: "E-Commerce Reactivation", duration: "2m 45s", sentiment: "interested", time: "6 mins ago", agent: "Alex AI" },
      { id: "CALL-8919", name: "Marcus Vance", phone: "+1 (555) 432-9087", campaign: "Healthcare Booking", duration: "3m 18s", sentiment: "delighted", time: "11 mins ago", agent: "Maya AI" },
      { id: "CALL-8918", name: "Jessica Taylor", phone: "+1 (555) 789-3412", campaign: "Real Estate Outreach", duration: "5m 02s", sentiment: "interested", time: "15 mins ago", agent: "David AI" },
      { id: "CALL-8917", name: "Robert Fox", phone: "+1 (555) 654-7890", campaign: "Enterprise SaaS Lead", duration: "1m 55s", sentiment: "neutral", time: "22 mins ago", agent: "Sarah AI" },
      { id: "CALL-8916", name: "Sophia Martinez", phone: "+1 (555) 321-6549", campaign: "E-Commerce Reactivation", duration: "4m 30s", sentiment: "delighted", time: "28 mins ago", agent: "Alex AI" }
    ]
  },
  ecommerce: {
    title: "E-Commerce Reactivation Campaign",
    kpis: {
      totalCalls: "42,150",
      totalCallsTrend: "+31.2%",
      qualRate: "68.4%",
      qualRateTrend: "+14.1%",
      avgDuration: "2m 50s",
      sentimentScore: "92.8%",
      costSaved: "$21,400",
      latency: "195ms"
    },
    chartData: [1200, 1800, 2400, 2900, 3500, 4100, 5200],
    qualData: [800, 1200, 1650, 1980, 2380, 2800, 3550],
    sentiment: [55, 30, 10, 5],
    callLogs: [
      { id: "CALL-8920", name: "Amanda Chen", phone: "+1 (555) 876-1234", campaign: "E-Commerce Reactivation", duration: "2m 45s", sentiment: "interested", time: "6 mins ago", agent: "Alex AI" },
      { id: "CALL-8916", name: "Sophia Martinez", phone: "+1 (555) 321-6549", campaign: "E-Commerce Reactivation", duration: "4m 30s", sentiment: "delighted", time: "28 mins ago", agent: "Alex AI" },
      { id: "CALL-8910", name: "Liam O'Connor", phone: "+1 (555) 998-1122", campaign: "Cart Abandonment", duration: "3m 10s", sentiment: "delighted", time: "42 mins ago", agent: "Alex AI" }
    ]
  },
  saas: {
    title: "B2B SaaS Inbound Qualification",
    kpis: {
      totalCalls: "58,300",
      totalCallsTrend: "+19.8%",
      qualRate: "78.5%",
      qualRateTrend: "+9.2%",
      avgDuration: "4m 35s",
      sentimentScore: "96.1%",
      costSaved: "$32,800",
      latency: "220ms"
    },
    chartData: [1500, 2100, 2800, 3200, 4100, 5400, 6800],
    qualData: [1180, 1650, 2200, 2510, 3220, 4240, 5330],
    sentiment: [70, 20, 6, 4],
    callLogs: [
      { id: "CALL-8921", name: "David Miller", phone: "+1 (555) 234-8901", campaign: "Enterprise SaaS Lead", duration: "4m 12s", sentiment: "delighted", time: "2 mins ago", agent: "Sarah AI" },
      { id: "CALL-8917", name: "Robert Fox", phone: "+1 (555) 654-7890", campaign: "Enterprise SaaS Lead", duration: "1m 55s", sentiment: "neutral", time: "22 mins ago", agent: "Sarah AI" },
      { id: "CALL-8905", name: "Elena Rostova", phone: "+1 (555) 443-8811", campaign: "Demo Request Followup", duration: "5m 20s", sentiment: "delighted", time: "1 hour ago", agent: "Sarah AI" }
    ]
  },
  healthcare: {
    title: "Healthcare Appointment Scheduling",
    kpis: {
      totalCalls: "26,400",
      totalCallsTrend: "+15.3%",
      qualRate: "84.2%",
      qualRateTrend: "+8.7%",
      avgDuration: "2m 15s",
      sentimentScore: "97.5%",
      costSaved: "$14,100",
      latency: "190ms"
    },
    chartData: [800, 1100, 1400, 1800, 2200, 2600, 3100],
    qualData: [670, 930, 1180, 1510, 1850, 2190, 2610],
    sentiment: [75, 18, 5, 2],
    callLogs: [
      { id: "CALL-8919", name: "Marcus Vance", phone: "+1 (555) 432-9087", campaign: "Healthcare Booking", duration: "3m 18s", sentiment: "delighted", time: "11 mins ago", agent: "Maya AI" },
      { id: "CALL-8908", name: "Patricia Wright", phone: "+1 (555) 776-3344", campaign: "Patient Recall", duration: "2m 05s", sentiment: "delighted", time: "35 mins ago", agent: "Maya AI" }
    ]
  }
};

// --- Global Chart Instances ---
let volumeChartInstance = null;
let sentimentChartInstance = null;

// --- State Variables ---
let currentScenario = 'all';
let isLiveModeActive = true;
let isPitchModeActive = false;
let liveInterval = null;
let audioIsPlaying = false;

// --- Initialize Dashboard ---
document.addEventListener('DOMContentLoaded', () => {
  initCharts();
  renderScenario(currentScenario);
  setupEventListeners();
  startLiveMode();
  updateRoiCalculator();
});

// --- Initialize Chart.js Charts ---
function initCharts() {
  // 1. Call Volume & Qualification Line Chart
  const ctxVolume = document.getElementById('volumeChart').getContext('2d');
  
  const gradVolume = ctxVolume.createLinearGradient(0, 0, 0, 300);
  gradVolume.addColorStop(0, 'rgba(255, 80, 101, 0.4)');
  gradVolume.addColorStop(1, 'rgba(255, 80, 101, 0.0)');

  const gradQual = ctxVolume.createLinearGradient(0, 0, 0, 300);
  gradQual.addColorStop(0, 'rgba(16, 185, 129, 0.4)');
  gradQual.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

  volumeChartInstance = new Chart(ctxVolume, {
    type: 'line',
    data: {
      labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      datasets: [
        {
          label: 'Total AI Calls',
          data: SCENARIO_DATA.all.chartData,
          borderColor: '#ff5065',
          backgroundColor: gradVolume,
          borderWidth: 3,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 7
        },
        {
          label: 'Qualified Leads',
          data: SCENARIO_DATA.all.qualData,
          borderColor: '#10b981',
          backgroundColor: gradQual,
          borderWidth: 3,
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 7
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Sora', size: 12 } }
        },
        tooltip: {
          backgroundColor: '#11131c',
          borderColor: 'rgba(255, 80, 101, 0.3)',
          borderWidth: 1,
          titleFont: { family: 'Sora', size: 13 },
          bodyFont: { family: 'JetBrains Mono', size: 12 },
          padding: 12
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'Sora' } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono' } }
        }
      }
    }
  });

  // 2. Sentiment Donut Chart
  const ctxSentiment = document.getElementById('sentimentChart').getContext('2d');
  sentimentChartInstance = new Chart(ctxSentiment, {
    type: 'doughnut',
    data: {
      labels: ['Delighted (62%)', 'Interested (24%)', 'Neutral (9%)', 'Objection (5%)'],
      datasets: [{
        data: SCENARIO_DATA.all.sentiment,
        backgroundColor: ['#10b981', '#06b6d4', '#94a3b8', '#f59e0b'],
        borderWidth: 2,
        borderColor: '#12141d',
        hoverOffset: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: { color: '#94a3b8', font: { family: 'Sora', size: 12 }, boxWidth: 14 }
        }
      },
      cutout: '70%'
    }
  });
}

// --- Render Selected Scenario ---
function renderScenario(key) {
  const data = SCENARIO_DATA[key] || SCENARIO_DATA.all;
  currentScenario = key;

  // Update KPI values
  document.getElementById('kpi-total-calls').innerText = data.kpis.totalCalls;
  document.getElementById('kpi-calls-trend').innerText = data.kpis.totalCallsTrend;
  
  document.getElementById('kpi-qual-rate').innerText = data.kpis.qualRate;
  document.getElementById('kpi-qual-trend').innerText = data.kpis.qualRateTrend;
  
  document.getElementById('kpi-duration').innerText = data.kpis.avgDuration;
  document.getElementById('kpi-sentiment').innerText = data.kpis.sentimentScore;
  document.getElementById('kpi-cost-saved').innerText = data.kpis.costSaved;
  document.getElementById('kpi-latency').innerText = data.kpis.latency;

  // Update Charts
  if (volumeChartInstance) {
    volumeChartInstance.data.datasets[0].data = data.chartData;
    volumeChartInstance.data.datasets[1].data = data.qualData;
    volumeChartInstance.update();
  }

  if (sentimentChartInstance) {
    sentimentChartInstance.data.datasets[0].data = data.sentiment;
    sentimentChartInstance.update();
  }

  // Render Call Feed
  renderCallFeed(data.callLogs);
}

// --- Render Call Feed List ---
function renderCallFeed(logs) {
  const container = document.getElementById('callFeedList');
  if (!container) return;

  container.innerHTML = '';
  logs.forEach(log => {
    const initials = log.name.split(' ').map(n => n[0]).join('');
    const el = document.createElement('div');
    el.className = 'call-item';
    el.onclick = () => openCallModal(log);
    
    el.innerHTML = `
      <div class="call-item-left">
        <div class="caller-avatar">${initials}</div>
        <div class="caller-info">
          <span class="caller-name">${log.name}</span>
          <span class="caller-meta">${log.phone} • ${log.agent}</span>
        </div>
      </div>
      <div class="call-item-right">
        <span class="sentiment-badge ${log.sentiment}">${log.sentiment}</span>
        <span class="call-duration">${log.duration} • ${log.time}</span>
      </div>
    `;
    container.appendChild(el);
  });
}

// --- Event Listeners Setup ---
function setupEventListeners() {
  // Scenario Dropdown
  const scenarioSelect = document.getElementById('scenarioSelect');
  if (scenarioSelect) {
    scenarioSelect.addEventListener('change', (e) => {
      renderScenario(e.target.value);
    });
  }

  // Time Tabs
  const timeTabs = document.querySelectorAll('.time-tab');
  timeTabs.forEach(tab => {
    tab.addEventListener('click', (e) => {
      timeTabs.forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      // Simulate slight data variation
      renderScenario(currentScenario);
    });
  });

  // Pitch Mode Toggle
  const pitchBtn = document.getElementById('pitchModeBtn');
  const pitchBanner = document.getElementById('pitchBanner');
  if (pitchBtn) {
    pitchBtn.addEventListener('click', () => {
      isPitchModeActive = !isPitchModeActive;
      pitchBtn.classList.toggle('active', isPitchModeActive);
      pitchBanner.classList.toggle('show', isPitchModeActive);
      document.body.classList.toggle('pitch-banner-active', isPitchModeActive);
    });
  }

  // Live Mode Toggle
  const liveBtn = document.getElementById('liveToggleBtn');
  if (liveBtn) {
    liveBtn.addEventListener('click', () => {
      isLiveModeActive = !isLiveModeActive;
      liveBtn.classList.toggle('active', isLiveModeActive);
      liveBtn.innerHTML = isLiveModeActive 
        ? `<span class="pulse-dot"></span> Live Stream ACTIVE` 
        : `<span>⏸️</span> Live Stream PAUSED`;
      
      if (isLiveModeActive) {
        startLiveMode();
      } else {
        clearInterval(liveInterval);
      }
    });
  }

  // ROI Calculator Sliders
  const volSlider = document.getElementById('roiCallsSlider');
  const rateSlider = document.getElementById('roiRateSlider');
  if (volSlider && rateSlider) {
    volSlider.addEventListener('input', updateRoiCalculator);
    rateSlider.addEventListener('input', updateRoiCalculator);
  }
}

// --- ROI Calculator Logic ---
function updateRoiCalculator() {
  const callsVal = parseInt(document.getElementById('roiCallsSlider').value);
  const rateVal = parseInt(document.getElementById('roiRateSlider').value);

  document.getElementById('roiCallsVal').innerText = callsVal.toLocaleString();
  document.getElementById('roiRateVal').innerText = `$${rateVal}/hr`;

  // Calculation: Avg human agent handles 12 calls/hr. MixUp AI cost per call ~$0.15 vs Human cost per call ~$2.50
  const totalHumanCost = callsVal * (rateVal / 12);
  const totalMixupCost = callsVal * 0.18;
  const netSavings = Math.round(totalHumanCost - totalMixupCost);
  const hoursSaved = Math.round(callsVal / 12);
  const roiPct = Math.round((netSavings / (totalMixupCost || 1)) * 100);

  document.getElementById('roiNetSavings').innerText = `$${netSavings.toLocaleString()}`;
  document.getElementById('roiHoursSaved').innerText = `${hoursSaved.toLocaleString()} hrs`;
  document.getElementById('roiPercentage').innerText = `+${roiPct}%`;
}

// --- Live Simulation Mode (Pushes live calls & notifications) ---
const SIMULATED_NAMES = [
  "Emily Watson", "Jason Myers", "Carlos Rodriguez", "Sarah Jenkins", "Michael Chang", "Olivia Sterling", "Brian O'Neill"
];
const SIMULATED_CAMPAIGNS = [
  "Enterprise SaaS Lead", "E-Commerce Reactivation", "Healthcare Booking", "Real Estate Outreach"
];

function startLiveMode() {
  if (liveInterval) clearInterval(liveInterval);
  
  liveInterval = setInterval(() => {
    if (!isLiveModeActive) return;

    const randomName = SIMULATED_NAMES[Math.floor(Math.random() * SIMULATED_NAMES.length)];
    const randomCamp = SIMULATED_CAMPAIGNS[Math.floor(Math.random() * SIMULATED_CAMPAIGNS.length)];
    const newLog = {
      id: `CALL-${Math.floor(8922 + Math.random() * 500)}`,
      name: randomName,
      phone: `+1 (555) ${Math.floor(100 + Math.random() * 899)}-${Math.floor(1000 + Math.random() * 8999)}`,
      campaign: randomCamp,
      duration: `${Math.floor(1 + Math.random() * 4)}m ${Math.floor(10 + Math.random() * 45)}s`,
      sentiment: Math.random() > 0.3 ? "delighted" : "interested",
      time: "Just now",
      agent: "Sarah AI"
    };

    // Add to top of list
    const currentList = SCENARIO_DATA.all.callLogs;
    currentList.unshift(newLog);
    if (currentList.length > 8) currentList.pop();
    
    renderCallFeed(currentList);
    showToastNotification(newLog);

    // Bump counter slightly
    const elCalls = document.getElementById('kpi-total-calls');
    if (elCalls) {
      let num = parseInt(elCalls.innerText.replace(/,/g, ''));
      elCalls.innerText = (num + 1).toLocaleString();
    }
  }, 7000);
}

// --- Toast Notifications ---
function showToastNotification(call) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast-msg';
  toast.innerHTML = `
    <div class="pulse-dot"></div>
    <div>
      <strong>Live Call Qualified!</strong><br>
      <span style="color:#94a3b8">${call.name} • ${call.campaign} (${call.duration})</span>
    </div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// --- Call Detail Modal Drawer ---
function openCallModal(log) {
  const modal = document.getElementById('callDetailModal');
  if (!modal) return;

  document.getElementById('modalCallerName').innerText = log.name;
  document.getElementById('modalCallerMeta').innerText = `${log.phone} • ${log.campaign} • Agent: ${log.agent}`;
  
  // Render Transcript Timeline
  const timeline = document.getElementById('modalTranscriptTimeline');
  timeline.innerHTML = `
    <div class="chat-bubble agent">
      <div class="bubble-meta"><span>🤖 ${log.agent}</span> • 00:02 • <span>Latency 210ms</span></div>
      <div class="bubble-content">Hello ${log.name.split(' ')[0]}! This is ${log.agent} from Mixup. I noticed you checked out our enterprise AI agent workflow demo yesterday. How is your team currently handling inbound lead qualification?</div>
    </div>
    <div class="chat-bubble customer">
      <div class="bubble-meta"><span>👤 ${log.name}</span> • 00:08 • <span class="badge-tag badge-emerald">Enthusiastic</span></div>
      <div class="bubble-content">Hi Sarah! Yeah, we currently have 4 SDRs manually dialing inquiries, but our response time is over 3 hours. We're losing a ton of hot leads. Can your AI agents respond instantly?</div>
    </div>
    <div class="chat-bubble agent">
      <div class="bubble-meta"><span>🤖 ${log.agent}</span> • 00:15 • <span>Latency 195ms</span></div>
      <div class="bubble-content">Absolutely! Mixup AI agents initiate outbound calls or answer inbound calls within 2.5 seconds of a web form submission. We qualify their budget, timeline, and sync directly to your CRM in real time. Would Tuesday at 2 PM work for a live architecture review?</div>
    </div>
    <div class="chat-bubble customer">
      <div class="bubble-meta"><span>👤 ${log.name}</span> • 00:24 • <span class="badge-tag badge-emerald">Ready to Book</span></div>
      <div class="bubble-content">That sounds perfect. Lock in Tuesday at 2 PM for me and send the calendar invite!</div>
    </div>
  `;

  // Render AI Action Insights
  const insights = document.getElementById('modalInsights');
  insights.innerHTML = `
    <div class="insights-title">✨ AI Extracted Insights & CRM Auto-Sync</div>
    <div class="insights-list">
      <div>✓ <strong>Primary Pain Point Identified:</strong> High lead response latency (>3 hours with human SDR team).</div>
      <div>✓ <strong>Budget & Intent:</strong> Enterprise Tier Qualified ($5,000+/mo budget).</div>
      <div>✓ <strong>Action Completed:</strong> Demo scheduled for Tuesday at 2:00 PM EST.</div>
      <div>✓ <strong>Salesforce Sync Status:</strong> Contact & Lead record updated instantly (ID: #SF-99824).</div>
    </div>
  `;

  modal.classList.add('active');
}

function closeCallModal() {
  const modal = document.getElementById('callDetailModal');
  if (modal) modal.classList.remove('active');
  audioIsPlaying = false;
  const btn = document.getElementById('modalPlayBtn');
  if (btn) btn.innerText = '▶';
}

function toggleModalAudio() {
  audioIsPlaying = !audioIsPlaying;
  const btn = document.getElementById('modalPlayBtn');
  if (btn) btn.innerText = audioIsPlaying ? '⏸' : '▶';
}

// --- Export Modal ---
function openExportModal() {
  const modal = document.getElementById('exportModal');
  if (modal) modal.classList.add('active');
}

function closeExportModal() {
  const modal = document.getElementById('exportModal');
  if (modal) modal.classList.remove('active');
}

function triggerDownloadReport() {
  alert('✨ MixUp Analytics Executive Summary PDF generated & ready for download!');
  closeExportModal();
}
