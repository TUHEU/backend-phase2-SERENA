import os
import requests
from flask import Flask, request, jsonify, send_from_directory, Response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.join(PROJECT_ROOT, "frontend"))

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5011")
ITINERARY_SERVICE_URL = os.environ.get("ITINERARY_SERVICE_URL", "http://localhost:5012")
RECOMMENDATION_SERVICE_URL = os.environ.get("RECOMMENDATION_SERVICE_URL", "http://localhost:5013")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response


# Route prefix -> upstream service. Order matters (checked top to bottom).
ROUTES = [
    ("/api/register", USER_SERVICE_URL, "/register"),
    ("/api/login", USER_SERVICE_URL, "/login"),
    ("/api/me", USER_SERVICE_URL, "/me"),
    ("/api/itineraries", ITINERARY_SERVICE_URL, "/itineraries"),
    ("/api/destinations", RECOMMENDATION_SERVICE_URL, "/destinations"),
    ("/api/meta", RECOMMENDATION_SERVICE_URL, "/meta"),
    ("/api/recommendations", RECOMMENDATION_SERVICE_URL, "/recommendations"),
]


def resolve_route(path):
    """path is the full request path, e.g. /api/itineraries/3 """
    for prefix, base_url, upstream_prefix in ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            remainder = path[len(prefix):]
            return base_url + upstream_prefix + remainder
    return None


@app.route("/api/<path:_any>", methods=["GET", "POST", "DELETE", "OPTIONS"])
def gateway(_any):
    if request.method == "OPTIONS":
        return "", 204

    target = resolve_route(request.path)
    if not target:
        return jsonify({"error": "Route API inconnue"}), 404

    headers = {"Content-Type": "application/json"}
    if "Authorization" in request.headers:
        headers["Authorization"] = request.headers["Authorization"]

    try:
        upstream = requests.request(
            method=request.method,
            url=target,
            params=request.args,
            headers=headers,
            data=request.get_data(),
            timeout=6,
        )
    except requests.RequestException:
        return jsonify({"error": "Service temporairement indisponible"}), 502

    return Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))


@app.route("/health")
def health():
    return jsonify({"service": "api-gateway", "status": "ok"})


# ---------- Serve frontend ----------

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
