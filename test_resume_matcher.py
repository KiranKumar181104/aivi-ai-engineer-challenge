import json
import unittest
from urllib.error import HTTPError

from resume_matcher import MatchError, match_resume, parse_result

VALID = {"match_score": 65, "top_strengths": ["Python project evidenced."],
         "missing_skills": ["SQL not evidenced."], "summary": "Python is evidenced.\nSQL is not evidenced."}


def envelope(data=VALID, reason="STOP"):
    return {"candidates": [{"finishReason": reason, "content": {"parts": [{"text": json.dumps(data)}]}}]}


class MatcherTests(unittest.TestCase):
    def run_match(self, transport, **kwargs):
        return match_resume("Python project", "Python and SQL", api_key="test-key",
                            model="test-model", transport=transport, sleep=lambda _: None,
                            jitter=lambda a, b: 0, **kwargs)

    def test_valid(self):
        self.assertEqual(self.run_match(lambda *a: envelope()).match_score, 65)

    def test_fence_and_bom(self):
        self.assertEqual(parse_result('\ufeff```json\n'+json.dumps(VALID)+'\n```').match_score, 65)

    def test_reject_invalid_types_and_ranges(self):
        for score in [True, "65", -1, 101, 65.0]:
            with self.subTest(score=score), self.assertRaises(MatchError):
                parse_result(json.dumps({**VALID, "match_score": score}))

    def test_reject_extra_missing_and_bad_summary(self):
        for data in [{**VALID, "extra": 1}, {k:v for k,v in VALID.items() if k!='summary'},
                     {**VALID, "summary": "one line"}, {**VALID, "top_strengths": [""]}]:
            with self.assertRaises(MatchError):
                parse_result(json.dumps(data))

    def test_duplicate_and_prose(self):
        for text in ['{"match_score":1,"match_score":100}', 'Here is JSON: '+json.dumps(VALID),
                     json.dumps(VALID)+' trailing', '{"match_score":NaN}']:
            with self.assertRaises(MatchError):
                parse_result(text)

    def test_retry_429_then_success(self):
        calls=[]
        def transport(*args):
            calls.append(1)
            if len(calls)==1:
                raise HTTPError('test',429,'limited',{'Retry-After':'0'},None)
            return envelope()
        self.assertEqual(self.run_match(transport).match_score,65)
        self.assertEqual(len(calls),2)

    def test_permanent_error_no_retry(self):
        calls=[]
        def transport(*a):
            calls.append(1)
            raise HTTPError('test',403,'denied',{},None)
        with self.assertRaises(MatchError) as error:
            self.run_match(transport)
        self.assertEqual(error.exception.code,'api_error')
        self.assertEqual(len(calls),1)

    def test_timeout_exhaustion_no_score(self):
        calls=[]
        def transport(*a):
            calls.append(1)
            raise TimeoutError()
        with self.assertRaises(MatchError) as error:
            self.run_match(transport)
        self.assertEqual(error.exception.code,'timeout')
        self.assertEqual(len(calls),3)

    def test_invalid_output_one_regeneration(self):
        calls=[]
        def transport(*a):
            calls.append(1)
            return envelope(reason='MAX_TOKENS')
        with self.assertRaises(MatchError):
            self.run_match(transport)
        self.assertEqual(len(calls),2)

    def test_deadline_stops_retry_after(self):
        calls=[]
        def transport(*a):
            calls.append(1)
            raise HTTPError('test',429,'limited',{'Retry-After':'100'},None)
        with self.assertRaises(MatchError):
            self.run_match(transport,deadline=5)
        self.assertEqual(len(calls),1)

    def test_empty_input_does_not_transmit(self):
        with self.assertRaises(MatchError):
            match_resume('', 'Python', api_key='test',model='test',
                         transport=lambda *a:self.fail('must not transmit'))

    def test_payload_isolates_untrusted_text(self):
        def transport(payload,*a):
            data=json.loads(payload['contents'][0]['parts'][0]['text'])
            self.assertEqual(data['resume_text'],'Python project')
            self.assertIn('systemInstruction',payload)
            self.assertEqual(payload['generationConfig']['responseMimeType'],'application/json')
            return envelope()
        self.run_match(transport)


if __name__ == '__main__':
    unittest.main()
