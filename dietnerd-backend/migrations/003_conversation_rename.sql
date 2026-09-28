-- Lets users rename conversations without the auto-title job overwriting them.
ALTER TABLE conversations ADD COLUMN title_locked TINYINT(1) NOT NULL DEFAULT 0;
