-- Adds the opt-in diet profile used to personalize answers.
CREATE TABLE IF NOT EXISTS user_profiles (
    email VARCHAR(255) PRIMARY KEY,
    age_range VARCHAR(40) NOT NULL DEFAULT '',
    goals VARCHAR(300) NOT NULL DEFAULT '',
    conditions VARCHAR(300) NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
);
