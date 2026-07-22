/* ==========================================
   SUPABASE CLIENT & AUTH STATE ENGINE
   ========================================== */

const SUPABASE_URL = 'https://zuxjdbrgfwpphswgxkiw.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ0ODI1NTQsImV4cCI6MjEwMDA1ODU1NH0.mxWB8ACxJcq01XuuXJRclA4M7_bL7MYaq5fC_3ZzZXg';

// Initialize Supabase Client
const supabaseClient = window.supabase ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

// Helper to get active session
async function getSupabaseSession() {
    if (!supabaseClient) return null;
    try {
        const { data: { session } } = await supabaseClient.auth.getSession();
        return session;
    } catch (e) {
        console.warn('Supabase getSession error:', e);
        return null;
    }
}

// Helper to get current user
async function getCurrentUser() {
    const session = await getSupabaseSession();
    return session ? session.user : null;
}

// Helper to sign out
async function logoutBusiness() {
    if (supabaseClient) {
        await supabaseClient.auth.signOut();
    }
    window.location.href = 'index.html';
}

// Dynamically update UI based on registration/login state
async function updateAuthStateUI() {
    try {
        const session = await getSupabaseSession();
        const isLoggedIn = !!(session && session.user);

        const navActions = document.querySelector('.nav-actions');
        const heroGetStartedBtn = document.getElementById('heroGetStartedBtn');

        if (isLoggedIn) {
            // --- LOGGED IN / REGISTERED USER UI ---

            // 1. Update Navbar Buttons
            if (navActions) {
                const isDashboardPage = window.location.pathname.includes('dashboard.html') || document.getElementById('sidebarToggleBtn');
                if (isDashboardPage) {
                    navActions.innerHTML = `
                        <button class="dash-menu-toggle-icon" id="sidebarToggleBtn" onclick="toggleSidebarDrawer()" aria-label="Toggle Business Menu" title="Business Menu & Profile">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                        </button>
                    `;
                } else {
                    navActions.innerHTML = `
                        <button class="btn btn-primary" onclick="window.location.href='dashboard.html'">My Dashboard</button>
                        <button class="btn btn-dark" onclick="logoutBusiness()">Log out</button>
                    `;
                }
            }

            // 2. Update Single Hero Button for Logged-In User
            if (heroGetStartedBtn) {
                heroGetStartedBtn.href = 'dashboard.html';
                heroGetStartedBtn.innerHTML = `
                    <span>Go to Dashboard</span>
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M4 10h12m-4-4l4 4-4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                `;
            }

        } else {
            // --- UNREGISTERED / GUEST USER UI ---

            // 1. Update Navbar Buttons
            if (navActions) {
                navActions.innerHTML = `
                    <button class="btn btn-dark" onclick="window.location.href='login.html'">Log in</button>
                    <button class="btn btn-primary" onclick="window.location.href='register.html'">Register Business</button>
                `;
            }

            // 2. Ensure Hero Button points to registration
            if (heroGetStartedBtn) {
                heroGetStartedBtn.href = 'register.html';
                heroGetStartedBtn.innerHTML = `
                    <span>Get Started</span>
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M4 10h12m-4-4l4 4-4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                `;
            }
        }
    } catch (err) {
        console.warn('updateAuthStateUI error:', err);
        // If anything fails, the button still works as a plain <a href="register.html"> link
    }
}

// Auto-run on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    try {
        updateAuthStateUI();
    } catch (err) {
        console.warn('Auth UI init error:', err);
    }
});
