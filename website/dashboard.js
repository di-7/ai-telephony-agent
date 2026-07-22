/* ==========================================
   MIXUP FUNCTIONAL ANALYTICS DASHBOARD ENGINE
   v3.0 - Real Data Only (No Mock Transcripts)
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
// AUTHENTICATION & BUSINESS PROFILE
// ========================================

async function checkBusinessAuth() {
    const session = await getSupabaseSession();
    if (!session || !session.user) {
        console.log('No active session found. Redirecting to registration...');
        window.location.href = 'register.html';
        return false;
    }

    const user = session.user;
    const metadata = user.user_metadata || {};

    try {
        let { data: businessData, error } = await supabaseClient
            .from('businesses')
            .select('*')
            .eq('id', user.id)
            .maybeSingle();

        if (error) {
            console.warn('Error fetching business info from Supabase:', error);
        }

        // Determine best values between DB record and user_metadata
        const finalBusinessName = businessData?.business_name || metadata.business_name || user.email.split('@')[0];
        const finalIndustry = (businessData?.industry && businessData.industry !== 'General Business') 
            ? businessData.industry 
            : (metadata.industry || businessData?.industry || 'General Business');
        const finalContactName = businessData?.contact_name || metadata.contact_name || 'Business Owner';
        const finalPhone = businessData?.phone || metadata.phone || '';

        // If the DB row is missing, OR if DB has default/missing values compared to metadata, upsert to DB
        const needsSync = !businessData || 
            (!businessData.phone && finalPhone) || 
            (businessData.industry === 'General Business' && finalIndustry !== 'General Business');

        if (needsSync) {
            const payload = {
                id: user.id,
                business_name: finalBusinessName,
                industry: finalIndustry,
                contact_name: finalContactName,
                email: user.email,
                phone: finalPhone
            };

            const { data: upserted, error: upsertErr } = await supabaseClient
                .from('businesses')
                .upsert([payload])
                .select()
                .maybeSingle();

            if (!upsertErr && upserted) {
                businessData = upserted;
            } else if (upsertErr) {
                console.warn('Error upserting business profile into Supabase:', upsertErr);
            }
        }

        currentBusiness = businessData || {
            id: user.id,
            business_name: finalBusinessName,
            industry: finalIndustry,
            contact_name: finalContactName,
            email: user.email,
            phone: finalPhone
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
    const contactEl = document.getElementById('displayContactName');
    const emailEl = document.getElementById('displayEmail');
    const phoneEl = document.getElementById('displayPhone');

    const bName = business.business_name || 'My Business';

    if (nameEl) nameEl.innerText = bName;
    if (industryEl) industryEl.innerText = business.industry || 'General';
    if (contactEl) contactEl.innerText = business.contact_name || 'Admin';
    if (emailEl) emailEl.innerText = business.email || '';
    if (phoneEl) phoneEl.innerText = (business.phone && business.phone.trim() !== '') ? business.phone : 'No phone set';
}

// ========================================
// DIRECT DEMO CALL TRIGGER
// ========================================

async function triggerTestDemoCall() {
    if (!currentBusiness) {
        alert('Please log in to trigger a demo call.');
        return;
    }

    let phone = currentBusiness.phone;
    if (!phone || phone.trim().length < 5) {
        phone = prompt('Please enter your phone number to receive the AI demo call:', '+1');
        if (!phone) return;
        
        // Save provided phone back to current business profile
        currentBusiness.phone = phone;
        renderBusinessInfo(currentBusiness);

        // Update database
        supabaseClient.from('businesses').upsert([{
            id: currentBusiness.id,
            business_name: currentBusiness.business_name,
            industry: currentBusiness.industry,
            contact_name: currentBusiness.contact_name,
            email: currentBusiness.email,
            phone: phone
        }]).then(() => {}).catch(e => console.warn(e));

        if (supabaseClient.auth) {
            supabaseClient.auth.updateUser({ data: { phone: phone } }).catch(e => console.warn(e));
        }
    }

    // Format phone number
    if (!phone.startsWith('+')) {
        phone = '+' + phone.trim();
    }

    const modal = document.getElementById('testCallModal');
    const statusText = document.getElementById('testCallStatusText');

    if (modal && statusText) {
        statusText.innerHTML = `Dialing <strong>${escapeHtml(phone)}</strong>... Answer your phone to speak with your AI Agent!`;
        modal.classList.add('active');
    }

    try {
        // Call backend API endpoint to trigger VideoSDK call
        // The backend handles call logging — no mock data inserted from frontend
        const apiEndpoint = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
            ? `${window.location.protocol}//${window.location.hostname}:8081/api/make-call`
            : 'https://ai-telephony-agent.onrender.com/api/make-call';

        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                to_number: phone,
                name: currentBusiness.contact_name || currentBusiness.business_name,
                company: currentBusiness.business_name,
                business_id: currentBusiness.id
            })
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            const errMsg = errData.error || `Call failed (HTTP ${response.status})`;
            if (statusText) {
                statusText.innerHTML = `<span style="color: #ff5065;">❌ ${escapeHtml(errMsg)}</span>`;
            }
            return;
        }

        if (statusText) {
            statusText.innerHTML = `📞 Call initiated to <strong>${escapeHtml(phone)}</strong>. Pick up your phone!<br><span style="font-size: 12px; color: #7a7b7c; margin-top: 8px; display: block;">Call details will appear in your feed once processed.</span>`;
        }

        // Auto-refresh feed after 5 seconds to pick up backend-logged data
        setTimeout(() => {
            fetchBusinessDashboardData();
        }, 5000);

    } catch (err) {
        console.error('Trigger call error:', err);
        if (statusText) {
            statusText.innerHTML = `<span style="color: #ff5065;">❌ Could not reach the call server. Please try again later.</span>`;
        }
    }
}

function closeTestCallModal() {
    const modal = document.getElementById('testCallModal');
    if (modal) modal.classList.remove('active');
}

// ========================================
// DATA FETCHING & RENDERING
// ========================================

async function fetchBusinessDashboardData() {
    if (!currentBusiness) return;

    try {
        const { data: logs, error } = await supabaseClient
            .from('call_logs')
            .select('*')
            .eq('business_id', currentBusiness.id)
            .order('created_at', { ascending: false });

        if (error) {
            console.warn('Error loading logs from Supabase:', error);
        }

        allCallLogs = logs || [];

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

function updateKPIs(logs) {
    const totalCalls = logs.length;
    const answered = logs.filter(l => l.status === 'completed').length;
    const initiated = logs.filter(l => l.status === 'initiated' || l.status === 'ringing').length;
    const successRate = totalCalls > 0 ? Math.round((answered / totalCalls) * 100) : 0;
    
    const delighted = logs.filter(l => l.sentiment === 'Delighted').length;
    const interested = logs.filter(l => l.sentiment === 'Interested').length;
    const sentimentBase = answered > 0 ? answered : totalCalls;
    const sentiment = sentimentBase > 0 ? Math.min(Math.round(((delighted + interested * 0.8) / sentimentBase) * 100), 100) : 0;

    // Calculate real average duration from logs that have parseable durations
    let avgDuration = '--';
    const completedLogs = logs.filter(l => l.status === 'completed' && l.duration);
    if (completedLogs.length > 0) {
        let totalSeconds = 0;
        completedLogs.forEach(l => {
            const match = (l.duration || '').match(/(\d+)m\s*(\d+)s/);
            if (match) {
                totalSeconds += parseInt(match[1]) * 60 + parseInt(match[2]);
            }
        });
        if (totalSeconds > 0) {
            const avgSec = Math.round(totalSeconds / completedLogs.length);
            avgDuration = `${Math.floor(avgSec / 60)}m ${String(avgSec % 60).padStart(2, '0')}s`;
        }
    }

    document.getElementById('kpiCalls').innerText = totalCalls.toLocaleString();
    document.getElementById('kpiSuccessRate').innerText = `${successRate}%`;
    document.getElementById('kpiAvgTime').innerText = avgDuration;
    document.getElementById('kpiSentiment').innerText = `${sentiment}%`;

    const callsBadge = document.getElementById('kpiCallsBadge');
    const successBadge = document.getElementById('kpiSuccessBadge');
    const sentimentBadge = document.getElementById('kpiSentimentBadge');

    if (callsBadge) callsBadge.innerText = totalCalls > 0 ? `${totalCalls} logged` : '0 calls';
    if (successBadge) successBadge.innerText = answered > 0 ? `${answered} answered` : `${initiated} initiated`;
    if (sentimentBadge) sentimentBadge.innerText = sentiment > 0 ? `NPS +${Math.round(sentiment * 0.8)}` : 'N/A';
}

function updateSourceBreakdown(logs) {
    const ctaEl = document.getElementById('ctaCallCount');
    const instantEl = document.getElementById('instantCallCount');

    const ctaCount = logs.filter(l => l.source === 'cta_form').length;
    const instantCount = logs.filter(l => l.source === 'instant_call' || !l.source).length;

    if (ctaEl) ctaEl.innerText = ctaCount;
    if (instantEl) instantEl.innerText = instantCount;
}

function initChart(logs) {
    const canvas = document.getElementById('simpleChart');
    const emptyState = document.getElementById('chartEmptyState');
    if (!canvas) return;

    const chartWrap = canvas.parentElement;

    if (!logs || logs.length === 0) {
        if (chartWrap) chartWrap.style.display = 'none';
        canvas.style.display = 'none';
        if (emptyState) emptyState.style.display = 'flex';
        return;
    }

    if (chartWrap) chartWrap.style.display = 'block';
    canvas.style.display = 'block';
    if (emptyState) emptyState.style.display = 'none';

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
        const status = call.status || 'initiated';
        const duration = call.duration || '--';
        const timeAgo = getTimeAgo(call.created_at || call.timestamp);

        // Status-based styling
        let statusLabel, tagClass;
        if (status === 'completed') {
            statusLabel = call.sentiment || 'Completed';
            tagClass = call.sentiment === 'Delighted' ? 'dash-tag-delighted' : 'dash-tag-interested';
        } else if (status === 'initiated' || status === 'ringing') {
            statusLabel = 'Initiated';
            tagClass = 'dash-tag-initiated';
        } else {
            statusLabel = status.charAt(0).toUpperCase() + status.slice(1);
            tagClass = 'dash-tag-initiated';
        }

        const div = document.createElement('div');
        div.className = 'dash-feed-item';
        div.onclick = () => openModal(call);
        div.innerHTML = `
            <div style="display: flex; align-items: center; gap: 12px;">
                <div class="dash-avatar">${initials}</div>
                <div class="dash-caller-info">
                    <span class="dash-caller-name">${escapeHtml(name)}</span>
                    <span class="dash-caller-meta">${escapeHtml(phone)} &middot; ${escapeHtml(source)} &middot; ${escapeHtml(duration)}</span>
                </div>
            </div>
            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
                <span class="${tagClass}">${escapeHtml(statusLabel)}</span>
                <span style="font-size: 11px; color: #7a7b7c; font-family: 'JetBrains Mono', monospace;">${escapeHtml(timeAgo)}</span>
            </div>
        `;
        container.appendChild(div);
    });
}

function openModal(call) {
    const modal = document.getElementById('callModal');
    if (!modal) return;

    const name = call.caller_name || call.name || 'Unknown Caller';
    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    const phone = call.caller_phone || call.phone || '--';
    const source = call.source === 'cta_form' ? 'CTA Form' : 'Instant Call';
    const duration = call.duration || '--';
    const status = call.status || 'initiated';

    document.getElementById('modalAvatar').innerText = initials;
    document.getElementById('modalName').innerText = name;
    document.getElementById('modalMeta').innerText = `${phone} \u2022 ${source} \u2022 Duration: ${duration} \u2022 Status: ${status}`;

    const chatList = document.getElementById('modalChatList');
    const transcript = call.transcript;

    // Only show real transcripts — no mock data
    if (!transcript || !Array.isArray(transcript) || transcript.length === 0) {
        chatList.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #7a7b7c;">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 12px; opacity: 0.4;">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                <p style="font-weight: 600; margin-bottom: 4px;">No transcript available</p>
                <p style="font-size: 12px;">
                    ${status === 'initiated' || status === 'ringing' 
                        ? 'This call was initiated but no conversation was recorded. The call may not have been answered.' 
                        : 'Transcript data is not available for this call.'}
                </p>
            </div>
        `;
    } else {
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
    }

    modal.classList.add('active');
}

function closeModal() {
    const modal = document.getElementById('callModal');
    if (modal) modal.classList.remove('active');
}

function openEditProfileModal() {
    if (!currentBusiness) return;
    const nameInput = document.getElementById('editBusinessName');
    const industrySelect = document.getElementById('editIndustry');
    const contactInput = document.getElementById('editContactName');
    const phoneInput = document.getElementById('editPhone');

    if (nameInput) nameInput.value = currentBusiness.business_name || '';
    if (industrySelect) industrySelect.value = currentBusiness.industry || 'General Business';
    if (contactInput) contactInput.value = currentBusiness.contact_name || '';
    if (phoneInput) phoneInput.value = currentBusiness.phone || '';

    const modal = document.getElementById('editProfileModal');
    if (modal) modal.classList.add('active');
}

function closeEditProfileModal() {
    const modal = document.getElementById('editProfileModal');
    if (modal) modal.classList.remove('active');
}

async function saveBusinessProfile(e) {
    if (e) e.preventDefault();
    if (!currentBusiness) return;

    const bName = document.getElementById('editBusinessName').value.trim();
    const ind = document.getElementById('editIndustry').value;
    const cName = document.getElementById('editContactName').value.trim();
    const ph = document.getElementById('editPhone').value.trim();

    const saveBtn = document.getElementById('saveProfileBtn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerText = 'Saving...';
    }

    try {
        const payload = {
            id: currentBusiness.id,
            business_name: bName || currentBusiness.business_name,
            industry: ind || 'General Business',
            contact_name: cName || currentBusiness.contact_name,
            email: currentBusiness.email,
            phone: ph
        };

        // 1. Update Supabase Database
        const { data, error } = await supabaseClient
            .from('businesses')
            .upsert([payload])
            .select()
            .maybeSingle();

        if (error) throw error;

        // 2. Update Supabase Auth Metadata
        if (supabaseClient.auth) {
            await supabaseClient.auth.updateUser({
                data: {
                    business_name: payload.business_name,
                    industry: payload.industry,
                    contact_name: payload.contact_name,
                    phone: payload.phone
                }
            }).catch(err => console.warn('Auth metadata update warning:', err));
        }

        currentBusiness = data || payload;
        renderBusinessInfo(currentBusiness);
        closeEditProfileModal();

    } catch (err) {
        console.error('Error saving business profile:', err);
        alert('Failed to update business profile: ' + (err.message || err));
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerText = 'Save Changes';
        }
    }
}

document.addEventListener('click', (e) => {
    const modal = document.getElementById('callModal');
    const testModal = document.getElementById('testCallModal');
    const editModal = document.getElementById('editProfileModal');
    if (modal && modal.classList.contains('active') && e.target === modal) {
        closeModal();
    }
    if (testModal && testModal.classList.contains('active') && e.target === testModal) {
        closeTestCallModal();
    }
    if (editModal && editModal.classList.contains('active') && e.target === editModal) {
        closeEditProfileModal();
    }
});

function showEmptyStates() {
    const chartCanvas = document.getElementById('simpleChart');
    const chartEmpty = document.getElementById('chartEmptyState');
    const feedEmpty = document.getElementById('feedEmptyState');

    if (chartCanvas) {
        chartCanvas.style.display = 'none';
        if (chartCanvas.parentElement) chartCanvas.parentElement.style.display = 'none';
    }
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
