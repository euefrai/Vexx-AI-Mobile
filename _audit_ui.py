import re, sys
sys.path.insert(0, ".")
js = open("public/app.js", encoding="utf-8").read()
html = open("public/index.html", encoding="utf-8").read()
ids_js = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", js))
ids_html = set(re.findall(r'id="([A-Za-z0-9_]+)"', html))
getel = set(re.findall(r'getElementById\("([A-Za-z0-9_]+)"\)', js))
faltam = sorted((ids_js | getel) - ids_html)
print("IDs usados no JS:", len(ids_js | getel), "| ausentes no HTML:", len(faltam))
for i in faltam:
    print("  FALTA:", i)
