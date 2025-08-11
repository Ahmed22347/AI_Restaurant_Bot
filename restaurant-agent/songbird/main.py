from flask import Flask
from songbird.routes import main as main_blueprint
from dotenv import load_dotenv

def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.secret_key = "your-secret-key"
    app.register_blueprint(main_blueprint)
    return app
