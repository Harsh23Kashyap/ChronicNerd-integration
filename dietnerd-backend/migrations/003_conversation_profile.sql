-- Saved conversation-specific opt-out. Existing chats keep prior behavior.
ALTER TABLE conversations ADD COLUMN use_profile TINYINT(1) NOT NULL DEFAULT 1;
