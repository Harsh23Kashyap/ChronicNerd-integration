"""Local browser-E2E server: real app/DB/SSE with only external science APIs stubbed."""
import json
import sys

import uvicorn

sys.path.insert(0, "dietnerd-backend")
import main


def summary(previous, question, answer):
    return ((previous + "\n") if previous else "") + question + ": " + answer


def fake_process(user_query, request_id, email, conversation_id):
    memory = main.get_session_memory(email, conversation_id)
    standalone = user_query
    if memory and user_query.lower() == "what about sleep?":
        standalone = "What are the effects of magnesium on sleep?"
    answer = "Generated browser-test answer for: " + standalone
    entry = {
        "request_id": request_id,
        "raw_question": user_query,
        "standalone_question": standalone,
        "answer": answer,
    }
    main.append_session_memory(email, conversation_id, entry)
    main.set_conversation_summary(
        email,
        conversation_id,
        summary(main.get_conversation_summary(email, conversation_id), standalone, answer),
    )
    main.loop.run_until_complete(main.send_update(request_id, "Generated PubMed queries..."))
    main.loop.run_until_complete(main.send_update(request_id, {
        "end_output": answer,
        "relevant_articles": [],
        "citations_obj": {},
        "citations": [],
        "session_memory_entry": entry,
    }))


main.process_user_query = fake_process
main.determine_question_validity = lambda question: "True"
main.update_conversation_summary = summary


def capture_reset(to_email, reset_url):
    with open("tests/.last-reset-url", "w") as handle:
        handle.write(reset_url)
    return True


main.auth.send_reset_email = capture_reset

CACHED_QUESTION = "browser cached question"
CACHED_PAYLOAD = {
    "end_output": "Cached browser-test answer",
    "relevant_articles": [],
    "citations_obj": {},
    "citations": [],
}


def seed_cached_answer():
    """Give the E2E flow one known cached answer; the test DB may have been reset."""
    main.create_tables()
    db = main._get_db_connection()
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM question_answer WHERE question = %s", (CACHED_QUESTION,))
        cursor.execute(
            "INSERT INTO question_answer (question, answer) VALUES (%s, %s)",
            (CACHED_QUESTION, json.dumps(CACHED_PAYLOAD)),
        )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_cached_answer()
    uvicorn.run(main.app, host="127.0.0.1", port=8000)
