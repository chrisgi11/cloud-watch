import json, urllib.request, pathlib
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
out = pathlib.Path("debug"); out.mkdir(exist_ok=True)
for s in json.load(open("services.json")):
    url = "https://statusgator.com/services/" + s["slug"]
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"}), timeout=30)
        body = r.read().decode("utf-8", "replace")
        (out / f"{s['id']}.html").write_text(body)
        print(s["id"], r.status, len(body))
    except Exception as e:
        (out / f"{s['id']}.err").write_text(str(e))
        print(s["id"], "ERR", e)
