from flask import Blueprint, render_template, request, session, jsonify
from songbird.agent.agent import ConversationalAgent
import uuid

main = Blueprint("main", __name__)
agent = ConversationalAgent()

def get_user_id():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    return session["user_id"]

@main.route("/", methods=["GET"])
def index():
    return render_template("chat.html")

@main.route("/start", methods=["GET"])
def start():
    user_id = get_user_id()
    message = agent.start_conversation(user_id)
    return jsonify({"message": message})

@main.route("/chat", methods=["POST"])
def chat():
    user_id = get_user_id()
    user_message = request.json.get("message")
    response = agent.handle_user_input(user_id, user_message)
    return jsonify({"response": response})

@main.route("/end", methods=["GET"])
def end():
    user_id = get_user_id()
    message = agent.end_session(user_id)
    return jsonify({"message": message})
