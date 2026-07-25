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
    loadAgentConfigFromStorage();
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
            if (error.code === 'PGRST303' || (error.message && error.message.includes('JWT expired'))) {
                console.warn('JWT expired during auth check. Refreshing session...');
                const { data: refreshed } = await supabaseClient.auth.refreshSession().catch(() => ({}));
                if (refreshed && refreshed.session) {
                    const retry = await supabaseClient.from('businesses').select('*').eq('id', user.id).maybeSingle();
                    if (retry.data) businessData = retry.data;
                }
            }
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

    checkAdminAccess();
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
        let logsMap = new Map();

        // 1. Fetch from Supabase directly (all records or by business_id)
        try {
            const { data: supaLogs, error } = await supabaseClient
                .from('call_logs')
                .select('*')
                .order('created_at', { ascending: false });

            if (error) {
                console.warn('Supabase call_logs query error:', error);
            } else if (supaLogs && supaLogs.length > 0) {
                const bId = currentBusiness.id;
                const userEmail = (currentBusiness.email || '').toLowerCase();
                const userPhone = (currentBusiness.phone || '').replace(/\D/g, '');
                const userName = (currentBusiness.contact_name || currentBusiness.business_name || '').toLowerCase();

                supaLogs.forEach(l => {
                    if (l.caller_name === 'SYSTEM_AGENT_CONFIG' || l.status === 'config' || l.source === 'agent_config') {
                        return; // Ignore system config records from call analytics
                    }

                    const lPhone = (l.caller_phone || l.phone || '').replace(/\D/g, '');
                    const lEmail = (l.caller_email || l.email || '').toLowerCase();
                    const lName = (l.caller_name || l.name || '').toLowerCase();

                    const matchesId = l.business_id && l.business_id === bId;
                    const matchesEmail = userEmail && lEmail && lEmail === userEmail;
                    const matchesPhone = userPhone && lPhone && (lPhone.includes(userPhone) || userPhone.includes(lPhone));
                    const matchesName = userName && lName && (lName.includes(userName) || userName.includes(lName));

                    if (matchesId || matchesEmail || matchesPhone || matchesName || supaLogs.length <= 5) {
                        logsMap.set(l.id, l);

                        // Auto-link business_id in Supabase if missing
                        if (!l.business_id && bId) {
                            supabaseClient.from('call_logs')
                                .update({ business_id: bId })
                                .eq('id', l.id)
                                .then(() => {})
                                .catch(e => console.warn(e));
                        }
                    }
                });
            }
        } catch (e) {
            console.warn('Supabase fetch exception:', e);
        }

        let logs = Array.from(logsMap.values());

        // 2. Fallback to Backend API (/api/call-logs) if Supabase returned 0 logs
        if (logs.length === 0) {
            const endpoints = [
                'https://ai-telephony-agent.onrender.com/api/call-logs',
                'http://localhost:8081/api/call-logs',
                'http://127.0.0.1:8081/api/call-logs'
            ];

            for (const ep of endpoints) {
                try {
                    const resp = await fetch(ep);
                    if (resp.ok) {
                        const apiLogs = await resp.json();
                        if (Array.isArray(apiLogs) && apiLogs.length > 0) {
                            logs = apiLogs;
                            break;
                        }
                    }
                } catch (e) {
                    // Try next endpoint
                }
            }
        }

        // Sort logs descending by timestamp/created_at
        logs.sort((a, b) => {
            const dA = new Date(a.created_at || a.timestamp || 0);
            const dB = new Date(b.created_at || b.timestamp || 0);
            return dB - dA;
        });

        allCallLogs = logs;

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
        } else if (status === 'no_answer') {
            statusLabel = 'No Answer';
            tagClass = 'dash-tag-no-answer';
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

// ========================================
// SIDEBAR TAB SWITCHING & ENGINE CONFIG
// ========================================

function switchDashboardTab(tabName) {
    const tabAnalytics = document.getElementById('tabAnalytics');
    const tabConfig = document.getElementById('tabConfig');
    const tabAdmin = document.getElementById('tabAdmin');
    const navAnalyticsBtn = document.getElementById('navAnalyticsBtn');
    const navConfigBtn = document.getElementById('navConfigBtn');
    const navAdminBtn = document.getElementById('navAdminBtn');

    if (tabName === 'admin') {
        if (tabAnalytics) tabAnalytics.style.display = 'none';
        if (tabConfig) tabConfig.style.display = 'none';
        if (tabAdmin) tabAdmin.style.display = 'block';
        if (navAnalyticsBtn) navAnalyticsBtn.classList.remove('active');
        if (navConfigBtn) navConfigBtn.classList.remove('active');
        if (navAdminBtn) navAdminBtn.classList.add('active');
        loadAdminUserList();
    } else if (tabName === 'config') {
        if (tabAnalytics) tabAnalytics.style.display = 'none';
        if (tabConfig) tabConfig.style.display = 'block';
        if (tabAdmin) tabAdmin.style.display = 'none';
        if (navAnalyticsBtn) navAnalyticsBtn.classList.remove('active');
        if (navConfigBtn) navConfigBtn.classList.add('active');
        if (navAdminBtn) navAdminBtn.classList.remove('active');
        loadAgentConfigFromStorage();
    } else {
        if (tabAnalytics) tabAnalytics.style.display = 'block';
        if (tabConfig) tabConfig.style.display = 'none';
        if (tabAdmin) tabAdmin.style.display = 'none';
        if (navAnalyticsBtn) navAnalyticsBtn.classList.add('active');
        if (navConfigBtn) navConfigBtn.classList.remove('active');
        if (navAdminBtn) navAdminBtn.classList.remove('active');
    }

    // Auto close sidebar drawer on mobile after clicking
    if (window.innerWidth <= 768) {
        toggleSidebarDrawer();
    }
}

// ========================================
// SUPER ADMIN CONTROL PANEL LOGIC
// ========================================

const KOKORO_VOICES = [
    { value: 'am_adam', label: 'Adam — Deep Male (US English)' },
    { value: 'af_bella', label: 'Bella — Expressive Female (US English)' },
    { value: 'am_michael', label: 'Michael — Professional Male (US English)' },
    { value: 'af_heart', label: 'Heart — Warm Female (US English)' },
    { value: 'af_nicole', label: 'Nicole — Clear Female (US English)' },
    { value: 'af_sky', label: 'Sky — Lively Female (US English)' },
    { value: 'af_sarah', label: 'Sarah — Warm Receptionist Female (US English)' },
    { value: 'af_alloy', label: 'Alloy — Balanced Female (US English)' },
    { value: 'am_echo', label: 'Echo — Smooth Male (US English)' },
    { value: 'am_eric', label: 'Eric — Friendly Male (US English)' },
    { value: 'bf_emma', label: 'Emma — British Female (UK English)' },
    { value: 'bm_george', label: 'George — British Male (UK English)' }
];

const VIDEOSDK_VOICES = [
    { value: 'Callirrhoe', label: 'Callirrhoe — Clear, Expressive Neutral / Female' },
    { value: 'Laomedeia', label: 'Laomedeia — Smooth, Melodic Female' },
    { value: 'Aoede', label: 'Aoede — Warm, Conversational Female' },
    { value: 'Leda', label: 'Leda — Warm, Professional Female' },
    { value: 'Algenib', label: 'Algenib — Crisp, Articulate Neutral' },
    { value: 'Fenrir', label: 'Fenrir — Deep, Smooth Male' },
    { value: 'Charon', label: 'Charon — Professional, Authoritative Male' },
    { value: 'Iapetus', label: 'Iapetus — Deep, Warm Male' },
    { value: 'Gacrux', label: 'Gacrux — Resonant, Steady Male' },
    { value: 'Sulafat', label: 'Sulafat — Expressive, Dynamic Female' },
    { value: 'Kore', label: 'Kore — Calm, Relaxed Female' },
    { value: 'Puck', label: 'Puck — Energetic, Playful Male' }
];

async function checkAdminAccess() {
    const navAdminBtn = document.getElementById('navAdminBtn');
    const saveConfigBtn = document.getElementById('saveConfigBtn');
    const adminEmailNotice = document.getElementById('adminEmailNotice');

    let isSuperAdmin = false;

    if (currentBusiness && currentBusiness.email && typeof supabaseClient !== 'undefined' && supabaseClient) {
        try {
            const { data, error } = await supabaseClient
                .from('admin_users')
                .select('*')
                .eq('email', currentBusiness.email)
                .maybeSingle();

            if (!error && data && (data.role === 'super_admin' || data.role === 'admin')) {
                isSuperAdmin = true;
            }
        } catch (e) {
            console.warn('Error checking admin_users table:', e);
        }
        
        // Fallback for primary setup
        if (!isSuperAdmin && currentBusiness.email === 'dukeindustries7@gmail.com') {
            isSuperAdmin = true;
        }
    }

    if (adminEmailNotice && currentBusiness) {
        adminEmailNotice.innerText = `(${currentBusiness.email})`;
    }

    if (navAdminBtn) {
        navAdminBtn.style.display = isSuperAdmin ? 'flex' : 'none';
    }

    if (!isSuperAdmin) {
        // Non-admin users: make config tab read-only
        if (saveConfigBtn) saveConfigBtn.style.display = 'none';
        const cfgSaveStatus = document.getElementById('configSaveStatus');
        if (cfgSaveStatus) {
            cfgSaveStatus.style.display = 'inline-flex';
            cfgSaveStatus.style.background = 'rgba(239, 68, 68, 0.1)';
            cfgSaveStatus.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            cfgSaveStatus.style.color = '#dc2626';
            cfgSaveStatus.innerHTML = '🔒 Managed Configuration (Read Only)';
        }
    } else {
        if (saveConfigBtn) saveConfigBtn.style.display = 'inline-block';
    }
}

async function loadAdminUserList() {
    const selectElem = document.getElementById('adminTargetUserSelect');
    if (!selectElem) return;

    selectElem.innerHTML = '<option value="">Loading registered users...</option>';
    try {
        if (typeof supabaseClient !== 'undefined' && supabaseClient) {
            const { data: users, error } = await supabaseClient
                .from('businesses')
                .select('*')
                .order('created_at', { ascending: false });

            if (!error && users && users.length > 0) {
                selectElem.innerHTML = users.map(u => 
                    `<option value="${u.id}">${u.business_name || 'Business'} (${u.email || u.contact_name || u.id})</option>`
                ).join('');
                onAdminTargetUserChange();
                return;
            }
        }
    } catch (e) {
        console.warn('Error fetching users for Admin Panel:', e);
    }
    
    // Fallback if DB list empty
    if (currentBusiness) {
        selectElem.innerHTML = `<option value="${currentBusiness.id}">${currentBusiness.business_name} (${currentBusiness.email})</option>`;
        onAdminTargetUserChange();
    }
}

function selectAdminEngineProvider(provider) {
    const adminCardKokoro = document.getElementById('adminCardKokoro');
    const adminCardVideoSdk = document.getElementById('adminCardVideoSdk');
    const adminRadioKokoro = document.getElementById('adminRadioKokoro');
    const adminRadioVideoSdk = document.getElementById('adminRadioVideoSdk');
    const adminVideoSdkIdWrap = document.getElementById('adminVideoSdkIdWrap');

    if (provider === 'videosdk') {
        if (adminCardKokoro) adminCardKokoro.classList.remove('active');
        if (adminCardVideoSdk) adminCardVideoSdk.classList.add('active');
        if (adminRadioKokoro) adminRadioKokoro.checked = false;
        if (adminRadioVideoSdk) adminRadioVideoSdk.checked = true;
        if (adminVideoSdkIdWrap) adminVideoSdkIdWrap.style.display = 'block';
        populateAdminVoiceOptions('videosdk');
    } else {
        if (adminCardKokoro) adminCardKokoro.classList.add('active');
        if (adminCardVideoSdk) adminCardVideoSdk.classList.remove('active');
        if (adminRadioKokoro) adminRadioKokoro.checked = true;
        if (adminRadioVideoSdk) adminRadioVideoSdk.checked = false;
        if (adminVideoSdkIdWrap) adminVideoSdkIdWrap.style.display = 'none';
        populateAdminVoiceOptions('kokoro');
    }
}

function populateAdminVoiceOptions(provider, selectedVoice = null) {
    const voiceSelect = document.getElementById('adminVoiceSelect');
    if (!voiceSelect) return;

    const voices = provider === 'videosdk' ? VIDEOSDK_VOICES : KOKORO_VOICES;
    voiceSelect.innerHTML = voices.map(v => 
        `<option value="${v.value}" ${selectedVoice === v.value ? 'selected' : ''}>${v.label}</option>`
    ).join('');

    if (!selectedVoice && voices.length > 0) {
        voiceSelect.value = voices[0].value;
    }
}

async function onAdminTargetUserChange() {
    const targetBusinessId = document.getElementById('adminTargetUserSelect')?.value;
    if (!targetBusinessId || typeof supabaseClient === 'undefined' || !supabaseClient) return;

    try {
        const { data, error } = await supabaseClient
            .from('agent_configs')
            .select('*')
            .eq('business_id', targetBusinessId)
            .maybeSingle();

        if (!error && data && data.config) {
            const cfg = typeof data.config === 'string' ? JSON.parse(data.config) : data.config;
            const provider = cfg.provider === 'videosdk' ? 'videosdk' : 'kokoro';
            selectAdminEngineProvider(provider);

            if (cfg.video_sdk_agent_id) {
                const sdkInput = document.getElementById('adminVideoSdkAgentId');
                if (sdkInput) sdkInput.value = cfg.video_sdk_agent_id;
            }

            const currentVoice = cfg.gemini?.voice || cfg.kokoro?.voice || cfg.voice;
            populateAdminVoiceOptions(provider, currentVoice);

            if (cfg.agent_name) {
                const nameInput = document.getElementById('adminAgentName');
                if (nameInput) nameInput.value = cfg.agent_name;
            }
            if (cfg.greeting) {
                const greetInput = document.getElementById('adminAgentGreeting');
                if (greetInput) greetInput.value = cfg.greeting;
            }
            if (cfg.system_instruction) {
                const promptInput = document.getElementById('adminSystemPrompt');
                if (promptInput) promptInput.value = cfg.system_instruction;
            }
        } else {
            selectAdminEngineProvider('kokoro');
        }
    } catch (e) {
        console.warn('Error loading admin target user config:', e);
    }
}

async function saveAdminUserConfig() {
    const targetBusinessId = document.getElementById('adminTargetUserSelect')?.value;
    if (!targetBusinessId) {
        alert('Please select a target user account.');
        return;
    }

    const isVideoSdk = document.getElementById('adminRadioVideoSdk')?.checked;
    const provider = isVideoSdk ? 'videosdk' : 'kokoro';
    const videoSdkAgentId = isVideoSdk ? document.getElementById('adminVideoSdkAgentId')?.value.trim() : '';
    const selectedVoice = document.getElementById('adminVoiceSelect')?.value || 'Aoede';
    const agentName = document.getElementById('adminAgentName')?.value.trim() || 'Sarah';
    const greeting = document.getElementById('adminAgentGreeting')?.value.trim() || '';
    const systemPrompt = document.getElementById('adminSystemPrompt')?.value.trim() || '';

    const payload = {
        provider: provider,
        video_sdk_agent_id: videoSdkAgentId,
        agent_name: agentName,
        greeting: greeting,
        system_instruction: systemPrompt,
        gemini: {
            model: 'models/gemini-3.1-flash-live-preview',
            voice: selectedVoice,
            vad_silence_ms: 200
        },
        kokoro: {
            voice: selectedVoice,
            speed: 1.0
        }
    };

    // 1. Save directly to Supabase agent_configs table under target business_id
    if (typeof supabaseClient !== 'undefined' && supabaseClient) {
        try {
            await supabaseClient.from('agent_configs').upsert({
                business_id: targetBusinessId,
                provider: provider,
                config: payload,
                updated_at: new Date().toISOString()
            }, { onConflict: 'business_id' });
        } catch (err) {
            console.warn('Error saving admin config to Supabase agent_configs table:', err);
        }
    }

    // 2. Post to backend API
    try {
        await fetch(getBackendUrl('/api/config'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...payload, business_id: targetBusinessId })
        });
    } catch (e) {}

    // Show success button animation
    const saveBtn = document.querySelector('button[onclick="saveAdminUserConfig()"]');
    const originalBtnHtml = saveBtn ? saveBtn.innerHTML : 'Save & Attach Config to User';

    if (saveBtn) {
        saveBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        saveBtn.innerHTML = `✓ User Configuration Saved & Attached!`;
    }

    const statusElem = document.getElementById('adminSaveStatus');
    if (statusElem) {
        statusElem.style.display = 'inline-flex';
    }

    setTimeout(() => {
        if (statusElem) statusElem.style.display = 'none';
        if (saveBtn) {
            saveBtn.style.background = 'linear-gradient(135deg, #ff5065, #ff7a59)';
            saveBtn.innerHTML = originalBtnHtml;
        }
    }, 3000);
}

function selectEngineProvider(provider) {
    const cardGemini = document.getElementById('cardGemini');
    const cardKokoro = document.getElementById('cardKokoro');
    const radioGemini = document.getElementById('radioGemini');
    const radioKokoro = document.getElementById('radioKokoro');
    const secGeminiControls = document.getElementById('secGeminiControls');
    const secKokoroControls = document.getElementById('secKokoroControls');

    if (provider === 'kokoro') {
        if (cardGemini) cardGemini.classList.remove('active');
        if (cardKokoro) cardKokoro.classList.add('active');
        if (radioGemini) radioGemini.checked = false;
        if (radioKokoro) radioKokoro.checked = true;

        if (secGeminiControls) secGeminiControls.style.display = 'none';
        if (secKokoroControls) secKokoroControls.style.display = 'block';
    } else {
        if (cardGemini) cardGemini.classList.add('active');
        if (cardKokoro) cardKokoro.classList.remove('active');
        if (radioGemini) radioGemini.checked = true;
        if (radioKokoro) radioKokoro.checked = false;

        if (secGeminiControls) secGeminiControls.style.display = 'block';
        if (secKokoroControls) secKokoroControls.style.display = 'none';
    }
}

function getBackendUrl(path) {
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const baseUrl = isLocal ? `${window.location.protocol}//${window.location.hostname}:8081` : 'https://ai-telephony-agent.onrender.com';
    return `${baseUrl}${path}`;
}

async function loadAgentConfigFromSupabase() {
    if (typeof supabaseClient === 'undefined' || !supabaseClient) return null;
    try {
        // 1. Query dedicated agent_configs table first
        const { data: acData, error: acErr } = await supabaseClient
            .from('agent_configs')
            .select('*')
            .limit(1);

        if (!acErr && acData && acData.length > 0 && acData[0].config) {
            const cfg = typeof acData[0].config === 'string' ? JSON.parse(acData[0].config) : acData[0].config;
            if (cfg && Object.keys(cfg).length > 0) return cfg;
        }

        // 2. Fallback to call_logs table
        const { data, error } = await supabaseClient
            .from('call_logs')
            .select('*')
            .eq('caller_name', 'SYSTEM_AGENT_CONFIG')
            .order('created_at', { ascending: false })
            .limit(1);

        if (!error && data && data.length > 0 && data[0].transcript) {
            const config = JSON.parse(data[0].transcript);
            return config;
        }
    } catch (e) {
        console.warn('Could not load config from Supabase:', e);
    }
    return null;
}

async function loadAgentConfigFromStorage() {
    let config = null;

    // 1. Read from localStorage immediately on refresh so UI updates instantly
    const stored = localStorage.getItem('mixup_agent_config');
    if (stored) {
        try { config = JSON.parse(stored); } catch (e) {}
    }

    if (config) {
        populateConfigUI(config);
    }

    // 2. Sync with Supabase Cloud DB & Backend API asynchronously
    try {
        const spConfig = await loadAgentConfigFromSupabase();
        if (spConfig) {
            config = spConfig;
            localStorage.setItem('mixup_agent_config', JSON.stringify(spConfig));
            populateConfigUI(spConfig);
        } else {
            const resp = await fetch(getBackendUrl('/api/config'));
            if (resp.ok) {
                const remoteConfig = await resp.json();
                if (remoteConfig && Object.keys(remoteConfig).length > 0) {
                    localStorage.setItem('mixup_agent_config', JSON.stringify(remoteConfig));
                    populateConfigUI(remoteConfig);
                }
            }
        }
    } catch (e) {
        console.warn('Could not fetch config from backend/Supabase:', e);
    }

    // 3. Fallback defaults if still empty
    if (!config) {
        config = {
            provider: 'gemini',
            gemini: {
                model: 'models/gemini-3.1-flash-live-preview',
                voice: 'Aoede',
                vad_silence_ms: 200
            },
            kokoro: {
                voice: 'am_adam',
                speed: 1.0
            },
            system_instruction: "You are a warm, helpful sales receptionist for Mixup AI. Greet the caller nicely, answer questions naturally, and collect their name and company to schedule a demo."
        };
        populateConfigUI(config);
    }
}

function populateConfigUI(config) {
    if (!config) return;

    selectEngineProvider(config.provider || 'gemini');

    if (config.gemini) {
        const cfgVoice = document.getElementById('cfgGeminiVoice');
        const cfgModel = document.getElementById('cfgGeminiModel');
        const cfgVad = document.getElementById('cfgGeminiVad');

        if (cfgVoice && config.gemini.voice) cfgVoice.value = config.gemini.voice;
        if (cfgModel && config.gemini.model) cfgModel.value = config.gemini.model;
        if (cfgVad && config.gemini.vad_silence_ms) cfgVad.value = config.gemini.vad_silence_ms;
    }

    if (config.kokoro) {
        const cfgKokoroVoice = document.getElementById('cfgKokoroVoice');
        const cfgKokoroSpeed = document.getElementById('cfgKokoroSpeed');

        if (cfgKokoroVoice && config.kokoro.voice) {
            cfgKokoroVoice.value = config.kokoro.voice;
        }
        if (cfgKokoroSpeed) {
            const rawSpeed = config.kokoro.speed;
            const parsedSpeed = (rawSpeed !== null && rawSpeed !== undefined && !isNaN(parseFloat(rawSpeed))) ? parseFloat(rawSpeed).toFixed(1) : "1.0";
            cfgKokoroSpeed.value = parsedSpeed;
        }
    }

    const cfgPrompt = document.getElementById('cfgSystemPrompt');
    if (cfgPrompt && config.system_instruction) {
        cfgPrompt.value = config.system_instruction;
    }

    const cfgAgentName = document.getElementById('cfgAgentName');
    if (cfgAgentName && config.agent_name) {
        cfgAgentName.value = config.agent_name;
    }

    const cfgAgentGreeting = document.getElementById('cfgAgentGreeting');
    if (cfgAgentGreeting && config.greeting) {
        cfgAgentGreeting.value = config.greeting;
    }

    const cfgVideoSdkAgentId = document.getElementById('cfgVideoSdkAgentId');
    if (cfgVideoSdkAgentId && config.video_sdk_agent_id !== undefined) {
        cfgVideoSdkAgentId.value = config.video_sdk_agent_id;
    }

    updateVideoSdkNotice();
}

function updateVideoSdkNotice() {
    const agentIdElem = document.getElementById('cfgVideoSdkAgentId');
    const noticeElem = document.getElementById('videoSdkCloudNotice');
    const agentIdVal = agentIdElem ? agentIdElem.value.trim() : '';

    if (noticeElem) {
        if (agentIdVal !== '') {
            noticeElem.style.display = 'block';
            noticeElem.innerHTML = `<strong>ℹ️ VideoSDK Cloud Agent Active (${agentIdVal})</strong><br>Phone calls will route to your VideoSDK Cloud Agent. Its pipeline model, voice, system prompt, and tools are configured directly inside your <a href="https://console.videosdk.live" target="_blank" style="color: #2563eb; font-weight: 700; text-decoration: underline;">VideoSDK Agent Builder console</a>.<br><br>💡 <em>To configure voices for your Custom Python Agent instead, clear the VideoSDK Cloud Agent Builder ID field above.</em>`;
        } else {
            noticeElem.style.display = 'none';
        }
    }
}

async function saveAgentConfig() {
    const radioKokoro = document.getElementById('radioKokoro');
    const provider = radioKokoro && radioKokoro.checked ? 'kokoro' : 'gemini';

    const cfgGeminiVoice = document.getElementById('cfgGeminiVoice');
    const cfgGeminiModel = document.getElementById('cfgGeminiModel');
    const cfgGeminiVad = document.getElementById('cfgGeminiVad');

    const cfgKokoroVoice = document.getElementById('cfgKokoroVoice');
    const cfgKokoroSpeed = document.getElementById('cfgKokoroSpeed');

    const cfgVideoSdkAgentId = document.getElementById('cfgVideoSdkAgentId');
    const cfgAgentName = document.getElementById('cfgAgentName');
    const cfgAgentGreeting = document.getElementById('cfgAgentGreeting');
    const cfgSystemPrompt = document.getElementById('cfgSystemPrompt');

    const rawSpeed = cfgKokoroSpeed ? parseFloat(cfgKokoroSpeed.value) : 1.0;
    const speedVal = isNaN(rawSpeed) ? 1.0 : rawSpeed;

    const payload = {
        provider: provider,
        video_sdk_agent_id: cfgVideoSdkAgentId ? cfgVideoSdkAgentId.value.trim() : '',
        agent_name: cfgAgentName ? cfgAgentName.value.trim() : 'Sarah',
        greeting: cfgAgentGreeting ? cfgAgentGreeting.value.trim() : "Hi! Thanks for checking out our site. I'm an AI assistant. Should I have my human team reach out to schedule a full demo?",
        gemini: {
            model: cfgGeminiModel ? cfgGeminiModel.value : 'models/gemini-3.1-flash-live-preview',
            voice: cfgGeminiVoice ? cfgGeminiVoice.value : 'Aoede',
            vad_silence_ms: cfgGeminiVad ? parseInt(cfgGeminiVad.value, 10) : 200
        },
        kokoro: {
            voice: cfgKokoroVoice ? cfgKokoroVoice.value : 'am_adam',
            speed: speedVal
        },
        system_instruction: cfgSystemPrompt ? cfgSystemPrompt.value.trim() : ''
    };

    // 1. Save to localStorage
    localStorage.setItem('mixup_agent_config', JSON.stringify(payload));

    // 2. Save directly to Supabase agent_configs table
    if (typeof supabaseClient !== 'undefined' && supabaseClient && currentBusiness) {
        try {
            await supabaseClient.from('agent_configs').upsert({
                business_id: currentBusiness.id,
                provider: provider,
                config: payload,
                updated_at: new Date().toISOString()
            }, { onConflict: 'business_id' });
        } catch (err) {
            console.warn('Error saving config to Supabase agent_configs table:', err);
        }
    }

    // 3. Send to backend API
    try {
        const resp = await fetch(getBackendUrl('/api/config'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (resp.ok) {
            console.log('Configuration saved to backend API successfully');
        }
    } catch (e) {
        console.warn('Failed to post config to backend API:', e);
    }

    // Show status indicator & button success animation
    const saveBtn = document.querySelector('button[onclick="saveAgentConfig()"]');
    const originalBtnHtml = saveBtn ? saveBtn.innerHTML : 'Save & Apply Settings';

    if (saveBtn) {
        saveBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        saveBtn.innerHTML = `✓ Settings Saved & Applied!`;
    }

    const statusElem = document.getElementById('configSaveStatus');
    if (statusElem) {
        statusElem.style.display = 'inline-flex';
        statusElem.style.alignItems = 'center';
        statusElem.style.gap = '6px';
        statusElem.style.padding = '8px 16px';
        statusElem.style.background = 'rgba(16, 185, 129, 0.12)';
        statusElem.style.border = '1px solid rgba(16, 185, 129, 0.3)';
        statusElem.style.borderRadius = '20px';
        statusElem.style.color = '#059669';
        statusElem.style.fontWeight = '700';
    }

    setTimeout(() => {
        if (statusElem) statusElem.style.display = 'none';
        if (saveBtn) {
            saveBtn.style.background = 'linear-gradient(135deg, #ff5065, #ff7a59)';
            saveBtn.innerHTML = originalBtnHtml;
        }
    }, 3000);
}

