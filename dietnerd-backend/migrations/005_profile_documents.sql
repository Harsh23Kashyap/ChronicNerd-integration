CREATE TABLE IF NOT EXISTS user_profile_documents (
    email VARCHAR(255) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    content LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (email, filename),
    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
);
