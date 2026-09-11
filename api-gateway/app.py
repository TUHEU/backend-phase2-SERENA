import os
import requests
from flask import Flask, request, jsonify, Response

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5011")
ITINERARY_SERVICE_URL = os.environ.get("ITINERARY_SERVICE_URL", "http://localhost:5012")
RECOMMENDATION_SERVICE_URL = os.environ.get("RECOMMENDATION_SERVICE_URL", "http://localhost:5013")
COMMUNITY_SERVICE_URL = os.environ.get("COMMUNITY_SERVICE_URL", "http://localhost:5014")

# Pure API gateway — the frontend is served separately by Nginx, not by
# this service, so no static file handling lives here.
app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


# Route prefix -> upstream service. Order matters (checked top to bottom) —
# more specific prefixes must come before shorter ones they'd otherwise be
# swallowed by (e.g. /api/me/stats before /api/me).
ROUTES = [
    ("/api/register", USER_SERVICE_URL, "/register"),
    ("/api/login", USER_SERVICE_URL, "/login"),
    ("/api/me/stats", COMMUNITY_SERVICE_URL, "/me/stats"),
    ("/api/me", USER_SERVICE_URL, "/me"),
    ("/api/itineraries", ITINERARY_SERVICE_URL, "/itineraries"),
    ("/api/destinations", RECOMMENDATION_SERVICE_URL, "/destinations"),
    ("/api/meta", RECOMMENDATION_SERVICE_URL, "/meta"),
    ("/api/recommendations", RECOMMENDATION_SERVICE_URL, "/recommendations"),
    ("/api/favorites", COMMUNITY_SERVICE_URL, "/favorites"),
    ("/api/chat", COMMUNITY_SERVICE_URL, "/chat"),
    ("/api/leaderboard", COMMUNITY_SERVICE_URL, "/leaderboard"),
    ("/api/stats", COMMUNITY_SERVICE_URL, "/stats"),
    ("/api/contact", COMMUNITY_SERVICE_URL, "/contact"),
]


def resolve_route(path):
    """path is the full request path, e.g. /api/itineraries/3 """
    for prefix, base_url, upstream_prefix in ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            remainder = path[len(prefix):]
            return base_url + upstream_prefix + remainder
    return None


@app.route("/api/<path:_any>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
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


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
