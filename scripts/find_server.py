import urllib.request, json

ports = [8000] + list(range(64000,65001))
found = []
for p in ports:
    try:
        url = f'http://127.0.0.1:{p}/api/patients'
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=0.6) as r:
            data = r.read(65536)
            try:
                parsed = json.loads(data.decode('utf-8'))
            except Exception:
                parsed = data.decode('utf-8', errors='replace')
            print('OK', p, type(parsed).__name__, (len(parsed) if isinstance(parsed, list) else 'len?'))
            found.append((p, parsed))
            break
    except Exception:
        pass
if not found:
    print('No server found on scanned ports')
else:
    p, parsed = found[0]
    print('Found server on port', p)
    if isinstance(parsed, list):
        print('First 3 entries:', parsed[:3])
    else:
        print('Response sample:', str(parsed)[:400])
