import json
import os
import datetime
from functools import wraps

import jwt
from flask import Flask, request, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SECRET_KEY = os.environ.get("SECRET_KEY", "yaounde-secret-dev-key-change-me")

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response


def _path(name):
    return os.path.join(DATA_DIR, f"{name}.json")


def load(name):
    with open(_path(name), "r", encoding="utf-8") as f:
        return json.load(f)


def save(name, data):
    with open(_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def next_id(items):
    return (max([item["id"] for item in items], default=0)) + 1


def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Token manquant"}), 401
        try:
            payload = jwt.decode(auth.split(" ", 1)[1], SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expirée, reconnectez-vous"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token invalide"}), 401
        request.user_id = int(payload["sub"])
        request.user_name = payload["name"]
        return f(*args, **kwargs)
    return wrapper


@app.route("/health")
def health():
    return jsonify({"service": "recommendation-service", "status": "ok"})


@app.route("/destinations", methods=["GET"])
def get_destinations():
    destinations = load("destinations")
    q = (request.args.get("q") or "").strip().lower()
    category = (request.args.get("category") or "").strip()
    quartier = (request.args.get("quartier") or "").strip()

    def matches(d):
        if q and q not in d["name"].lower() and q not in d["quartier"].lower():
            return False
        if category and d["category"] != category:
            return False
        if quartier and d["quartier"] != quartier:
            return False
        return True

    return jsonify([d for d in destinations if matches(d)])


@app.route("/destinations/<int:dest_id>", methods=["GET"])
def get_destination(dest_id):
    destinations = load("destinations")
    dest = next((d for d in destinations if d["id"] == dest_id), None)
    if not dest:
        return jsonify({"error": "Destination introuvable"}), 404
    return jsonify(dest)


@app.route("/meta", methods=["GET"])
def get_meta():
    destinations = load("destinations")
    return jsonify({
        "categories": sorted({d["category"] for d in destinations}),
        "quartiers": sorted({d["quartier"] for d in destinations}),
    })


@app.route("/recommendations", methods=["GET"])
def recommendations():
    destinations = load("destinations")
    top = sorted(destinations, key=lambda d: d["popularity"], reverse=True)[:6]
    return jsonify(top)


@app.route("/reviews/all", methods=["GET"])
def list_all_reviews_internal():
    """Internal endpoint used by community-service for leaderboard/stats
    aggregation. Not routed through the gateway."""
    return jsonify(load("reviews"))


@app.route("/destinations/<int:dest_id>/reviews", methods=["GET"])
def get_reviews(dest_id):
    reviews = load("reviews")
    return jsonify([r for r in reviews if r["destination_id"] == dest_id])


@app.route("/destinations/<int:dest_id>/reviews", methods=["POST"])
@token_required
def add_review(dest_id):
    destinations = load("destinations")
    if not any(d["id"] == dest_id for d in destinations):
        return jsonify({"error": "Destination introuvable"}), 404

    body = request.get_json(force=True) or {}
    rating = body.get("rating")
    comment = (body.get("comment") or "").strip()
    if not rating or not (1 <= int(rating) <= 5):
        return jsonify({"error": "Note entre 1 et 5 requise"}), 400

    reviews = load("reviews")
    review = {
        "id": next_id(reviews),
        "destination_id": dest_id,
        "user_id": request.user_id,
        "user_name": request.user_name,
        "rating": int(rating),
        "comment": comment,
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    reviews.append(review)
    save("reviews", reviews)
    return jsonify(review), 201


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5013)
