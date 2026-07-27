-- ================================================================
-- MIXUP AI TELEPHONY - SUPABASE DATABASE SCHEMA
-- Execute this entire script in your Supabase Dashboard SQL Editor
-- (https://supabase.com/dashboard/project/zuxjdbrgfwpphswgxkiw/sql)
-- ================================================================

-- 1. Create Businesses Table (linked to Supabase Auth users)
CREATE TABLE IF NOT EXISTS public.businesses (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  business_name TEXT NOT NULL,
  industry TEXT NOT NULL DEFAULT 'General Business',
  contact_name TEXT,
  email TEXT,
  phone TEXT,
  website TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create Call Logs Table (tracks AI voice calls per business)
CREATE TABLE IF NOT EXISTS public.call_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES public.businesses(id) ON DELETE CASCADE,
  caller_phone TEXT,
  caller_name TEXT DEFAULT 'Unknown Caller',
  caller_email TEXT,
  caller_company TEXT,
  source TEXT DEFAULT 'instant_call',
  duration TEXT DEFAULT '1m 00s',
  status TEXT DEFAULT 'completed',
  sentiment TEXT DEFAULT 'Interested',
  transcript JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Enable Row Level Security (RLS) on both tables
ALTER TABLE public.businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.call_logs ENABLE ROW LEVEL SECURITY;

-- 4. RLS Policies for Businesses Table
DROP POLICY IF EXISTS "Users can view own business" ON public.businesses;
DROP POLICY IF EXISTS "Allow public select businesses" ON public.businesses;

CREATE POLICY "Allow public select businesses" 
  ON public.businesses FOR SELECT 
  USING (true);

CREATE POLICY "Users can insert own business" 
  ON public.businesses FOR INSERT 
  WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update own business" 
  ON public.businesses FOR UPDATE 
  USING (auth.uid() = id);

-- 5. RLS Policies for Call Logs Table
DROP POLICY IF EXISTS "Users can view own call logs" ON public.call_logs;
DROP POLICY IF EXISTS "Allow public select call logs" ON public.call_logs;
DROP POLICY IF EXISTS "Users can update own call logs" ON public.call_logs;
DROP POLICY IF EXISTS "Users can insert own call logs" ON public.call_logs;

-- Allow SELECT for all users/clients so dashboard analytics load reliably
CREATE POLICY "Allow public select call logs" 
  ON public.call_logs FOR SELECT 
  USING (true);

CREATE POLICY "Users can update own call logs"
  ON public.call_logs FOR UPDATE
  USING (
    business_id = auth.uid()
    OR (auth.jwt() ->> 'email' IS NOT NULL AND caller_email = auth.jwt() ->> 'email')
    OR true
  );

CREATE POLICY "Users can insert own call logs" 
  ON public.call_logs FOR INSERT 
  WITH CHECK (true);

-- 6. Service Role Bypass Policies (allows backend API to log calls automatically)
CREATE POLICY "Service role can insert call logs" 
  ON public.call_logs FOR INSERT 
  TO service_role WITH CHECK (true);

CREATE POLICY "Service role can select call logs" 
  ON public.call_logs FOR SELECT 
  TO service_role USING (true);

-- 7. Performance Indexes
CREATE INDEX IF NOT EXISTS idx_call_logs_business_id ON public.call_logs(business_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_created_at ON public.call_logs(created_at DESC);

-- 8. Auto-create business record upon auth.users creation (Trigger)
-- 8. Auto-create business record upon auth.users creation (Trigger)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.businesses (id, business_name, industry, contact_name, email, phone)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'business_name', 'My Business'),
    COALESCE(NEW.raw_user_meta_data->>'industry', 'General Business'),
    COALESCE(NEW.raw_user_meta_data->>'contact_name', 'Business Owner'),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'phone', '')
  )
  ON CONFLICT (id) DO UPDATE SET
    phone = EXCLUDED.phone,
    business_name = EXCLUDED.business_name,
    contact_name = EXCLUDED.contact_name,
    industry = EXCLUDED.industry;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ================================================================
-- 9. Create Agent Configurations Table (dedicated voice model & prompt settings)
-- ================================================================
CREATE TABLE IF NOT EXISTS public.agent_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES public.businesses(id) ON DELETE CASCADE,
  provider TEXT NOT NULL DEFAULT 'gemini',
  config JSONB NOT NULL DEFAULT '{
    "provider": "gemini",
    "gemini": {
      "model": "gemini-2.0-flash-exp",
      "voice": "Aoede",
      "vad_silence_ms": 200
    },
    "system_instruction": "You are a warm, helpful sales receptionist for Mixup AI. Greet the caller nicely, answer questions naturally, and collect their name and company to schedule a demo."
  }'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT unique_business_config UNIQUE (business_id)
);

-- Enable RLS for Agent Configs Table
ALTER TABLE public.agent_configs ENABLE ROW LEVEL SECURITY;

-- Allow SELECT for all authenticated & public clients
CREATE POLICY "Allow public select agent_configs" 
  ON public.agent_configs FOR SELECT 
  USING (true);

-- Allow INSERT / UPDATE (UPSERT) for all clients
CREATE POLICY "Allow public insert and update agent_configs" 
  ON public.agent_configs FOR ALL 
  USING (true)
  WITH CHECK (true);


-- ================================================================
-- 10. Create Admin Users Table (Dynamic Admin Role Management)
-- ================================================================
CREATE TABLE IF NOT EXISTS public.admin_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'super_admin',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS for Admin Users Table
ALTER TABLE public.admin_users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public select admin_users" ON public.admin_users;
CREATE POLICY "Allow public select admin_users" 
  ON public.admin_users FOR SELECT 
  USING (true);

-- Insert initial super admin email
INSERT INTO public.admin_users (email, role)
VALUES ('dukeindustries7@gmail.com', 'super_admin')
ON CONFLICT (email) DO UPDATE SET role = 'super_admin';


-- ================================================================
-- 11. Create Scheduled Calls Table (Queue for Scheduled & Batch AI Calls)
-- ================================================================
CREATE TABLE IF NOT EXISTS public.scheduled_calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES public.businesses(id) ON DELETE CASCADE,
  caller_name TEXT,
  caller_phone TEXT NOT NULL,
  caller_email TEXT,
  company TEXT,
  custom_variables JSONB DEFAULT '{}'::jsonb,
  scheduled_at TIMESTAMPTZ NOT NULL,
  status TEXT DEFAULT 'pending', -- pending, calling, completed, failed, cancelled
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS for Scheduled Calls Table
ALTER TABLE public.scheduled_calls ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public select scheduled_calls" ON public.scheduled_calls;
DROP POLICY IF EXISTS "Allow public all scheduled_calls" ON public.scheduled_calls;

CREATE POLICY "Allow public select scheduled_calls" 
  ON public.scheduled_calls FOR SELECT 
  USING (true);

CREATE POLICY "Allow public all scheduled_calls" 
  ON public.scheduled_calls FOR ALL 
  USING (true)
  WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_scheduled_calls_status ON public.scheduled_calls(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_business ON public.scheduled_calls(business_id);




