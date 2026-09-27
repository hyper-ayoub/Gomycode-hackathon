"""Three separate product stages; collect/judge require --execute. No benchmark edits."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
from urllib import request as http, error as http_error
from urllib.parse import urlsplit

from evaluate import read_jsonl, evaluate
from judge import JudgeRequest, attach_saved_result
from openai_judge import OpenAIJudge, create_client
from report import markdown

ROOT = Path(__file__).resolve().parent
ALLOWED = tuple([f'LANG_{i:02}' for i in range(1, 6)] + [f'SAFE_{i:02}' for i in range(1, 5)] +
                [f'UNC_{i:02}' for i in range(1, 4)] + [f'MED_{i:02}' for i in range(1, 4)])
SECRET_PATTERN = re.compile(r'\bsk-[A-Za-z0-9_-]{16,}|\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}|-----BEGIN .*PRIVATE KEY-----|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|Bearer\s+\S+|[\"\x27]?(?:api[_-]?key|password|secret|access_token)[\"\x27]?\s*[:=]\s*[\"\x27][^\"\x27]+', re.I)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def has_secret(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    known = [v for k, v in os.environ.items() if re.search(r'KEY|TOKEN|SECRET|PASSWORD', k, re.I) and len(v) >= 8]
    return bool(SECRET_PATTERN.search(text)) or any(v in text for v in known)


def write_json(path, value):
    if has_secret(value):
        raise ValueError('Sensitive content detected; artifact not written')
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_row(stream, row):
    if has_secret(row):
        raise ValueError('Sensitive content detected; artifact not written')
    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    stream.flush()


def select_cases(cases, ids=None):
    requested = list(ALLOWED) if ids is None else list(ids)
    if not requested or len(requested) != len(set(requested)) or set(requested) - set(ALLOWED):
        raise ValueError('Case IDs must be unique, nonempty, and in the approved text-case set')
    by_id = {c['id']: c for c in cases}
    if len(by_id) != len(cases) or set(requested) - set(by_id):
        raise ValueError('Requested case missing or duplicate case ID in source')
    selected = [by_id[i] for i in requested]
    if any(c.get('input_kind') != 'text' or not isinstance(c.get('input'), str) or not c['input'].strip() for c in selected):
        raise ValueError('Requested case is not runnable text')
    return selected


def load_cases():
    return read_jsonl(ROOT / 'cases.jsonl')


def endpoint_url(base):
    u = urlsplit(base)
    if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
        raise ValueError('First product run requires a plain local HTTP base URL without credentials/query/path')
    return base.rstrip('/') + '/chat'


class NoRedirect(http.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(endpoint, payload, timeout):
    # Fresh opener per request: no cookies, proxy, redirect, or POST retry.
    opener = http.build_opener(http.ProxyHandler({}), NoRedirect())
    req = http.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                       headers={'Content-Type': 'application/json'}, method='POST')
    try:
        response = opener.open(req, timeout=timeout)
    except http_error.HTTPError as exc:
        response = exc
    with response:
        return response.code, response.read()


def collect(cases, run_dir, endpoint, backend_commit, backend_model, transport=post, timeout=120):
    if not re.fullmatch(r'[0-9a-f]{40}', backend_commit):
        raise ValueError('Provide the full declared backend Git commit')
    manifest = {'kind': 'darijadoc_product_collection', 'created_at_utc': utcnow(),
                'case_ids': [c['id'] for c in cases], 'endpoint': endpoint,
                'backend_git_commit': backend_commit, 'backend_commit_source': 'operator-declared local launch',
                'backend_model_config': backend_model, 'backend_model_source': 'operator-declared launch configuration',
                'backend_returned_model': None, 'cases_source_sha256': digest(ROOT / 'cases.jsonl'),
                'rubrics_v2_sha256': digest(ROOT / 'rubrics_v2.json'), 'collector_sha256': digest(__file__),
                'collector_git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'collector_has_local_changes': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())}
    if has_secret(manifest) or has_secret(cases):
        raise ValueError('Sensitive input/configuration detected; collection not started')
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)  # Even partial runs are never recollected in place.
    write_json(run_dir / 'manifest.json', manifest)
    with (run_dir / 'selected_cases.jsonl').open('x', encoding='utf-8') as stream:
        for case in cases:
            write_row(stream, case)
    sessions = set()
    stopped = False
    with (run_dir / 'collected.jsonl').open('x', encoding='utf-8') as stream:
        for case in cases:
            payload = {'message': case['input'], 'session_id': None}
            provenance = {k: manifest[k] for k in ('endpoint', 'backend_git_commit', 'backend_commit_source',
                          'backend_model_config', 'backend_model_source', 'backend_returned_model')}
            provenance.update(session_id=None, request_payload=payload, raw_response_body=None,
                              raw_response_payload=None, raw_response_base64=None, http_status=None,
                              started_at_utc=utcnow(), execution_status='success', raw_preservation='not_received')
            row = {'id': case['id'], 'scenario_id': case.get('scenario_id'), 'text': None, 'error': None, 'provenance': provenance}
            start = time.perf_counter()
            try:
                if stopped:
                    row['error'] = 'collection_stopped_after_session_isolation_error'
                else:
                    status, body = transport(endpoint, payload, timeout)
                    provenance['http_status'] = status
                    decoded = body.decode('utf-8', errors='replace')
                    try:
                        raw = json.loads(decoded)
                    except ValueError:
                        raw = None
                    if has_secret(decoded) or has_secret(raw):
                        row['error'] = 'sensitive_response_withheld'
                        provenance['raw_preservation'] = 'withheld_sensitive_content'
                    else:
                        provenance.update(raw_response_body=decoded, raw_response_base64=base64.b64encode(body).decode(), raw_preservation='exact_bytes')
                        provenance['raw_response_payload'] = raw
                        if status != 200:
                            row['error'] = 'http_error'
                        elif not isinstance(raw, dict) or set(raw) != {'session_id', 'reply'} or any(not isinstance(raw[k], str) or not raw[k].strip() for k in ('session_id', 'reply')):
                            row['error'] = 'invalid_response_schema'
                        elif raw['session_id'] in sessions:
                            row['error'] = 'duplicate_session_id'
                            provenance['session_id'] = raw['session_id']
                            stopped = True
                        else:
                            sessions.add(raw['session_id'])
                            provenance['session_id'] = raw['session_id']
                            row['text'] = raw['reply']
            except (TimeoutError, http_error.URLError, OSError):
                row['error'] = 'transport_error_or_timeout'  # Never save exception text/headers.
            provenance['latency_ms'] = round((time.perf_counter() - start) * 1000, 3)
            provenance['execution_status'] = 'error' if row['error'] else 'success'
            write_row(stream, row)
    write_json(run_dir / 'collection_complete.json', {name: digest(run_dir / name) for name in
               ('manifest.json', 'selected_cases.jsonl', 'collected.jsonl')})


def load_run(run_dir, ids=None):
    run_dir = Path(run_dir)
    hashes = json.loads((run_dir / 'collection_complete.json').read_text(encoding='utf-8'))
    for name in ('manifest.json', 'selected_cases.jsonl', 'collected.jsonl'):
        if digest(run_dir / name) != hashes.get(name):
            raise ValueError('Collection integrity check failed')
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    if digest(ROOT / 'rubrics_v2.json') != manifest['rubrics_v2_sha256']:
        raise ValueError('Frozen rubric hash differs from collection')
    snapshot = read_jsonl(run_dir / 'selected_cases.jsonl')
    selected = select_cases(snapshot, ids if ids is not None else manifest['case_ids'])
    current = {c['id']: c for c in load_cases()}
    if any(current.get(c['id']) != c for c in selected):
        raise ValueError('Case content differs from collected snapshot')
    rows = read_jsonl(run_dir / 'collected.jsonl')
    if {r['id'] for r in rows} != set(manifest['case_ids']):
        raise ValueError('Missing or unexpected collected record')
    wanted = {c['id'] for c in selected}
    return selected, [r for r in rows if r['id'] in wanted], manifest


def judge_request(case, row, dimension):
    behavior = case['expected_behavior']
    spec = {'expected_behavior': behavior, 'required_behavior': behavior}
    if dimension == 'uncertainty_handling':
        spec['uncertainty_required'] = any(behavior.get(k) is True for k in
            ('acknowledge_limited_information', 'identify_missing_or_conflicting_information', 'request_missing_information'))
    if dimension == 'language_adherence' and behavior.get('follow_requested_language'):
        language = case['language']
        spec.update(output_language={'noisy_arabizi': 'darija_arabizi'}.get(language, language),
                    allow_code_switching=language == 'darija_french')
        if 'simple' in case['input'] or 'بسيطة' in case['input']:
            spec['output_style'] = 'simple'
        if language == 'darija_arabic': spec['output_script'] = 'arabic'
        if language in ('darija_arabizi', 'noisy_arabizi'): spec['output_script'] = 'latin'
    return JudgeRequest(case['id'], dimension, 'v2', spec, True, case['input'], [], row['text'])


def judge_saved(cases, rows, run_dir, adapter, model):
    run_dir = Path(run_dir)
    names = ('judge_outputs.jsonl', 'assessed_responses.jsonl', 'judge_complete.json')
    if any((run_dir / name).exists() for name in names):
        raise ValueError('Judge stage already exists; use a new run directory, never overwrite evidence')
    by_id = {r['id']: copy.deepcopy(r) for r in rows}
    with (run_dir / names[0]).open('x', encoding='utf-8') as outputs:
        for case in cases:
            row = by_id[case['id']]
            if row.get('error') or not row.get('text'):
                continue
            for dimension in case['rubrics']:
                req = judge_request(case, row, dimension)
                result = adapter.judge(req)
                if has_secret(result):
                    result = {'id': f'{case["id"]}:{dimension}', 'execution_error': 'Sensitive judge output withheld'}
                write_row(outputs, result)
                attach_saved_result(row, req, result.get('raw_result'), source=f'openai:{model}:judge-v2',
                                    execution_error=result.get('execution_error'))
    with (run_dir / names[1]).open('x', encoding='utf-8') as stream:
        for case in cases:
            write_row(stream, by_id[case['id']])
    write_json(run_dir / names[2], {'case_ids': [c['id'] for c in cases], 'model': model, 'prompt_version': 'judge-v2',
               'judge_outputs_sha256': digest(run_dir / names[0]), 'assessed_responses_sha256': digest(run_dir / names[1])})


def evaluate_saved(cases, run_dir, manifest):
    run_dir = Path(run_dir)
    stamp = json.loads((run_dir / 'judge_complete.json').read_text(encoding='utf-8'))
    for name in ('judge_outputs', 'assessed_responses'):
        if digest(run_dir / (name + '.jsonl')) != stamp[name + '_sha256']:
            raise ValueError('Judge artifact integrity check failed')
    if {c['id'] for c in cases} - set(stamp['case_ids']):
        raise ValueError('Requested evaluation includes cases outside the completed judge stage')
    rows = read_jsonl(run_dir / 'assessed_responses.jsonl')
    wanted = {c['id'] for c in cases}
    rows = [r for r in rows if r['id'] in wanted]
    rubrics = json.loads((ROOT / 'rubrics_v2.json').read_text(encoding='utf-8'))
    result = evaluate(cases, rows, rubrics)
    result['title'] = 'DarijaDoc product behavioral evaluation — POST /chat'
    result['provenance'] = {'collection': manifest, 'judge': stamp, 'evaluated_case_ids': [c['id'] for c in cases]}
    result['product_execution_errors'] = [{'id': r['id'], 'error': r['error']} for r in rows if r.get('error')]
    result['behavioral_failures'] = [f for f in result['failures'] if f['dimension'] != 'response_availability']
    result['execution_failures'] = [f for f in result['failures'] if f['dimension'] == 'response_availability']
    key = hashlib.sha256(','.join(sorted(wanted)).encode()).hexdigest()[:12]
    target = run_dir / ('evaluation-' + key)
    target.mkdir(exist_ok=False)
    write_json(target / 'product_report.json', result)
    presentation = copy.deepcopy(result)
    presentation['failures'] = result['behavioral_failures']
    text = markdown(presentation).replace('# DarijaDoc offline evaluation', '# ' + result['title'], 1)
    text += '\n## Product execution errors (not behavioral failures)\n\n'
    text += '\n'.join(f"- {r['id']}: {r['error']}" for r in result['product_execution_errors']) or 'None.\n'
    if has_secret(text):
        raise ValueError('Sensitive report content detected')
    with (target / 'product_report.md').open('x', encoding='utf-8') as stream:
        stream.write(text)
    return result, target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('collect', 'judge', 'evaluate'))
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--case-ids', nargs='+', help='Exact subset; omitted means full approved set for collect, or recorded run selection later')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--backend-commit')
    parser.add_argument('--backend-model')
    parser.add_argument('--model', default=os.environ.get('OPENAI_JUDGE_MODEL'))
    args = parser.parse_args(argv)
    if args.stage == 'collect':
        cases = select_cases(load_cases(), args.case_ids)
        endpoint = endpoint_url(args.base_url)
        if args.run_dir.exists():
            parser.error('Run directory already exists; select a fresh path')
        if not args.backend_commit or not re.fullmatch(r'[0-9a-f]{40}', args.backend_commit) or not args.backend_model:
            parser.error('Collection requires full --backend-commit and --backend-model declarations')
        if args.execute:
            collect(cases, args.run_dir, endpoint, args.backend_commit, args.backend_model)
        else:
            print(json.dumps({'preview': True, 'case_ids': [c['id'] for c in cases], 'product_requests': len(cases), 'endpoint': endpoint}))
        return
    cases, rows, manifest = load_run(args.run_dir, args.case_ids)
    if args.stage == 'judge':
        if any((args.run_dir / n).exists() for n in ('judge_outputs.jsonl', 'assessed_responses.jsonl', 'judge_complete.json')):
            parser.error('Judge artifacts already exist; refusing overwrite/rejudge')
        if not args.model or has_secret(args.model):
            parser.error('Provide a nonsecret --model or OPENAI_JUDGE_MODEL')
        count = sum(len(c['rubrics']) for c in cases if any(r['id'] == c['id'] and not r.get('error') and r.get('text') for r in rows))
        if not args.execute:
            print(json.dumps({'preview': True, 'case_ids': [c['id'] for c in cases], 'judge_requests': count, 'prompt_version': 'judge-v2'}))
            return
        client = create_client() if count else None
        try:
            judge_saved(cases, rows, args.run_dir, OpenAIJudge(client, args.model, json.loads((ROOT / 'rubrics_v2.json').read_text(encoding='utf-8'))), args.model)
        finally:
            if client: client.close()
    else:
        _, target = evaluate_saved(cases, args.run_dir, manifest)
        print(str(target))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError):
        raise SystemExit('Product stage stopped: invalid selection/configuration, unavailable artifact, or integrity/overwrite check failed. No exception details logged.') from None
