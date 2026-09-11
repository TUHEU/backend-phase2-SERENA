import json
import os
import datetime
from functools import wraps

import jwt
import requests
from flask import Flask, request, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SECRET_KEY = os.environ.get("SECRET_KEY", "yaounde-secret-dev-key-change-me")

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5011")
ITINERARY_SERVICE_URL = os.environ.get("ITINERARY_SERVICE_URL", "http://localhost:5012")
RECOMMENDATION_SERVICE_URL = os.environ.get("RECOMMENDATION_SERVICE_URL", "http://localhost:5013")

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
        request.user_name = payload.get("name", "")
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Helpers that call the sibling services. Each one degrades to an empty
# result instead of raising, so one unreachable peer doesn't take down the
# whole leaderboard/stats page — only the numbers that depend on it.
# ---------------------------------------------------------------------------

def fetch_json(url, default):
    try:
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return default


def all_users():
    """[{id, name, created_at}, ...] from user-service."""
    return fetch_json(f"{USER_SERVICE_URL}/users", [])


def all_itineraries():
    return fetch_json(f"{ITINERARY_SERVICE_URL}/itineraries/all", [])


def all_destinations():
    return fetch_json(f"{RECOMMENDATION_SERVICE_URL}/destinations", [])


def all_reviews():
    return fetch_json(f"{RECOMMENDATION_SERVICE_URL}/reviews/all", [])


@app.route("/health")
def health():
    return jsonify({"service": "community-service", "status": "ok"})


# --- Favorites --------------------------------------------------------------

@app.route("/favorites", methods=["GET"])
@token_required
def get_favorites():
    favorites = load("favorites")
    dest_ids = [f["destination_id"] for f in favorites if f["user_id"] == request.user_id]

    destinations = []
    for dest_id in dest_ids:
        try:
            resp = requests.get(f"{RECOMMENDATION_SERVICE_URL}/destinations/{dest_id}", timeout=4)
            if resp.status_code == 200:
                destinations.append(resp.json())
        except requests.RequestException:
            continue
    return jsonify(destinations)


@app.route("/favorites/<int:dest_id>", methods=["POST"])
@token_required
def add_favorite(dest_id):
    try:
        resp = requests.get(f"{RECOMMENDATION_SERVICE_URL}/destinations/{dest_id}", timeout=4)
    except requests.RequestException:
        return jsonify({"error": "Service de recommandation indisponible, réessayez"}), 503
    if resp.status_code != 200:
        return jsonify({"error": "Destination invalide"}), 400

    favorites = load("favorites")
    if any(f["user_id"] == request.user_id and f["destination_id"] == dest_id for f in favorites):
        return jsonify({"added": True})

    favorites.append({
        "id": next_id(favorites),
        "user_id": request.user_id,
        "destination_id": dest_id,
        "created_at": datetime.datetime.utcnow().isoformat(),
    })
    save("favorites", favorites)
    return jsonify({"added": True}), 201


@app.route("/favorites/<int:dest_id>", methods=["DELETE"])
@token_required
def remove_favorite(dest_id):
    favorites = load("favorites")
    favorites = [f for f in favorites if not (f["user_id"] == request.user_id and f["destination_id"] == dest_id)]
    save("favorites", favorites)
    return jsonify({"removed": True})


# --- Chat ---------------------------------------------------------------

@app.route("/chat/messages", methods=["GET"])
@token_required
def get_chat_messages():
    messages = load("chat_messages")
    after_id = request.args.get("after_id", type=int, default=0)
    if after_id:
        messages = [m for m in messages if m["id"] > after_id]
    return jsonify(messages)


@app.route("/chat/messages", methods=["POST"])
@token_required
def post_chat_message():
    body = request.get_json(force=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Message vide"}), 400
    if len(text) > 500:
        text = text[:500]

    messages = load("chat_messages")
    message = {
        "id": next_id(messages),
        "user_id": request.user_id,
        "user_name": request.user_name or "Anonyme",
        "text": text,
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    messages.append(message)
    save("chat_messages", messages)
    return jsonify(message), 201


@app.route("/chat/read", methods=["POST"])
@token_required
def mark_chat_read():
    # Read-receipts aren't surfaced anywhere in the UI yet; accept and no-op
    # so the frontend's fire-and-forget call never errors.
    return jsonify({"ok": True})


# --- Contact --------------------------------------------------------------

@app.route("/contact", methods=["POST"])
@token_required
def post_contact():
    body = request.get_json(force=True) or {}
    subject = (body.get("subject") or "").strip()
    message = (body.get("message") or "").strip()
    if not subject or not message:
        return jsonify({"error": "Sujet et message sont requis"}), 400

    messages = load("contact_messages")
    entry = {
        "id": next_id(messages),
        "user_id": request.user_id,
        "user_name": request.user_name or "Anonyme",
        "subject": subject[:150],
        "message": message[:2000],
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    messages.append(entry)
    save("contact_messages", messages)
    return jsonify({"sent": True}), 201


# --- Leaderboard & stats -----------------------------------------------

def _score(reviews, itineraries, messages):
    return reviews * 3 + itineraries * 2 + messages * 1


@app.route("/leaderboard", methods=["GET"])
@token_required
def leaderboard():
    users = all_users()
    itineraries = all_itineraries()
    reviews = all_reviews()
    messages = load("chat_messages")

    entries = []
    for u in users:
        uid = u["id"]
        r_count = sum(1 for r in reviews if r.get("user_id") == uid)
        i_count = sum(1 for i in itineraries if i.get("user_id") == uid)
        m_count = sum(1 for m in messages if m.get("user_id") == uid)
        score = _score(r_count, i_count, m_count)
        if score == 0:
            continue
        entries.append({
            "name": u["name"],
            "reviews": r_count,
            "itineraries": i_count,
            "messages": m_count,
            "score": score,
        })

    entries.sort(key=lambda e: e["score"], reverse=True)
    return jsonify(entries[:20])


@app.route("/stats", methods=["GET"])
@token_required
def stats():
    users = all_users()
    destinations = all_destinations()
    itineraries = all_itineraries()
    reviews = all_reviews()
    messages = load("chat_messages")
    favorites = load("favorites")

    dest_by_id = {d["id"]: d for d in destinations}
    review_counts = {}
    rating_total = 0
    for r in reviews:
        did = r.get("destination_id")
        review_counts[did] = review_counts.get(did, 0) + 1
        rating_total += r.get("rating", 0)

    top_destinations = sorted(review_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]
    top_destinations = [
        {"name": dest_by_id[did]["name"], "reviews": count}
        for did, count in top_destinations if did in dest_by_id
    ]

    categories = {}
    for d in destinations:
        cat = d.get("category", "Autre")
        categories[cat] = categories.get(cat, 0) + 1

    signups = {}
    for u in users:
        created = u.get("created_at")
        if not created:
            continue
        day = created[:10]
        signups[day] = signups.get(day, 0) + 1
    signups_by_day = [{"date": d, "count": c} for d, c in sorted(signups.items())]

    return jsonify({
        "users": len(users),
        "destinations": len(destinations),
        "itineraries": len(itineraries),
        "reviews": len(reviews),
        "chat_messages": len(messages),
        "favorites": len(favorites),
        "avg_rating": round(rating_total / len(reviews), 1) if reviews else None,
        "top_destinations": top_destinations,
        "categories": categories,
        "signups_by_day": signups_by_day,
    })


@app.route("/me/stats", methods=["GET"])
@token_required
def me_stats():
    uid = request.user_id
    itineraries = all_itineraries()
    reviews = all_reviews()
    messages = load("chat_messages")
    favorites = load("favorites")

    return jsonify({
        "itineraries": sum(1 for i in itineraries if i.get("user_id") == uid),
        "reviews": sum(1 for r in reviews if r.get("user_id") == uid),
        "favorites": sum(1 for f in favorites if f.get("user_id") == uid),
        "messages": sum(1 for m in messages if m.get("user_id") == uid),
    })


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5014)
