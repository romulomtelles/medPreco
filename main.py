import asyncio
import os
from flask import Flask, request, jsonify, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/search")
def search():
    from scrapers import search_all
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"error": "Informe o nome do medicamento"}), 400

    results = asyncio.run(search_all(q))

    if not results:
        return jsonify({"query": q, "results": [], "top3": [], "rest": [], "total": 0})

    return jsonify({
        "query": q,
        "results": results,
        "top3": results[:3],
        "rest": results[3:],
        "total": len(results),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
