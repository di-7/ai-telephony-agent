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
        applyTimeRangeFilter(selectedTimeRange);

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

    // Add play/download recording buttons if recording_url exists
    const recordingUrl = call.recording_url;
    const downloadBtnContainer = document.getElementById('modalDownloadBtn');
    if (downloadBtnContainer) {
        if (recordingUrl) {
            downloadBtnContainer.style.display = 'flex';
            downloadBtnContainer.style.gap = '8px';
            downloadBtnContainer.style.alignItems = 'center';
            downloadBtnContainer.innerHTML = `
                <button onclick="toggleRecordingPlayer('${escapeHtml(recordingUrl)}')" 
                   style="display: inline-flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #3b82f6, #2563eb); color: #fff; padding: 8px 16px; border: none; border-radius: 8px; font-weight: 600; font-size: 13px; cursor: pointer;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polygon points="5 3 19 12 5 21 5 3"/>
                    </svg>
                    Play Recording
                </button>
                <a href="${escapeHtml(recordingUrl)}" download="recording_${call.id}.mp4" target="_blank" 
                   style="display: inline-flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #10b981, #059669); color: #fff; padding: 8px 16px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 13px;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download
                </a>
            `;
        } else {
            downloadBtnContainer.style.display = 'none';
        }
    }
    
    // Hide recording player by default
    const recordingPlayerContainer = document.getElementById('modalRecordingPlayer');
    if (recordingPlayerContainer) {
        recordingPlayerContainer.style.display = 'none';
    }

    const chatList = document.getElementById('modalChatList');
    const transcript = call.transcript;

    // Only show real transcripts — auto-poll if call completed recently without transcript
    if (!transcript || !Array.isArray(transcript) || transcript.length === 0) {
        chatList.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #7a7b7c;">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 12px; opacity: 0.4;">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                <p style="font-weight: 600; margin-bottom: 4px; id="modalTranscriptTitle">No transcript available</p>
                <p style="font-size: 12px;" id="modalTranscriptSubtitle">
                    ${status === 'initiated' || status === 'ringing' 
                        ? 'This call was initiated but no conversation was recorded. The call may not have been answered.' 
                        : 'Transcript processing... VideoSDK Cloud indexes post-call audio within 20 seconds.'}
                </p>
            </div>
        `;

        // If call was recently completed but transcript is missing, auto-poll Supabase after 5s
        if (call.id && (status === 'completed' || status === 'ended')) {
            setTimeout(async () => {
                try {
                    const { data: updated } = await supabaseClient
                        .from('call_logs')
                        .select('*')
                        .eq('id', call.id)
                        .maybeSingle();

                    if (updated && Array.isArray(updated.transcript) && updated.transcript.length > 0) {
                        call.transcript = updated.transcript;
                        call.duration = updated.duration || call.duration;
                        call.status = updated.status || call.status;
                        openModal(call); // Re-render with new transcript
                        fetchBusinessDashboardData(); // Refresh feed
                    }
                } catch (e) {
                    console.warn('Auto-poll transcript error:', e);
                }
            }, 5000);
        }
    } else {
        chatList.innerHTML = transcript.map(msg => {
            const rawSpeaker = (msg.speaker || '').toLowerCase();
            const rawName = (msg.name || '').toLowerCase();
            const callerNameClean = (name || call.caller_name || '').toLowerCase();

            // Dynamic agent check — zero hardcoded names
            const isUserRole = rawSpeaker === 'user' || rawSpeaker === 'caller' || rawSpeaker === 'customer' || (rawName && rawName === callerNameClean);
            const isAgentRole = rawSpeaker === 'agent' || rawSpeaker === 'ai' || rawSpeaker === 'system' || rawSpeaker === 'assistant' || rawSpeaker === 'bot';
            
            const isAgent = isAgentRole || (!isUserRole && rawSpeaker !== '');

            const speakerIcon = isAgent
                ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
                : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
            
            const speakerName = isAgent 
                ? (msg.name || 'AI Agent')
                : (msg.name || name || 'Caller');

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

let selectedTimeRange = '30d';

function getFilteredCallLogs(logs, range) {
    if (!logs || logs.length === 0) return [];
    if (!range || range === 'all') return logs;

    const now = new Date();
    let startTime;

    if (range === 'today') {
        startTime = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
    } else if (range === '7d') {
        startTime = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
    } else if (range === '30d') {
        startTime = new Date(now.getTime() - (30 * 24 * 60 * 60 * 1000));
    } else {
        return logs;
    }

    return logs.filter(l => {
        const logDate = new Date(l.created_at || l.timestamp || 0);
        return logDate >= startTime;
    });
}

function applyTimeRangeFilter(range) {
    selectedTimeRange = range;
    const filtered = getFilteredCallLogs(allCallLogs, selectedTimeRange);
    updateKPIs(filtered);
    initChart(filtered);
    renderFeed(filtered);
}

function setupEvents() {
    document.querySelectorAll('.dash-filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.dash-filter-btn').forEach(b => b.classList.remove('active'));
            const target = e.currentTarget || e.target;
            target.classList.add('active');
            const range = target.getAttribute('data-range') || '30d';
            applyTimeRangeFilter(range);
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
    const tabAdmin = document.getElementById('tabAdmin');
    const tabSchedule = document.getElementById('tabSchedule');
    const navAnalyticsBtn = document.getElementById('navAnalyticsBtn');
    const navScheduleBtn = document.getElementById('navScheduleBtn');
    const navConfigBtn = document.getElementById('navConfigBtn');

    if (tabName === 'schedule') {
        if (tabAnalytics) tabAnalytics.style.display = 'none';
        if (tabAdmin) tabAdmin.style.display = 'none';
        if (tabSchedule) tabSchedule.style.display = 'block';
        if (navAnalyticsBtn) navAnalyticsBtn.classList.remove('active');
        if (navScheduleBtn) navScheduleBtn.classList.add('active');
        if (navConfigBtn) navConfigBtn.classList.remove('active');
        loadScheduledCallsQueue();
        toggleSchedNow(document.getElementById('schedNowCheckbox')?.checked || false);
    } else if (tabName === 'config' || tabName === 'admin') {
        if (tabAnalytics) tabAnalytics.style.display = 'none';
        if (tabAdmin) tabAdmin.style.display = 'block';
        if (tabSchedule) tabSchedule.style.display = 'none';
        if (navAnalyticsBtn) navAnalyticsBtn.classList.remove('active');
        if (navScheduleBtn) navScheduleBtn.classList.remove('active');
        if (navConfigBtn) navConfigBtn.classList.add('active');
        loadAdminUserList();
    } else {
        if (tabAnalytics) tabAnalytics.style.display = 'block';
        if (tabAdmin) tabAdmin.style.display = 'none';
        if (tabSchedule) tabSchedule.style.display = 'none';
        if (navAnalyticsBtn) navAnalyticsBtn.classList.add('active');
        if (navScheduleBtn) navScheduleBtn.classList.remove('active');
        if (navConfigBtn) navConfigBtn.classList.remove('active');
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
    const navConfigBtn = document.getElementById('navConfigBtn');
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

    if (isSuperAdmin) {
        // Super Admin sees Agent Config tab
        if (navConfigBtn) navConfigBtn.style.display = 'flex';
        if (saveConfigBtn) saveConfigBtn.style.display = 'inline-block';
    } else {
        // Normal user: HIDE Agent Config tab from sidebar completely
        if (navConfigBtn) navConfigBtn.style.display = 'none';
        if (saveConfigBtn) saveConfigBtn.style.display = 'none';
        
        // Switch normal user to Analytics tab
        switchDashboardTab('analytics');
    }
}

async function loadAdminUserList() {
    const selectElem = document.getElementById('adminTargetUserSelect');
    if (!selectElem) return;

    selectElem.innerHTML = '<option value="">Loading registered users...</option>';
    const userMap = new Map();

    // 1. Add current business profile
    if (currentBusiness && currentBusiness.id) {
        userMap.set(currentBusiness.id, {
            id: currentBusiness.id,
            name: currentBusiness.business_name || 'My Business',
            email: currentBusiness.email || ''
        });
    }

    try {
        if (typeof supabaseClient !== 'undefined' && supabaseClient) {
            // 2. Query businesses table
            const { data: businesses } = await supabaseClient
                .from('businesses')
                .select('*');

            if (businesses && businesses.length > 0) {
                businesses.forEach(b => {
                    userMap.set(b.id, {
                        id: b.id,
                        name: b.business_name || 'Business',
                        email: b.email || b.contact_name || b.id
                    });
                });
            }

            // 3. Query agent_configs table
            const { data: configs } = await supabaseClient
                .from('agent_configs')
                .select('business_id');

            if (configs && configs.length > 0) {
                configs.forEach(c => {
                    if (c.business_id && !userMap.has(c.business_id)) {
                        userMap.set(c.business_id, {
                            id: c.business_id,
                            name: 'User Account',
                            email: c.business_id
                        });
                    }
                });
            }
        }
    } catch (e) {
        console.warn('Error fetching users for Admin Panel:', e);
    }

    const allUsers = Array.from(userMap.values());
    if (allUsers.length > 0) {
        selectElem.innerHTML = allUsers.map(u => 
            `<option value="${u.id}">${u.name} (${u.email || u.id})</option>`
        ).join('');
        onAdminTargetUserChange();
    } else {
        selectElem.innerHTML = '<option value="">No registered users found</option>';
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

        const sdkInput = document.getElementById('adminVideoSdkAgentId');
        if (!error && data && data.config) {
            const cfg = typeof data.config === 'string' ? JSON.parse(data.config) : data.config;
            if (sdkInput) sdkInput.value = cfg.video_sdk_agent_id || '';
        } else {
            if (sdkInput) sdkInput.value = '';
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

    const videoSdkAgentId = document.getElementById('adminVideoSdkAgentId')?.value.trim() || '';
    const provider = 'videosdk';

    const payload = {
        provider: provider,
        video_sdk_agent_id: videoSdkAgentId,
        business_id: targetBusinessId
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
    } catch (err) {
        console.warn('Error posting admin config to backend API:', err);
    }

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
    }, 4000);
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
            provider: 'kokoro',
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

    selectEngineProvider(config.provider || 'videosdk');

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
    const cfgVideoSdkAgentId = document.getElementById('cfgVideoSdkAgentId');
    const videoSdkAgentId = cfgVideoSdkAgentId ? cfgVideoSdkAgentId.value.trim() : '';
    const provider = 'videosdk';

    const cfgGeminiVoice = document.getElementById('cfgGeminiVoice');
    const cfgGeminiModel = document.getElementById('cfgGeminiModel');
    const cfgGeminiVad = document.getElementById('cfgGeminiVad');

    const cfgAgentName = document.getElementById('cfgAgentName');
    const cfgAgentGreeting = document.getElementById('cfgAgentGreeting');
    const cfgSystemPrompt = document.getElementById('cfgSystemPrompt');

    const payload = {
        provider: provider,
        video_sdk_agent_id: videoSdkAgentId,
        agent_name: cfgAgentName ? cfgAgentName.value.trim() : 'Sarah',
        greeting: cfgAgentGreeting ? cfgAgentGreeting.value.trim() : "Hi! Thanks for checking out our site. I'm an AI assistant. Should I have my human team reach out to schedule a full demo?",
        gemini: {
            model: cfgGeminiModel ? cfgGeminiModel.value : 'gemini-2.0-flash-exp',
            voice: cfgGeminiVoice ? cfgGeminiVoice.value : 'Aoede',
            vad_silence_ms: cfgGeminiVad ? parseInt(cfgGeminiVad.value, 10) : 200
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

// ========================================
// CALL SCHEDULING & BATCH CAMPAIGN LOGIC
// ========================================

let currentSchedMode = 'single';
let currentBatchParsedContacts = [];

function setSchedMode(mode) {
    currentSchedMode = mode;
    const singleBtn = document.getElementById('schedModeSingleBtn');
    const batchBtn = document.getElementById('schedModeBatchBtn');
    const singleForm = document.getElementById('singleLeadForm');
    const batchForm = document.getElementById('batchUploadForm');

    if (mode === 'batch') {
        if (singleBtn) singleBtn.classList.remove('active');
        if (batchBtn) batchBtn.classList.add('active');
        if (singleForm) singleForm.style.display = 'none';
        if (batchForm) batchForm.style.display = 'block';
    } else {
        if (singleBtn) singleBtn.classList.add('active');
        if (batchBtn) batchBtn.classList.remove('active');
        if (singleForm) singleForm.style.display = 'block';
        if (batchForm) batchForm.style.display = 'none';
    }
}

function toggleSchedNow(isNow) {
    const dateInput = document.getElementById('schedInputDate');
    const timeInput = document.getElementById('schedInputTime');
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const localDate = `${year}-${month}-${day}`;
    
    const hours = String(now.getHours()).padStart(2, '0');
    const mins = String(now.getMinutes()).padStart(2, '0');
    const localTime = `${hours}:${mins}`;

    if (isNow) {
        if (dateInput) {
            dateInput.value = localDate;
            dateInput.disabled = true;
        }
        if (timeInput) {
            timeInput.value = localTime;
            timeInput.disabled = true;
        }
    } else {
        if (dateInput) {
            if (!dateInput.value) dateInput.value = localDate;
            dateInput.disabled = false;
        }
        if (timeInput) {
            if (!timeInput.value) timeInput.value = localTime;
            timeInput.disabled = false;
        }
    }
}

function addCustomVariableRow(key = '', val = '') {
    const list = document.getElementById('customVarList');
    if (!list) return;

    const rowId = 'cvar_' + Math.random().toString(36).substr(2, 9);
    const rowDiv = document.createElement('div');
    rowDiv.id = rowId;
    rowDiv.style.cssText = 'display: flex; gap: 10px; align-items: center;';

    rowDiv.innerHTML = `
        <input type="text" class="cvar-key" placeholder="Variable Key (e.g. appointment_date)" value="${escapeHtml(key)}" style="flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 13px;">
        <input type="text" class="cvar-val" placeholder="Value (e.g. Tomorrow 10am)" value="${escapeHtml(val)}" style="flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 13px;">
        <button type="button" onclick="document.getElementById('${rowId}').remove()" style="background: none; border: none; color: #ef4444; font-size: 16px; cursor: pointer; padding: 4px 8px;" title="Remove Variable">✕</button>
    `;

    list.appendChild(rowDiv);
}

function getCustomVariablesFromForm() {
    const vars = {};
    document.querySelectorAll('#customVarList > div').forEach(row => {
        const keyInput = row.querySelector('.cvar-key');
        const valInput = row.querySelector('.cvar-val');
        if (keyInput && valInput) {
            const k = keyInput.value.trim();
            const v = valInput.value.trim();
            if (k) vars[k] = v;
        }
    });
    return vars;
}

function handleBatchFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(evt) {
        const text = evt.target.result;
        parseCSVOrExcelText(text, file.name);
    };
    reader.readAsText(file);
}

function parseCSVOrExcelText(text, fileName) {
    const lines = text.split(/\r\n|\n/).map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length === 0) return;

    const headers = lines[0].split(',').map(h => h.replace(/^["']|["']$/g, '').trim());
    const contacts = [];

    for (let i = 1; i < lines.length; i++) {
        const rowVals = lines[i].split(',').map(v => v.replace(/^["']|["']$/g, '').trim());
        if (rowVals.length === 0 || !rowVals.some(v => v.length > 0)) continue;

        const rowObj = {};
        const customVars = {};

        headers.forEach((h, idx) => {
            const val = rowVals[idx] || '';
            const lowerH = h.toLowerCase();
            if (lowerH.includes('name')) rowObj.name = val;
            else if (lowerH.includes('phone') || lowerH.includes('mobile') || lowerH.includes('number')) rowObj.phone = val;
            else if (lowerH.includes('email')) rowObj.email = val;
            else if (lowerH.includes('company')) rowObj.company = val;
            else if (h) customVars[h] = val;
        });

        if (rowObj.phone || rowObj.name) {
            rowObj.custom_variables = customVars;
            contacts.push(rowObj);
        }
    }

    currentBatchParsedContacts = contacts;
    renderBatchPreview(headers, contacts, fileName);
}

function renderBatchPreview(headers, contacts, fileName) {
    const container = document.getElementById('batchPreviewContainer');
    const title = document.getElementById('batchPreviewTitle');
    const headTr = document.getElementById('batchPreviewHeader');
    const bodyTb = document.getElementById('batchPreviewBody');

    if (!container || !headTr || !bodyTb) return;

    title.innerText = `Parsed ${contacts.length} Contacts from ${fileName}`;
    headTr.innerHTML = headers.map(h => `<th style="padding: 10px 12px; font-weight: 600; color: #475569; border-bottom: 1px solid #cbd5e1;">${escapeHtml(h)}</th>`).join('');

    bodyTb.innerHTML = contacts.slice(0, 50).map(c => {
        return `<tr style="border-bottom: 1px solid #f1f5f9;">` +
            headers.map(h => {
                const lowerH = h.toLowerCase();
                let val = '';
                if (lowerH.includes('name')) val = c.name || '';
                else if (lowerH.includes('phone')) val = c.phone || '';
                else if (lowerH.includes('email')) val = c.email || '';
                else if (lowerH.includes('company')) val = c.company || '';
                else val = (c.custom_variables || {})[h] || '';
                return `<td style="padding: 8px 12px; color: #334155;">${escapeHtml(val)}</td>`;
            }).join('') +
            `</tr>`;
    }).join('');

    container.style.display = 'block';
}

function clearBatchFile() {
    currentBatchParsedContacts = [];
    const fileInput = document.getElementById('batchFileInput');
    const container = document.getElementById('batchPreviewContainer');
    if (fileInput) fileInput.value = '';
    if (container) container.style.display = 'none';
}

async function submitScheduledCalls() {
    const statusMsg = document.getElementById('schedStatusMsg');
    const submitBtn = document.getElementById('btnSubmitSched');
    const isNow = document.getElementById('schedNowCheckbox')?.checked;

    let scheduledAt = new Date().toISOString();
    if (!isNow) {
        const dateVal = document.getElementById('schedInputDate')?.value;
        const timeVal = document.getElementById('schedInputTime')?.value;
        if (!dateVal || !timeVal) {
            if (statusMsg) {
                statusMsg.style.display = 'inline';
                statusMsg.style.color = '#ef4444';
                statusMsg.innerText = 'Please select both Date and Time (or check Execute Immediately).';
            }
            return;
        }
        scheduledAt = new Date(`${dateVal}T${timeVal}`).toISOString();
    }

    let itemsToSchedule = [];
    const bId = currentBusiness ? currentBusiness.id : null;

    if (currentSchedMode === 'single') {
        const name = document.getElementById('singleSchedName')?.value.trim();
        const phone = document.getElementById('singleSchedPhone')?.value.trim();
        const email = document.getElementById('singleSchedEmail')?.value.trim();
        const company = document.getElementById('singleSchedCompany')?.value.trim();
        const customVars = getCustomVariablesFromForm();

        if (!phone) {
            if (statusMsg) {
                statusMsg.style.display = 'inline';
                statusMsg.style.color = '#ef4444';
                statusMsg.innerText = 'Phone Number is required.';
            }
            return;
        }

        const scId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : ('sc_' + Date.now());
        itemsToSchedule.push({
            id: scId,
            business_id: bId,
            caller_name: name || 'Scheduled Prospect',
            caller_phone: phone.startsWith('+') ? phone : '+' + phone,
            caller_email: email,
            company: company,
            custom_variables: customVars,
            scheduled_at: scheduledAt,
            status: isNow ? 'calling' : 'pending'
        });
    } else {
        if (currentBatchParsedContacts.length === 0) {
            if (statusMsg) {
                statusMsg.style.display = 'inline';
                statusMsg.style.color = '#ef4444';
                statusMsg.innerText = 'Please upload a valid CSV or Excel file with contact rows.';
            }
            return;
        }

        itemsToSchedule = currentBatchParsedContacts.map(c => ({
            id: (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : ('sc_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6)),
            business_id: bId,
            caller_name: c.name || 'Batch Lead',
            caller_phone: (c.phone || '').startsWith('+') ? c.phone : '+' + c.phone,
            caller_email: c.email || '',
            company: c.company || '',
            custom_variables: c.custom_variables || {},
            scheduled_at: scheduledAt,
            status: isNow ? 'calling' : 'pending'
        }));
    }

    if (submitBtn) submitBtn.disabled = true;
    if (statusMsg) {
        statusMsg.style.display = 'inline';
        statusMsg.style.color = '#0284c7';
        statusMsg.innerText = `Scheduling ${itemsToSchedule.length} call(s)...`;
    }

    try {
        let supaSuccess = false;
        // 1. Save directly to Supabase scheduled_calls table
        if (typeof supabaseClient !== 'undefined' && supabaseClient) {
            const { error } = await supabaseClient.from('scheduled_calls').insert(itemsToSchedule);
            if (!error) {
                supaSuccess = true;
            } else {
                console.warn('Supabase scheduled_calls insert warning:', error);
            }
        }

        // 2. Only post to backend API if Supabase insert failed or for instant call execution
        if (!supaSuccess || isNow) {
            try {
                await fetch(getBackendUrl('/api/schedule-call'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ calls: itemsToSchedule, execute_now: isNow })
                });
            } catch (e) {}
        }

        if (statusMsg) {
            statusMsg.style.color = '#10b981';
            statusMsg.innerText = `Successfully scheduled ${itemsToSchedule.length} call(s)!`;
        }

        // Reset inputs
        if (currentSchedMode === 'single') {
            document.getElementById('singleSchedName').value = '';
            document.getElementById('singleSchedPhone').value = '';
            document.getElementById('singleSchedEmail').value = '';
            document.getElementById('singleSchedCompany').value = '';
            document.getElementById('customVarList').innerHTML = '';
        } else {
            clearBatchFile();
        }

        setTimeout(() => {
            if (statusMsg) statusMsg.style.display = 'none';
            if (submitBtn) submitBtn.disabled = false;
        }, 3000);

        loadScheduledCallsQueue();

    } catch (err) {
        console.error('Schedule calls error:', err);
        if (statusMsg) {
            statusMsg.style.color = '#ef4444';
            statusMsg.innerText = 'Failed to schedule calls. Please try again.';
        }
        if (submitBtn) submitBtn.disabled = false;
    }
}

async function loadScheduledCallsQueue() {
    const tbody = document.getElementById('schedQueueTableBody');
    const emptyState = document.getElementById('schedEmptyState');
    if (!tbody) return;

    try {
        let items = [];

        if (typeof supabaseClient !== 'undefined' && supabaseClient) {
            const query = supabaseClient.from('scheduled_calls').select('*').order('scheduled_at', { ascending: true });
            if (currentBusiness && currentBusiness.id) {
                query.eq('business_id', currentBusiness.id);
            }
            const { data, error } = await query;
            if (!error && data) items = data;
        }

        if (items.length === 0) {
            try {
                const resp = await fetch(getBackendUrl('/api/scheduled-calls'));
                if (resp.ok) items = await resp.json();
            } catch (e) {}
        }

        if (!items || items.length === 0) {
            tbody.innerHTML = '';
            if (emptyState) emptyState.style.display = 'flex';
            return;
        }

        if (emptyState) emptyState.style.display = 'none';

        tbody.innerHTML = items.map(item => {
            const dt = new Date(item.scheduled_at);
            const dtStr = dt.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            
            const varsObj = item.custom_variables || {};
            const varsBadges = Object.keys(varsObj).map(k => `<span style="background: #f1f5f9; color: #475569; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-right: 4px;">${escapeHtml(k)}: ${escapeHtml(varsObj[k])}</span>`).join('') || '<span style="color: #94a3b8; font-size: 12px;">--</span>';

            let statusBadge = '<span class="dash-tag-initiated">Pending</span>';
            if (item.status === 'completed') statusBadge = '<span class="dash-tag-completed">Completed</span>';
            else if (item.status === 'calling') statusBadge = '<span class="dash-tag-interested">Calling Now</span>';
            else if (item.status === 'cancelled') statusBadge = '<span style="background: #fee2e2; color: #ef4444; padding: 2px 8px; border-radius: 100px; font-size: 11px; font-weight: 700;">Cancelled</span>';
            else if (item.status === 'failed') statusBadge = '<span style="background: #fee2e2; color: #ef4444; padding: 2px 8px; border-radius: 100px; font-size: 11px; font-weight: 700;">Failed</span>';

            return `
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 12px 16px; font-weight: 600; color: #1e293b;">${escapeHtml(dtStr)}</td>
                    <td style="padding: 12px 16px; font-weight: 700; color: #0f172a;">${escapeHtml(item.caller_name || 'Prospect')}</td>
                    <td style="padding: 12px 16px; font-family: 'JetBrains Mono', monospace; color: #334155;">${escapeHtml(item.caller_phone)}</td>
                    <td style="padding: 12px 16px;">${varsBadges}</td>
                    <td style="padding: 12px 16px;">${statusBadge}</td>
                    <td style="padding: 12px 16px; text-align: right;">
                        ${item.status === 'pending' ? `
                            <button onclick="triggerScheduledNow('${item.id}')" style="background: #10b981; color: #fff; border: none; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 700; cursor: pointer; margin-right: 6px;">Call Now</button>
                            <button onclick="cancelScheduledCall('${item.id}')" style="background: none; border: 1px solid #cbd5e1; color: #ef4444; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 600; cursor: pointer;">Cancel</button>
                        ` : ''}
                    </td>
                </tr>
            `;
        }).join('');

    } catch (err) {
        console.error('Load scheduled calls error:', err);
    }
}

async function triggerScheduledNow(id) {
    try {
        if (typeof supabaseClient !== 'undefined' && supabaseClient) {
            await supabaseClient.from('scheduled_calls').update({ status: 'calling', scheduled_at: new Date().toISOString() }).eq('id', id);
        }
        await fetch(getBackendUrl('/api/trigger-scheduled-now'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        loadScheduledCallsQueue();
    } catch (e) {}
}

async function cancelScheduledCall(id) {
    try {
        if (typeof supabaseClient !== 'undefined' && supabaseClient) {
            await supabaseClient.from('scheduled_calls').update({ status: 'cancelled' }).eq('id', id);
        }
        await fetch(getBackendUrl('/api/scheduled-calls'), {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        loadScheduledCallsQueue();
    } catch (e) {}
}

function toggleRecordingPlayer(recordingUrl) {
    const playerContainer = document.getElementById('modalRecordingPlayer');
    const videoPlayer = document.getElementById('modalVideoPlayer');
    
    if (!playerContainer || !videoPlayer) return;
    
    if (playerContainer.style.display === 'none' || playerContainer.style.display === '') {
        // Show player
        videoPlayer.src = recordingUrl;
        playerContainer.style.display = 'block';
        
        // Scroll player into view
        playerContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        // Hide player and stop playback
        videoPlayer.pause();
        videoPlayer.src = '';
        playerContainer.style.display = 'none';
    }
}


