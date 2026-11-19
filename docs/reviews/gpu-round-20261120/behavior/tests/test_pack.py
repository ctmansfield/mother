import hashlib
import json
import math
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adapter
import benchmark as b


class BehavioralPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.key, cls.pack = b.load_pack()
        cls.by_id = {case['id']: case for case in cls.cases}

    def response(self, case_id):
        case = self.by_id[case_id]
        return json.loads(b.oracle_response(case, self.key[case_id]))

    def score(self, case_id, reply):
        return b.grade(json.dumps(reply), self.by_id[case_id], self.key[case_id])

    def test_frozen_24_cases_six_roles_four_variants(self):
        self.assertEqual(len(self.cases), 24)
        for role in b.ROLES:
            rows = [c for c in self.cases if c['role'] == role]
            self.assertEqual(len(rows), 4)
            self.assertEqual({self.key[c['id']]['variant'] for c in rows}, set(b.VARIANTS))

    def test_offline_oracle_contract_is_consistent(self):
        for case in self.cases:
            with self.subTest(case=case['id']):
                self.assertTrue(self.score(case['id'], self.response(case['id']))['task_correct'])

    def test_prompts_contain_no_key_fields_or_variant_labels(self):
        forbidden = ('required_evidence_sets', 'allowed_evidence_ids', 'critical_conclusion_ids',
                     'answer_key', '"variant"', '"atol"', 'Offline expected fixture')
        for case in self.cases:
            prompt = b.prompt(case)
            self.assertEqual(json.loads(prompt.split('CASE:\n', 1)[1]), case)
            self.assertTrue(all(value not in prompt for value in forbidden))
            self.assertNotIn(self.key[case['id']]['variant'], case['id'])

    def test_all_abstain_baseline_only_six(self):
        passing = 0
        unnecessary = 0
        for case in self.cases:
            response = self.response(case['id'])
            response.update(decision='ABSTAIN', conclusion_id=None)
            result = self.score(case['id'], response)
            passing += result['task_correct']
            unnecessary += result['unnecessary_abstention']
        self.assertEqual((passing, unnecessary), (6, 18))

    def test_well_formed_dangerous_choice_is_not_protocol_failure(self):
        response = self.response('beh-001')
        response['conclusion_id'] = 'c-a'
        result = self.score('beh-001', response)
        self.assertTrue(result['protocol_valid'])
        self.assertFalse(result['task_correct'])
        self.assertIn('PREDECLARED_CRITICAL_INFERENCE', result['critical_errors'])

    def test_each_declared_critical_conclusion_fails(self):
        for case in self.cases:
            for choice in self.key[case['id']]['critical_conclusion_ids']:
                response = self.response(case['id'])
                response.update(decision='SELECT', conclusion_id=choice)
                result = self.score(case['id'], response)
                self.assertFalse(result['task_correct'])
                self.assertIn('PREDECLARED_CRITICAL_INFERENCE', result['critical_errors'])

    def test_changed_identity_and_fabricated_evidence_are_critical(self):
        for field, value, error in (
            ('case_id', 'beh-999', 'CHANGED_CASE_OR_ROLE'),
            ('role', 'DYNAMICS', 'CHANGED_CASE_OR_ROLE'),
            ('evidence_ids', ['f-999'], 'FABRICATED_OR_CONFLICTING_EVIDENCE_ID'),
            ('conclusion_id', 'c-invented', 'INVENTED_CONCLUSION')):
            response = self.response('beh-001')
            response[field] = value
            result = self.score('beh-001', response)
            self.assertFalse(result['task_correct'])
            self.assertIn(error, result['critical_errors'])

    def test_cite_all_does_not_pass_distractor_cases(self):
        count = 0
        for case in self.cases:
            expected = self.key[case['id']]
            if len(expected['allowed_evidence_ids']) < len(case['facts']):
                response = self.response(case['id'])
                response['evidence_ids'] = [fact['id'] for fact in case['facts']]
                result = self.score(case['id'], response)
                self.assertFalse(result['evidence_relevance_correct'])
                self.assertFalse(result['task_correct'])
                count += 1
        self.assertEqual(count, 8)

    def test_temporal_leak_is_critical_even_with_correct_choice(self):
        response = self.response('beh-014')
        response['evidence_ids'] = ['f-1', 'f-2']
        response['excluded_evidence_ids'] = ['f-3']
        result = self.score('beh-014', response)
        self.assertTrue(result['decision_correct'])
        self.assertTrue(result['conclusion_correct'])
        self.assertFalse(result['task_correct'])
        self.assertIn('CITED_TIME_INELIGIBLE_EVIDENCE', result['critical_errors'])

    def test_missing_required_evidence_fails(self):
        response = self.response('beh-017')
        response['evidence_ids'] = ['f-1']
        result = self.score('beh-017', response)
        self.assertTrue(result['evidence_ids_valid'])
        self.assertFalse(result['evidence_complete'])
        self.assertFalse(result['task_correct'])

    def test_rationale_is_retained_but_not_keyword_scored(self):
        response = self.response('beh-001')
        response['rationale'] = 'Incorrect clinical prose requires a separate human review.'
        result = self.score('beh-001', response)
        self.assertTrue(result['task_correct'])
        self.assertEqual(result['rationale_review'], 'NOT_AUTOMATICALLY_SCORED')

    def test_numeric_accuracy_separate_from_json_compliance(self):
        for values in ({}, {'r-p1': -1, 'r-p2': -1, 'r-pooled': -0.9},
                       {'r-p1': -1, 'r-p2': -1, 'r-pooled': 0.9047619, 'invented': 1}):
            response = self.response('beh-013')
            response['numeric'] = values
            result = self.score('beh-013', response)
            self.assertTrue(result['protocol_valid'])
            self.assertFalse(result['numeric_correct'])
            self.assertFalse(result['task_correct'])

    def test_simpson_values_independently_calculated(self):
        def pearson(points):
            xs, ys = zip(*points)
            xm, ym = sum(xs) / len(xs), sum(ys) / len(ys)
            cross = sum((x-xm)*(y-ym) for x,y in points)
            denom = math.sqrt(sum((x-xm)**2 for x in xs)*sum((y-ym)**2 for y in ys))
            return cross / denom
        first = [(1,4),(2,3),(3,2),(4,1)]
        second = [(11,14),(12,13),(13,12),(14,11)]
        expected = self.key['beh-013']['numeric']
        for label, data in [('r-p1',first),('r-p2',second),('r-pooled',first+second)]:
            self.assertAlmostEqual(pearson(data), expected[label]['value'], places=12)
        self.assertLess(pearson(first), 0)
        self.assertGreater(pearson(first+second), 0)

    def test_duplicate_keys_nonfinite_extra_fields_rejected(self):
        raw = json.dumps(self.response('beh-001'))
        malformed = [raw[:-1] + ', "case_id":"beh-001"}',
                     raw.replace('"score-change": 4', '"score-change": NaN'),
                     raw[:-1] + ', "answer":"secret"}', '[]', '\x00', '['*2000 + ']'*2000]
        for value in malformed:
            result = b.grade(value, self.by_id['beh-001'], self.key['beh-001'])
            self.assertFalse(result['protocol_valid'])
            self.assertFalse(result['task_correct'])

    def test_pack_byte_change_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'cases.json'
            path.write_bytes(b.CASE_FILE.read_bytes() + b' ')
            with patch.object(b, 'CASE_FILE', path):
                with self.assertRaisesRegex(ValueError, 'frozen pack bytes changed'):
                    b.load_pack()

    def mock_caller(self, calls, fail_on=None, wrong_model=False):
        def call(model, prompt, options):
            case = json.loads(prompt.split('CASE:\n', 1)[1])
            self.assertEqual(set(case), b.CASE_FIELDS)
            self.assertNotIn('required_evidence_sets', prompt)
            calls.append(case['id'])
            if fail_on == len(calls):
                raise RuntimeError('Synthetic external audit refusal; no network access')
            return {'model': 'other:tag' if wrong_model else model, 'done':True,
                    'done_reason':'stop', 'response':b.oracle_response(case, self.key[case['id']]),
                    'eval_count':100, 'eval_duration':1000}
        return call

    def test_serial_adapter_mock_24_durable_records_and_no_overwrite(self):
        calls=[]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'run'
            summary=adapter.run_model(path,'synthetic:test','a'*64,'b'*40,self.mock_caller(calls))
            rows=[json.loads(line) for line in (path/'records.jsonl').read_text().splitlines()]
            self.assertEqual(calls,[case['id'] for case in self.cases])
            self.assertEqual(len(rows),24)
            self.assertTrue(summary['complete'])
            self.assertEqual(sum(role['structured_correct'] for role in summary['roles'].values()),24)
            self.assertEqual(summary['records_sha256'],hashlib.sha256((path/'records.jsonl').read_bytes()).hexdigest())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE((path/'records.jsonl').stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):
                adapter.run_model(path,'synthetic:test','a'*64,'b'*40,self.mock_caller(calls))
            self.assertEqual(len(calls),24)

    def test_caller_refusal_stops_and_retains_partial_result(self):
        calls=[]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'run'
            summary=adapter.run_model(path,'synthetic:test','a'*64,'b'*40,self.mock_caller(calls,fail_on=2))
            rows=[json.loads(line) for line in (path/'records.jsonl').read_text().splitlines()]
            self.assertFalse(summary['complete'])
            self.assertEqual(summary['unattempted_cases'],22)
            self.assertEqual(len(calls),2)
            self.assertTrue(rows[0]['request_ok'])
            self.assertFalse(rows[1]['request_ok'])
            self.assertEqual(rows[1]['request_failure_code'],'CALLER_ERROR')

    def test_wrong_model_refuses_and_short_digest_never_calls(self):
        calls=[]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'run'
            with self.assertRaisesRegex(ValueError,'full model digest'):
                adapter.run_model(path,'synthetic:test','a'*12,'b'*40,self.mock_caller(calls))
            self.assertEqual(calls,[])
            summary=adapter.run_model(path,'synthetic:test','a'*64,'b'*40,self.mock_caller(calls,wrong_model=True))
            rows=[json.loads(line) for line in (path/'records.jsonl').read_text().splitlines()]
            self.assertEqual(len(calls),1)
            self.assertFalse(summary['complete'])
            self.assertEqual(rows[0]['request_failure_code'],'MODEL_IDENTITY_MISMATCH')

    def test_completed_output_failure_does_not_skip_other_cases(self):
        for failure_code, bad_response, reason in (
            ('TRUNCATED_GENERATION', '{"partial":', 'length'),
            ('RESPONSE_NOT_TEXT', {'unexpected': 'object'}, 'stop'),
            ('RESPONSE_BYTE_BUDGET', 'x' * (b.MAX_RESPONSE + 1), 'stop')):
            calls=[]
            normal=self.mock_caller(calls)
            def call(model, prompt, options):
                reply=normal(model,prompt,options)
                if len(calls)==1:
                    reply.update(response=bad_response, done_reason=reason)
                return reply
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'run'
                summary=adapter.run_model(path,'synthetic:test','a'*64,'b'*40,call)
                rows=[json.loads(line) for line in (path/'records.jsonl').read_text().splitlines()]
                self.assertEqual(len(calls),24)
                self.assertEqual(summary['completed_case_slots'],24)
                self.assertEqual(summary['successful_requests'],23)
                self.assertTrue(summary['complete'])
                self.assertFalse(summary['fatal_hold'])
                self.assertFalse(rows[0]['request_ok'])
                self.assertFalse(rows[0]['grade']['task_correct'])
                self.assertEqual(rows[0]['request_failure_code'],failure_code)
                raw=bad_response.encode() if isinstance(bad_response,str) else b.canonical(bad_response)
                self.assertEqual(rows[0]['raw_response_sha256'],b.sha(raw))
                self.assertTrue(rows[0]['raw_response'])


if __name__ == '__main__':
    unittest.main()
