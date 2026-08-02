from flask import Flask, jsonify, request

from plan_generator import ChatRequest, generate_plans

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/plan", methods=["POST"])
def plan():
    data = request.get_json()

    chat_request = ChatRequest(
        current_location=data["current_location"],
        available_time=data["available_time"],
        vibe=data["vibe"],
        budget=data["budget"],
        transportation=data["transportation"],
        energy_level=data["energy_level"],
        companions=data["companions"],
        weather=data["weather"],
    )
    plans = generate_plans(chat_request)
    return jsonify({"plans": [plan.dict() for plan in plans.plans]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
