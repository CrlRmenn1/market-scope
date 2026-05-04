-- Recommended indexes for MarketScope backend
-- Run this script in your PostgreSQL database (psql, DBeaver, etc.)

-- USERS TABLE
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);

-- ANALYSIS_HISTORY TABLE
CREATE INDEX IF NOT EXISTS idx_analysis_history_user_id ON analysis_history(user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_history_business_type ON analysis_history(business_type);

-- TREND_SCAN_SNAPSHOTS TABLE
CREATE UNIQUE INDEX IF NOT EXISTS idx_trend_scan_snapshots_radius ON trend_scan_snapshots(radius);

-- CUSTOM_MSME TABLE
CREATE INDEX IF NOT EXISTS idx_custom_msme_business_type ON custom_msme(business_type);

-- USER_SPACE_SUBMISSIONS TABLE
CREATE INDEX IF NOT EXISTS idx_user_space_submissions_user_id ON user_space_submissions(submitted_by_user_id);

-- ADMIN_SPACE_SUBMISSIONS TABLE
CREATE INDEX IF NOT EXISTS idx_admin_space_submissions_user_id ON admin_space_submissions(id);
