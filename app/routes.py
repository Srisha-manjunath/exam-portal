from flask import Blueprint, jsonify
from . import mongo

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return jsonify({"message": "Essay Exam Portal running with MongoDB Atlas!"})

@main.route("/test-db")
def test_db():
    try:
        mongo.db.command("ping")  # simple command to test connection
        return jsonify({"status": "Connected to MongoDB Atlas!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
