"""The last eight turns inform conversational intent, not citation evidence."""
import importlib
import sys
import unittest
from unittest.mock import MagicMock


class RecentDialogueContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, 'dietnerd-backend')
        cls.h = importlib.import_module('helper_functions')

    def test_only_eight_previous_turns_reach_final_prompt(self):
        h = self.h
        old = h.client
        try:
            h.client = MagicMock()
            h.client.chat.completions.create.return_value.choices = [
                MagicMock(message=MagicMock(content='What we know\nTest.\n\nWhat we don\'t know\nUnknown.\n\nWhat to ask a dietitian\nAsk.'))
            ]
            turns = [{'raw_question': f'previous-question-{i}', 'answer': f'previous-answer-{i}'} for i in range(10)]
            h.generate_final_response([], 'current-question', recent_history=turns)
            messages = h.client.chat.completions.create.call_args.kwargs['messages']
            prompt = messages[1]['content']
            self.assertNotIn('previous-question-0', prompt)
            self.assertNotIn('previous-question-1', prompt)
            self.assertIn('previous-question-2', prompt)
            self.assertIn('previous-answer-9', prompt)
            self.assertIn('not as evidence', prompt)
            self.assertIn('prior answers are not evidence', messages[0]['content'])
        finally:
            h.client = old


if __name__ == '__main__':
    unittest.main()
