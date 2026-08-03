from flask import Flask, jsonify, request
from groq import GroqError, RateLimitError
from pydantic import ValidationError

from plan_generator import ChatRequest, generate_plans

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/plan", methods=["POST"])
def plan():
    data = request.get_json(silent=True) or {}

    try:
        chat_request = ChatRequest(**data)
    except ValidationError:
        return jsonify({"error": "Invalid request body."}), 400

    try:
        plans = generate_plans(chat_request)
    except RateLimitError:
        return jsonify(
            {"error": "The planning service is rate limited right now. Try again shortly."}
        ), 429
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except GroqError:
        app.logger.exception("Plan generation failed")
        return jsonify({"error": "Couldn't build plans just now. Please try again."}), 502

    if not plans.plans:
        return jsonify(
            {"error": "Couldn't find enough open places near there. Try a wider area."}
        ), 422

    return jsonify({"plans": [plan.model_dump() for plan in plans.plans]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
