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
        request.user_id = payload["sub"]
        return f(*args, **kwargs)
    return wrapper


@app.route("/health")
def health():
    return jsonify({"service": "itinerary-service", "status": "ok"})


@app.route("/itineraries", methods=["GET"])
@token_required
def list_itineraries():
    itineraries = load("itineraries")
    return jsonify([i for i in itineraries if i["user_id"] == request.user_id])


@app.route("/itineraries", methods=["POST"])
@token_required
def create_itinerary():
    body = request.get_json(force=True) or {}
    title = (body.get("title") or "").strip()
    destination_id = body.get("destination_id")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    notes = (body.get("notes") or "").strip()

    if not title or not destination_id or not start_date or not end_date:
        return jsonify({"error": "Titre, destination et dates sont requis"}), 400

    # --- Synchronous inter-service call: validate the destination against
    # recommendation-service, which owns the destinations data. ---
    try:
        resp = requests.get(f"{RECOMMENDATION_SERVICE_URL}/destinations/{destination_id}", timeout=4)
    except requests.RequestException:
        return jsonify({"error": "Service de recommandation indisponible, réessayez"}), 503

    if resp.status_code != 200:
        return jsonify({"error": "Destination invalide"}), 400
    dest = resp.json()

    itineraries = load("itineraries")
    itinerary = {
        "id": next_id(itineraries),
        "user_id": request.user_id,
        "title": title,
        "destination_id": destination_id,
        "destination_name": dest["name"],
        "start_date": start_date,
        "end_date": end_date,
        "notes": notes,
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    itineraries.append(itinerary)
    save("itineraries", itineraries)
    return jsonify(itinerary), 201


@app.route("/itineraries/<int:item_id>", methods=["DELETE"])
@token_required
def delete_itinerary(item_id):
    itineraries = load("itineraries")
    item = next((i for i in itineraries if i["id"] == item_id and i["user_id"] == request.user_id), None)
    if not item:
        return jsonify({"error": "Itinéraire introuvable"}), 404
    itineraries = [i for i in itineraries if i["id"] != item_id]
    save("itineraries", itineraries)
    return jsonify({"deleted": True})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5012)
