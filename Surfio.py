from flask import Flask, request, render_template_string
import sqlite3
import math
import json
import urllib.request
import urllib.parse

DB_NAME = "Surfio.db"
app = Flask(__name__)
PER_PAGE = 25

# CONFIGURATION GROQ
GROQ_API_KEY = "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"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def appeler_ai_urllib(prompt):
    """ Envoie une requête à Groq via urllib (sans bibliothèque externe) """
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }
    
    req = urllib.request.Request(GROQ_URL, data=json.dumps(data).encode('utf-8'))
    req.add_header('Authorization', f'Bearer {GROQ_API_KEY}')
    req.add_header('Content-Type', 'application/json')

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data['choices'][0]['message']['content']
    except Exception as e:
        print(f"Erreur API : {e}")
        return None

def traduire_resultats(results, lang_cible):
    if lang_cible == "fr" or not results: return results
    
    # On prépare un gros prompt pour traduire tout d'un coup (plus rapide)
    indices = []
    text_to_translate = ""
    for i, (url, titre, snippet) in enumerate(results):
        text_to_translate += f"[{i}] {titre} | {snippet}\n"
    
    prompt = f"Translate these search results into {lang_cible}. Keep HTML <b> tags. Format: [index] Translated Title | Translated Snippet. \n\n{text_to_translate}"
    
    response = appeler_ai_urllib(prompt)
    if not response: return results

    translated_results = list(results)
    # On essaie de parser la réponse ligne par ligne
    for line in response.strip().split('\n'):
        try:
            if '|' in line and ']' in line:
                parts = line.split(']', 1)[1].split('|', 1)
                idx = int(line.split('[')[1].split(']')[0])
                url = results[idx][0]
                translated_results[idx] = (url, parts[0].strip(), parts[1].strip())
        except: continue
            
    return translated_results

# --- Le reste du code (Template et Routes) reste identique ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Surfio Search</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .search-box { display: flex; gap: 10px; margin-bottom: 30px; }
        input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 5px; }
        .result { margin-bottom: 25px; border-left: 3px solid #eee; padding-left: 15px; }
        .result a { font-size: 1.2rem; color: #1a0dab; text-decoration: none; }
        .url { color: #006621; font-size: 0.85rem; display: block; }
        b { background: #fff1a8; }
        .pagination { margin-top: 20px; text-align: center; }
        .pagination a { padding: 8px 12px; border: 1px solid #ddd; text-decoration: none; margin: 2px; }
        .active { background: #007bff; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔎 <a href="/" style="text-decoration:none; color:black;">Surfio</a></h1>
        <select id="langSelect" onchange="changeLang()">
            <option value="fr">Français</option>
            <option value="en">English</option>
            <option value="es">Español</option>
            <option value="de">Deutsch</option>
        </select>
    </div>

    <form action="/search" class="search-box">
        <input name="q" placeholder="Rechercher..." value="{{ query }}">
        <input type="hidden" name="l" id="langInput">
        <button type="submit">Search</button>
    </form>

    {% if results %}
        <p>{{ total }} résultats ({{ lang_code.upper() }})</p>
        {% for url, titre, snippet in results %}
            <div class="result">
                <a href="{{ url }}">{{ titre }}</a>
                <span class="url">{{ url }}</span>
                <p>{{ snippet|safe }}</p>
            </div>
        {% endfor %}
        
        <div class="pagination">
            {% for p in range(start_page, end_page + 1) %}
                <a href="/search?q={{ query }}&p={{ p }}&l={{ lang_code }}" class="{{ 'active' if p == current_page else '' }}">{{ p }}</a>
            {% endfor %}
        </div>
    {% endif %}

    <script>
        const langSelect = document.getElementById('langSelect');
        const langInput = document.getElementById('langInput');
        const savedLang = localStorage.getItem('surfio_lang') || 'fr';
        langSelect.value = savedLang;
        langInput.value = savedLang;

        function changeLang() {
            localStorage.setItem('surfio_lang', langSelect.value);
            if ("{{ query }}") window.location.href = "/search?q={{ query }}&l=" + langSelect.value;
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE, query="")

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    page = request.args.get("p", 1, type=int)
    lang = request.args.get("l", "fr")
    
    if not query: return home()

    offset = (page - 1) * PER_PAGE
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT count(*) FROM pages_fts WHERE pages_fts MATCH ?", (query,))
        total = cursor.fetchone()[0]
        cursor.execute("SELECT url, titre, snippet(pages_fts, 2, '<b>', '</b>', '...', 20) FROM pages_fts WHERE pages_fts MATCH ? ORDER BY bm25(pages_fts) LIMIT ? OFFSET ?", (query, PER_PAGE, offset))
        raw_results = cursor.fetchall()
    except:
        raw_results, total = [], 0
    finally:
        conn.close()

    results = traduire_resultats(raw_results, lang)
    total_pages = math.ceil(total / PER_PAGE)
    
    return render_template_string(HTML_TEMPLATE, results=results, query=query, total=total, current_page=page, total_pages=total_pages, start_page=max(1, page-4), end_page=min(total_pages, page+4), lang_code=lang)

if __name__ == "__main__":
    app.run(debug=True)