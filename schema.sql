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
CREATE POLICY "Users can view own business" 
  ON public.businesses FOR SELECT 
  USING (auth.uid() = id);

CREATE POLICY "Users can insert own business" 
  ON public.businesses FOR INSERT 
  WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update own business" 
  ON public.businesses FOR UPDATE 
  USING (auth.uid() = id);

-- 5. RLS Policies for Call Logs Table
CREATE POLICY "Users can view own call logs" 
  ON public.call_logs FOR SELECT 
  USING (business_id = auth.uid());

CREATE POLICY "Users can insert own call logs" 
  ON public.call_logs FOR INSERT 
  WITH CHECK (business_id = auth.uid());

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

