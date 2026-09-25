"""Backfill only raw, owned first-turn titles; never touch generated titles."""
import importlib.util
import pathlib
from unittest.mock import MagicMock

PATH = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'backfill-conversation-titles.py'
spec = importlib.util.spec_from_file_location('backfill_titles', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_candidates_are_owner_scoped_and_raw_title_only():
    rows = [
        {'conversation_id':'a', 'title':'What diet?', 'raw_question':'What diet?'},
        {'conversation_id':'b', 'title':'Kidney Diet Evidence', 'raw_question':'What diet?'},
        {'conversation_id':'c', 'title':None, 'raw_question':'Another question'},
    ]
    db=MagicMock(); cursor=MagicMock(); db.cursor.return_value=cursor
    cursor.fetchall.return_value=rows
    main=MagicMock(); main._get_db_connection.return_value=db
    found=module.candidates(main,'owner@example.invalid')
    assert [row['conversation_id'] for row in found]==['a','c']
    sql, params=cursor.execute.call_args.args
    assert 'WHERE c.email = %s' in sql
    assert params==('owner@example.invalid',)
    db.close.assert_called_once()
