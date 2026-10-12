import json
import subprocess
import sys
from test_wiley_doi_paths import SOURCE, CASES, load_extract
BASE = '745d09547e3b092f5c66e7d1915e455ffb90b797'
if len(sys.argv) > 1:
    source = subprocess.check_output(['git', 'show', BASE + ':dietnerd-backend/helper_functions.py'], text=True) if sys.argv[1] == 'before' else SOURCE.read_text()
    extract = load_extract(source)
    print(json.dumps([extract(url) for url, _ in CASES]))
else:
    print('| Run | Before exact DOI cases | After exact DOI cases | Before full URL | After full URL |')
    print('| --- | --- | --- | --- | --- |')
    for run in range(1, 21):
        before = json.loads(subprocess.check_output([sys.executable, __file__, 'before'], text=True))
        after = json.loads(subprocess.check_output([sys.executable, __file__, 'after'], text=True))
        bp = sum(value == case[1] for value, case in zip(before, CASES))
        ap = sum(value == case[1] for value, case in zip(after, CASES))
        assert bp == 4 and ap == 12
        print(f'| {run} | {bp}/12 | {ap}/12 | {before[1]} | {after[1]} |')
