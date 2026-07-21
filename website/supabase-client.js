/* ==========================================
   SUPABASE CLIENT CONFIGURATION
   ========================================== */

const SUPABASE_URL = 'https://zuxjdbrgfwpphswgxkiw.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ0ODI1NTQsImV4cCI6MjEwMDA1ODU1NH0.mxWB8ACxJcq01XuuXJRclA4M7_bL7MYaq5fC_3ZzZXg';

// Initialize Supabase Client
const supabaseClient = window.supabase ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

// Helper to get active session
async function getSupabaseSession() {
    if (!supabaseClient) return null;
    const { data: { session } } = await supabaseClient.auth.getSession();
    return session;
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
    window.location.href = 'login.html';
}
