"""Do not turn an unsourced generic g/kg model reply into a personal target."""
from pathlib import Path
import sys
from unittest.mock import patch
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main


def test_no_personal_arithmetic_from_unsourced_model_range():
    answer = ("What we know\nA general range of 1.2 to 2.0 grams of protein per kilogram of body weight."
              "\n\nWhat we don't know\nNot a personal target.\n\nWhat to ask a dietitian\nWhat factors matter?")
    with patch.object(main, 'get_session_memory', return_value=[]), \
         patch.object(main, 'check_attachment_exists', return_value=False), \
         patch.object(main, 'get_diet_profile_prompt', return_value='weight 72 kg'), \
         patch.object(main, 'get_profile_documents', return_value=[]), \
         patch.object(main, 'query_generation', return_value=('q','q',['q'])), \
         patch.object(main, 'collect_articles', return_value=[]), \
         patch.object(main, 'concurrent_relevance_classification', return_value=([],[])), \
         patch.object(main, 'connect_to_reliability_analysis_db', return_value=pd.DataFrame([{'x':1}])), \
         patch.object(main, 'article_matching', return_value=([],[])), \
         patch.object(main, 'concurrent_article_processing', return_value=[]), \
         patch.object(main, 'generate_final_response', side_effect=[answer, answer]) as synth, \
         patch.object(main, 'write_articles_to_db'), patch.object(main, 'write_output_to_db'), \
         patch.object(main, 'append_session_memory'), patch.object(main, 'get_conversation_summary', return_value=''), \
         patch.object(main, 'update_conversation_summary', return_value=''), \
         patch.object(main, 'set_conversation_summary'), patch.object(main, 'send_update'):
        result = main.process_user_query('What daily protein range for my body weight? Show calculation.',
                                         'req','owner@example.invalid','conv')
    assert synth.call_count == 2
    assert '86.4 g/day' not in result['end_output']
    assert '144 g/day' not in result['end_output']
