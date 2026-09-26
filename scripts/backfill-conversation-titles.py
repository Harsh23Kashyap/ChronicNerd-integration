#!/usr/bin/env python3
"""One-time, dry-run-first title repair for conversations still named as raw questions.

Run from repo root in the API environment. Requires BACKFILL_EMAIL to target one
verified account; no changes unless --apply. Uses the same model/title function as
new conversations, and only examines conversations with at least one saved turn.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dietnerd-backend'))


def candidates(main, email):
    db = main._get_db_connection()
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute('''SELECT c.conversation_id, c.title, m.raw_question
            FROM conversations c
            JOIN user_session_memory m ON m.conversation_id = c.conversation_id
              AND m.email = c.email AND m.query_number = 1
            WHERE c.email = %s ORDER BY c.created_at''', (email,))
        return [row for row in cursor.fetchall() if
                not row['title'] or row['title'].strip() == (row['raw_question'] or '')[:120].strip()]
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Actually update selected titles')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    email = os.getenv('BACKFILL_EMAIL', '').strip().lower()
    if not email or '@' not in email:
        parser.error('Set BACKFILL_EMAIL to the verified account; never guess the owner')
    import main as app
    rows = candidates(app, email)
    print(f'{len(rows)} raw-title conversations for {email}; mode={"apply" if args.apply else "dry-run"}')
    for row in rows:
        print(f'{row["conversation_id"]}: {row["title"]!r}')
        if args.apply:
            app.update_conversation_title(email, row['conversation_id'])
    if args.apply:
        print('Backfill finished. Confirm updated titles from GET /conversations as that user.')
    else:
        print('No changes. Re-run with --apply after reviewing owner and candidate IDs.')


if __name__ == '__main__':
    main()
