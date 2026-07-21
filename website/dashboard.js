/* ==========================================
   MIXUP FUNCTIONAL ANALYTICS DASHBOARD ENGINE
   v2.1 - Supabase Auth & Personalized Business Dashboard
   ========================================== */

let mainChart = null;
let allCallLogs = [];
let currentBusiness = null;

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Authenticate & load business info
    const isAuthOk = await checkBusinessAuth();
    if (!isAuthOk) return;

    // 2. Fetch business data & call logs from Supabase
    await fetchBusinessDashboardData();
    setupEvents();
});

// ========================================
// AUTHENTICATION CHECK
// ========================================

async function checkBusinessAuth() {
    const session = await getSupabaseSession();
    if (!session || !session.user) {
        console.log('No active session found. Redirecting to registration...');
        window.location.href = 'register.html';
        return false;
    }

    const user = session.user;

    try {
        // Fetch business details from database
        const { data: businessData, error } = await supabaseClient
            .from('businesses')
            .select('*')
            .eq('id', user.id)
            .maybeSingle();

        if (error) {
            console.error('Error fetching business info:', error);
        }

        currentBusiness = businessData || {
            id: user.id,
            business_name: user.user_metadata?.business_name || user.email.split('@')[0],
            industry: 'General Business',
            contact_name: user.user_metadata?.contact_name || 'Business Owner',
            email: user.email
        };

        renderBusinessInfo(currentBusiness);
        return true;

    } catch (err) {
        console.error('Auth verification error:', err);
        window.location.href = 'register.html';
        return false;
    }
}

function renderBusinessInfo(business) {
    const nameEl = document.getElementById('displayBusinessName');
    const industryEl = document.getElementById('displayIndustry');
    const avatarEl = document.getElementById('businessAvatar');
    const metaEl = document.getElementById('displayContactMeta');
    const navNameEl = document.getElementById('navBusinessName');

    const bName = business.business_name || 'My Business';
    const initials = bName.substring(0, 2).toUpperCase();

    if (nameEl) nameEl.innerText = bName;
    if (industryEl) industryEl.innerText = business.industry || 'General';
    if (avatarEl) avatarEl.innerText = initials;
    if (metaEl) metaEl.innerText = `Managed by ${business.contact_name || 'Admin'} (${business.email || ''}) • Custom AI Agent Dashboard`;
    if (navNameEl) {
        navNameEl.innerText = bName;
        navNameEl.style.display = 'inline-block';
    }
}

// ========================================
// DATA FETCHING
// ========================================

async function fetchBusinessDashboardData() {
    if (!currentBusiness) return;

    try {
        // Fetch call logs for this specific business from Supabase
        const { data: logs, error } = await supabaseClient
            .from('call_logs')
            .select('*')
            .eq('business_id', currentBusiness.id)
            .order('created_at', { ascending: false });

        if (error) {
            console.warn('Error loading logs from Supabase:', error);
        }

        allCallLogs = logs || [];

        // If no logs yet, provide clean initial view
        updateKPIs(allCallLogs);
        initChart(allCallLogs);
        renderFeed(allCallLogs);
        updateSourceBreakdown(allCallLogs);

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
    fetchBusinessDashboardData();
}

// ========================================
// KPI UPDATES
// ========================================

function updateKPIs(logs) {
    const totalCalls = logs.length;
    const completed = logs.filter(l => l.status === 'completed' || !l.status).length;
    const successRate = totalCalls > 0 ? Math.round((completed / totalCalls) * 100) : 0;
    
    const delighted = logs.filter(l => l.sentiment === 'Delighted').length;
    const interested = logs.filter(l => l.sentiment === 'Interested' || !l.sentiment).length;
    const sentiment = totalCalls > 0 ? Math.min(Math.round(((delighted + interested * 0.8) / totalCalls) * 100), 100) : 0;

    document.getElementById('kpiCalls').innerText = totalCalls.toLocaleString();
    document.getElementById('kpiSuccessRate').innerText = `${successRate}%`;
    document.getElementById('kpiAvgTime').innerText = totalCalls > 0 ? '1m 00s' : '--';
    document.getElementById('kpiSentiment').innerText = `${sentiment}%`;

    const callsBadge = document.getElementById('kpiCallsBadge');
    const successBadge = document.getElementById('kpiSuccessBadge');
    const sentimentBadge = document.getElementById('kpiSentimentBadge');

    if (callsBadge) callsBadge.innerText = totalCalls > 0 ? `${totalCalls} logged` : '0 calls';
    if (successBadge) successBadge.innerText = completed > 0 ? `${completed} qualified` : '0 qualified';
    if (sentimentBadge) sentimentBadge.innerText = sentiment > 0 ? `NPS +${Math.round(sentiment * 0.8)}` : '0 rating';
}

function updateSourceBreakdown(logs) {
    const ctaEl = document.getElementById('ctaCallCount');
    const instantEl = document.getElementById('instantCallCount');

    const ctaCount = logs.filter(l => l.source === 'cta_form').length;
    const instantCount = logs.filter(l => l.source === 'instant_call' || !l.source).length;

    if (ctaEl) ctaEl.innerText = ctaCount;
    if (instantEl) instantEl.innerText = instantCount;
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
        const date = new Date(log.created_at || log.timestamp || Date.now()).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        callsByDate[date] = (callsByDate[date] || 0) + 1;
    });

    const labels = Object.keys(callsByDate).reverse().slice(-14);
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
                    label: 'Calls Handled',
                    data: data,
                    borderColor: '#ff5065',
                    backgroundColor: gradCalls,
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointBackgroundColor: '#ff5065'
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
                    ticks: { font: { family: 'JetBrains Mono', size: 11 }, color: '#7a7b7c', stepSize: 1 },
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

    logs.forEach(call => {
        const name = call.caller_name || call.name || 'Unknown Caller';
        const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
        const phone = call.caller_phone || call.phone || '--';
        const source = call.source === 'cta_form' ? 'CTA Form' : 'Instant Call';
        const sentiment = call.sentiment || 'Interested';
        const tagClass = sentiment === 'Delighted' ? 'dash-tag-delighted' : 'dash-tag-interested';
        const timeAgo = getTimeAgo(call.created_at || call.timestamp);
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
// MODAL & TRANSCRIPT
// ========================================

function openModal(call) {
    const modal = document.getElementById('callModal');
    if (!modal) return;

    const name = call.caller_name || call.name || 'Unknown Caller';
    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    const phone = call.caller_phone || call.phone || '--';
    const source = call.source === 'cta_form' ? 'CTA Form' : 'Instant Call';
    const duration = call.duration || '1m 00s';

    document.getElementById('modalAvatar').innerText = initials;
    document.getElementById('modalName').innerText = name;
    document.getElementById('modalMeta').innerText = `${phone} \u2022 ${source} \u2022 Duration: ${duration}`;

    const chatList = document.getElementById('modalChatList');
    const transcript = call.transcript || [
        { speaker: 'agent', name: 'Sarah (Mixup AI)', text: `Hello ${name}! Thank you for contacting ${currentBusiness?.business_name || 'our business'}. How can our AI assistant help you today?` },
        { speaker: 'customer', name: name, text: `Hi, I was interested in getting more information about your ${currentBusiness?.industry || 'services'}.` },
        { speaker: 'agent', name: 'Sarah (Mixup AI)', text: `Great! We've recorded your interest and our team will follow up with you shortly. Have a great day!` }
    ];

    chatList.innerHTML = transcript.map(msg => {
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

    modal.classList.add('active');
}

function closeModal() {
    const modal = document.getElementById('callModal');
    if (modal) modal.classList.remove('active');
}

document.addEventListener('click', (e) => {
    const modal = document.getElementById('callModal');
    if (modal && modal.classList.contains('active') && e.target === modal) {
        closeModal();
    }
});

function showEmptyStates() {
    const chartCanvas = document.getElementById('simpleChart');
    const chartEmpty = document.getElementById('chartEmptyState');
    const feedEmpty = document.getElementById('feedEmptyState');

    if (chartCanvas) chartCanvas.style.display = 'none';
    if (chartEmpty) chartEmpty.style.display = 'flex';
    if (feedEmpty) feedEmpty.style.display = 'flex';
}

function setupEvents() {
    document.querySelectorAll('.dash-filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.dash-filter-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
        });
    });
}

function getTimeAgo(timestamp) {
    if (!timestamp) return 'Recently';
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
