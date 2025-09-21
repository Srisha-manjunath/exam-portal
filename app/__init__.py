from flask import Flask
from flask_pymongo import PyMongo
from config import Config

mongo = PyMongo()

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Load config
    app.config.from_object(Config)

    # Initialize MongoDB connection
    mongo.init_app(app)

    # Register routes
    from .routes import main
    app.register_blueprint(main)

    return app
