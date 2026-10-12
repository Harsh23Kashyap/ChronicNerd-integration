-- Optional context, separate from conditions. Up to 1,000 characters enforced by API.
ALTER TABLE user_profiles ADD COLUMN additional_notes TEXT;
