import json
import os
import datetime
from functools import wraps

import jwt
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

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


def make_token(user):
    payload = {
        "sub": str(user["id"]),
        "name": user["name"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


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
        return f(*args, **kwargs)
    return wrapper


@app.route("/health")
def health():
    return jsonify({"service": "user-service", "status": "ok"})


@app.route("/register", methods=["POST"])
def register():
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "Nom, email et mot de passe sont requis"}), 400

    users = load("users")
    if any(u["email"] == email for u in users):
        return jsonify({"error": "Un compte existe déjà avec cet email"}), 409

    user = {
        "id": next_id(users),
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    users.append(user)
    save("users", users)

    token = make_token(user)
    return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}), 201


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json(force=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    users = load("users")
    user = next((u for u in users if u["email"] == email), None)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401

    token = make_token(user)
    return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}})


@app.route("/me", methods=["GET"])
@token_required
def me():
    users = load("users")
    user = next((u for u in users if u["id"] == request.user_id), None)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    return jsonify({
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "created_at": user.get("created_at"),
    })


@app.route("/me", methods=["PUT"])
@token_required
def update_me():
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Le nom ne peut pas être vide"}), 400

    users = load("users")
    user = next((u for u in users if u["id"] == request.user_id), None)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    user["name"] = name
    save("users", users)

    token = make_token(user)
    return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}})


@app.route("/me/password", methods=["POST"])
@token_required
def change_password():
    body = request.get_json(force=True) or {}
    current_password = body.get("current_password") or ""
    new_password = body.get("new_password") or ""

    if not current_password or not new_password:
        return jsonify({"error": "Mot de passe actuel et nouveau mot de passe requis"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Le nouveau mot de passe doit contenir au moins 6 caractères"}), 400

    users = load("users")
    user = next((u for u in users if u["id"] == request.user_id), None)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    if not check_password_hash(user["password_hash"], current_password):
        return jsonify({"error": "Mot de passe actuel incorrect"}), 401

    user["password_hash"] = generate_password_hash(new_password)
    save("users", users)
    return jsonify({"updated": True})


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user_internal(user_id):
    """Internal endpoint used by other services (e.g. to display a user's name)."""
    users = load("users")
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    return jsonify({"id": user["id"], "name": user["name"]})


@app.route("/users", methods=["GET"])
def list_users_internal():
    """Internal endpoint used by community-service to compute leaderboard/stats.
    Deliberately excludes email and password_hash."""
    users = load("users")
    return jsonify([
        {"id": u["id"], "name": u["name"], "created_at": u.get("created_at")}
        for u in users
    ])


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5011)
