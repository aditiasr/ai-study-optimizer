from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import pickle
import pandas as pd
import os
import warnings
from datetime import datetime
from pathlib import Path

try:
    import razorpay
except Exception:
    razorpay = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "study-ai-assessment-secret")

# ------------------ RAZORPAY CONFIG ------------------
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")

razorpay_client = None
if razorpay and RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ------------------ SETTINGS ------------------
FREE_USES = int(os.environ.get("FREE_USES", 100))
ASSESSMENT_MODE = os.environ.get("ASSESSMENT_MODE", "true").lower() == "true"
PREMIUM_PRICE_PAISE = 9900   # ₹99
CURRENCY = "INR"

history = []
latest_report = {}
BASE_DIR = Path(__file__).resolve().parent
HISTORY_FILE = BASE_DIR / "user_history.csv"

# ------------------ LOAD MODEL ------------------
MODEL_PATH = BASE_DIR / "model.pkl"
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    model = pickle.load(open(MODEL_PATH, "rb"))

# ------------------ HELPERS ------------------
def get_usage():
    if "use_count" not in session:
        session["use_count"] = 0

    # Assessment mode keeps the demo fully usable while payment feature remains available.
    if ASSESSMENT_MODE or "127.0.0.1" in request.host or "localhost" in request.host:
        paid_user = True
    else:
        paid_user = session.get("paid_user", False)

    return session["use_count"], paid_user


def get_remaining_free():
    use_count, _ = get_usage()
    return max(FREE_USES - use_count, 0)

# ------------------ RESET ROUTE ------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok", "project": "AI-Based Study Time Optimizer"})

@app.route("/reset-access")
def reset_access():
    session["use_count"] = 0
    session["paid_user"] = False
    return redirect(url_for("home"))

# ------------------ BASIC ROUTES ------------------
@app.route("/")
def welcome():
    return render_template("welcome.html")


@app.route("/home")
def home():
    use_count, paid_user = get_usage()
    return render_template(
        "home.html",
        use_count=use_count,
        paid_user=paid_user,
        remaining_free=get_remaining_free()
    )


@app.route("/input")
def input_page():
    use_count, paid_user = get_usage()
    return render_template(
        "input.html",
        use_count=use_count,
        paid_user=paid_user,
        remaining_free=get_remaining_free(),
        history=history
    )


@app.route("/history")
def history_page():
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        records = df.to_dict(orient="records")
    else:
        records = []

    return render_template("history.html", records=records)

# ------------------ PAYMENT PAGE ------------------
@app.route("/payment")
def payment():
    use_count, paid_user = get_usage()

    return render_template(
        "payment.html",
        use_count=use_count,
        paid_user=paid_user,
        free_uses=FREE_USES,
        amount_rupees=PREMIUM_PRICE_PAISE / 100,
        razorpay_key_id=RAZORPAY_KEY_ID
    )

# ------------------ CREATE RAZORPAY ORDER ------------------
@app.route("/create-razorpay-order", methods=["POST"])
def create_razorpay_order():
    use_count, paid_user = get_usage()

    if paid_user:
        return jsonify({"success": False, "message": "Premium already active."}), 400

    if not razorpay_client:
        return jsonify({
            "success": False,
            "message": "Razorpay keys missing. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
        }), 500

    try:
        receipt_id = f"rcpt_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        order_data = {
            "amount": PREMIUM_PRICE_PAISE,
            "currency": CURRENCY,
            "receipt": receipt_id,
            "notes": {
                "product": "AI-Based Study Time Optimizer Premium",
                "user_type": "student",
                "use_count": str(use_count)
            }
        }

        order = razorpay_client.order.create(data=order_data)
        session["current_order_id"] = order["id"]

        return jsonify({
            "success": True,
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key": RAZORPAY_KEY_ID,
            "name": "AI Based Study Time Optimizer",
            "description": "Premium Access Unlock"
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ------------------ VERIFY PAYMENT ------------------
@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    if not razorpay_client:
        return jsonify({"success": False, "message": "Razorpay not configured."}), 500

    try:
        razorpay_payment_id = request.form.get("razorpay_payment_id")
        razorpay_order_id = request.form.get("razorpay_order_id")
        razorpay_signature = request.form.get("razorpay_signature")

        server_order_id = session.get("current_order_id")

        if not server_order_id:
            return jsonify({"success": False, "message": "Order session missing."}), 400

        params_dict = {
            "razorpay_order_id": server_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature
        }

        razorpay_client.utility.verify_payment_signature(params_dict)
        session["paid_user"] = True

        return jsonify({"success": True, "redirect_url": url_for("input_page")})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# ------------------ DOWNLOAD REPORT ------------------
@app.route("/download-report")
def download_report():
    global latest_report

    if not latest_report:
        return "No report available. Please generate a result first."

    report_text = f"""
AI-BASED STUDY TIME OPTIMIZER REPORT
====================================

Productivity Score: {latest_report['score']}
Level: {latest_report['level']}
Badge: {latest_report['badge']}
Current Streak: {latest_report['streak']} High-Score Day(s)

Weekly Dashboard:
- Total Attempts: {latest_report['total_attempts']}
- Average Score: {latest_report['average_score']}
- Best Score: {latest_report['best_score']}
- Trend: {latest_report['trend']}

Message:
{latest_report['message']}

AI Insight:
{latest_report['explanation']}

Recommended Plan:
- Study Hours: {latest_report['recommended_study']}
- Sleep Hours: {latest_report['recommended_sleep']}

Suggestions:
"""
    for i, suggestion in enumerate(latest_report["suggestions"], start=1):
        report_text += f"{i}. {suggestion}\n"

    return Response(
        report_text,
        mimetype="text/plain",
        headers={"Content-disposition": "attachment; filename=study_time_report.txt"}
    )

# ------------------ CHATBOT ------------------
@app.route("/chatbot", methods=["POST"])
def chatbot():
    user_message = request.json.get("message", "").lower().strip()

    if not user_message:
        return jsonify({"reply": "Please ask something about study, sleep, focus, distractions, or productivity."})

    if "improve" in user_message or "better" in user_message:
        reply = "To improve your productivity, focus on better sleep, lower distractions, and consistent study hours."
    elif "sleep" in user_message:
        reply = "Sleep is very important. Try to get at least 6 to 8 hours of sleep for better concentration and productivity."
    elif "focus" in user_message:
        reply = "To improve focus, reduce distractions, take short breaks, and study in a quiet environment."
    elif "screen" in user_message:
        reply = "Too much screen time can reduce productivity. Try limiting unnecessary mobile usage during study hours."
    elif "study" in user_message:
        reply = "A good study plan includes regular study hours, revision, and balanced breaks."
    elif "exercise" in user_message:
        reply = "Exercise improves energy and mental freshness. Even 20 to 30 minutes daily can help."
    elif "distraction" in user_message:
        reply = "To reduce distractions, keep your phone away, use a study timer, and maintain a dedicated study area."
    elif "productivity" in user_message or "score" in user_message:
        reply = "Your productivity score depends on factors like sleep, focus, study hours, distractions, and lifestyle habits."
    elif "hello" in user_message or "hi" in user_message:
        reply = "Hello! I am your AI study assistant. Ask me about sleep, focus, study plans, or productivity."
    else:
        reply = "I can help with study, sleep, focus, distractions, exercise, and productivity tips."

    return jsonify({"reply": reply})

# ------------------ PREDICT ------------------
@app.route("/predict", methods=["POST"])
def predict():
    global latest_report

    use_count, paid_user = get_usage()

    # Payment gate
    if not paid_user and use_count >= FREE_USES:
        return redirect(url_for("payment"))

    try:
        sleep = float(request.form.get("sleep_hours", 0))
        wake = float(request.form.get("wakeup_time", 0))
        study = float(request.form.get("study_hours", 0))
        prev = float(request.form.get("previous_study_hours", 0))
        screen = float(request.form.get("screen_time", 0))
        distract = float(request.form.get("distractions", 0))
        energy = float(request.form.get("energy_level", 0))
        focus = float(request.form.get("focus_level", 0))
        break_time = float(request.form.get("break_time", 0))
        exercise = float(request.form.get("exercise_time", 0))

        feature_order = ["Sleep_Hours", "Wakeup_Time", "Study_Hours", "Previous_Study_Hours", "Screen_Time", "Distractions", "Energy_Level", "Focus_Level", "Break_Time", "Exercise_Time"]
        data = pd.DataFrame([[sleep, wake, study, prev, screen, distract, energy, focus, break_time, exercise]], columns=feature_order)
        score = round(float(model.predict(data)[0]), 2)
        score = max(0, min(100, score))

    except Exception as e:
        return render_template("result.html", prediction=0, level="Unable to predict", message=f"Please check input values. Error: {e}", history=history, use_count=session.get("use_count", 0), paid_user=paid_user, remaining_free=get_remaining_free(), recommended_study=0, recommended_sleep=0, explanation="The application is working, but prediction failed because the submitted values/model input format needs correction.", streak=0, badge="Try Again", average_score=0, best_score=0, trend="Not available", total_attempts=len(history), suggestions=["Go back and enter valid numeric values."])

    # Successful prediction ke baad hi count increase
    session["use_count"] += 1

    history.append(score)
    if len(history) > 5:
        history.pop(0)

    if score < 30:
        level = "Low 😟"
        msg = "Improve sleep and reduce distractions."
    elif score < 70:
        level = "Medium 🙂"
        msg = "Good, but improve focus."
    else:
        level = "High 🔥"
        msg = "Excellent routine!"

    if score < 50:
        recommended_study = study + 2
        recommended_sleep = max(7, sleep)
    elif score < 70:
        recommended_study = study + 1
        recommended_sleep = max(6.5, sleep)
    else:
        recommended_study = study
        recommended_sleep = sleep

    explanation = ""
    if screen > 5:
        explanation += "High screen time is reducing your productivity. "
    if distract > 5:
        explanation += "Too many distractions are affecting your focus. "
    if focus < 5:
        explanation += "Low focus level detected. Try improving concentration. "
    if sleep < 6:
        explanation += "Insufficient sleep is impacting performance. "
    if explanation == "":
        explanation = "Your routine looks well balanced. Keep it up!"

    suggestions = []
    if sleep < 6:
        suggestions.append("Increase sleep to at least 7 hours for better memory and concentration.")
    if screen > 5:
        suggestions.append("Reduce non-study screen time, especially before sleeping.")
    if distract > 5:
        suggestions.append("Use a distraction-free study space and keep your phone away during focus sessions.")
    if focus < 5:
        suggestions.append("Use 25–30 minute focused study blocks with short breaks.")
    if exercise < 20:
        suggestions.append("Add at least 20 minutes of light exercise or walking daily.")
    if not suggestions:
        suggestions.append("Great routine! Maintain consistency and keep tracking your progress.")

    streak = 0
    for item in reversed(history):
        if item >= 70:
            streak += 1
        else:
            break

    if score >= 85:
        badge = "Productivity Champion"
    elif score >= 70:
        badge = "Focus Star"
    elif score >= 50:
        badge = "Consistent Learner"
    else:
        badge = "Getting Started"

    total_attempts = len(history)
    average_score = round(sum(history) / len(history), 2) if history else 0
    best_score = max(history) if history else 0

    if len(history) >= 2:
        if history[-1] > history[-2]:
            trend = "Improving 📈"
        elif history[-1] < history[-2]:
            trend = "Needs Improvement 📉"
        else:
            trend = "Stable ➖"
    else:
        trend = "Not enough data yet"

    latest_report = {
        "score": score,
        "level": level,
        "message": msg,
        "recommended_study": recommended_study,
        "recommended_sleep": recommended_sleep,
        "explanation": explanation,
        "badge": badge,
        "streak": streak,
        "suggestions": suggestions,
        "average_score": average_score,
        "best_score": best_score,
        "trend": trend,
        "total_attempts": total_attempts
    }

    new_entry = pd.DataFrame([{
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "score": score,
        "level": level,
        "badge": badge,
        "sleep_hours": sleep,
        "study_hours": study,
        "focus_level": focus,
        "screen_time": screen
    }])

    if os.path.exists(HISTORY_FILE):
        new_entry.to_csv(HISTORY_FILE, mode="a", header=False, index=False)
    else:
        new_entry.to_csv(HISTORY_FILE, index=False)

    return render_template(
        "result.html",
        prediction=score,
        level=level,
        message=msg,
        history=history,
        use_count=session["use_count"],
        paid_user=paid_user,
        remaining_free=get_remaining_free(),
        recommended_study=recommended_study,
        recommended_sleep=recommended_sleep,
        explanation=explanation,
        streak=streak,
        badge=badge,
        average_score=average_score,
        best_score=best_score,
        trend=trend,
        total_attempts=total_attempts,
        suggestions=suggestions
    )

# ------------------ RUN ------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)