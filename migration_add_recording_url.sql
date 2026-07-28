-- ================================================================
-- MIGRATION: Add recording_url column to call_logs table
-- Execute this in your Supabase Dashboard SQL Editor
-- (https://supabase.com/dashboard/project/YOUR_PROJECT/sql)
-- ================================================================

-- Add recording_url column to store VideoSDK recording file URLs
ALTER TABLE public.call_logs ADD COLUMN IF NOT EXISTS recording_url TEXT;

-- Optional: Add index for faster queries on recording_url
CREATE INDEX IF NOT EXISTS idx_call_logs_recording_url ON public.call_logs(recording_url) WHERE recording_url IS NOT NULL;

-- Verify the column was added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'call_logs' AND column_name = 'recording_url';
