"""
ml/predictor.py
===============
The prediction centre used by the running application.

It follows the order set out in Chapter 3 and the system flow document:

    1. ELIGIBILITY GATE (a fixed rule, not the model)
       Attendance is compared with the 70% threshold. A student below it is
       shown their status and advice, and the model is NOT run for them.

    2. PREDICTION (the trained model)
       For an eligible student, the saved Logistic Regression or Random Forest
       model reads the student's features and returns at risk / not at risk
       together with a probability.

    3. RECOMMENDATION LAYER (fixed rules again)
       Each rule looks at one feature, so two students who are both at risk
       can receive different advice, matched to their own situation.

The models are the ones produced by train_models.py. Run that first:

    python ml/train_models.py
"""

from __future__ import annotations

import os
import sys

import pandas as pd
from joblib import load

# This file is normally imported by the app, which runs from the folder above.
# Adding that folder here means it can also be run on its own for a quick test:
#     python ml/predictor.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import EXAM_ELIGIBILITY_PERCENT

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")

# The order here must match the order the models were trained on.
FEATURES = ["prior_gpa", "test_score", "attendance_rate", "assignment_rate"]

# The model the running system uses.
#
# Both models were compared in train_models.py. Random Forest scored higher on
# accuracy, but Logistic Regression caught 82% of the students who were really
# heading for failure against Random Forest's 64%. For an early warning system
# a missed student costs more than a false alarm, so recall decides it.
DEPLOYED_MODEL = "logistic_regression"

# Typical values, used only when a feature is not available yet (see the
# "progressive prediction" note in the system flow document).
DEFAULTS = {"prior_gpa": 2.8, "test_score": 25.0, "assignment_rate": 60.0}

_cache: dict = {}


def available_models() -> list[str]:
    """Which trained models are on disk."""
    if not os.path.isdir(MODELS):
        return []
    return sorted(f.replace("dataset_a_", "").replace(".joblib", "")
                  for f in os.listdir(MODELS) if f.startswith("dataset_a_"))


def load_model(name: str = DEPLOYED_MODEL):
    """Load a trained model, keeping it in memory after the first time."""
    if name in _cache:
        return _cache[name]
    path = os.path.join(MODELS, f"dataset_a_{name}.joblib")
    if not os.path.exists(path):
        return None
    _cache[name] = load(path)
    return _cache[name]


# ---------------------------------------------------------------------------
# Step 1: the eligibility gate
# ---------------------------------------------------------------------------
def is_eligible(attendance_percent: float) -> bool:
    return attendance_percent >= EXAM_ELIGIBILITY_PERCENT


# ---------------------------------------------------------------------------
# Step 2: the model
# ---------------------------------------------------------------------------
def predict(features: dict, model_name: str = DEPLOYED_MODEL) -> dict | None:
    """
    Run the trained model on one student's features.

    Returns at_risk (True/False), the probability, and whether the result is
    provisional because some features were not supplied yet.
    """
    model = load_model(model_name)
    if model is None:
        return None

    provisional = False
    row = []
    for f in FEATURES:
        value = features.get(f)
        if value is None:
            value = DEFAULTS.get(f, 0.0)
            provisional = True          # a typical value was used, not a real one
        row.append(float(value))

    # a DataFrame with the same column names the model was trained on,
    # otherwise scikit-learn warns that the feature names are missing
    frame = pd.DataFrame([row], columns=FEATURES)
    at_risk = bool(model.predict(frame)[0])
    probability = float(model.predict_proba(frame)[0][1])
    return {"at_risk": at_risk, "probability": probability,
            "provisional": provisional,
            "model": model_name.replace("_", " ").title()}


# ---------------------------------------------------------------------------
# Step 3: the recommendation layer, one rule per feature
# ---------------------------------------------------------------------------
def recommendations(features: dict, at_risk: bool | None,
                    attendance_percent: float,
                    eligible: bool | None = None) -> list[str]:
    """Only the advice that applies to this particular student."""
    advice = []

    if attendance_percent < EXAM_ELIGIBILITY_PERCENT and eligible:
        advice.append(
            f"Your attendance is {attendance_percent:.0f}%, below the "
            f"{EXAM_ELIGIBILITY_PERCENT}% rule, but the administrator has "
            f"cleared you to sit the exam. Low attendance still affects your "
            f"result, so attend what remains.")
    elif attendance_percent < EXAM_ELIGIBILITY_PERCENT:
        short_by = EXAM_ELIGIBILITY_PERCENT - attendance_percent
        advice.append(
            f"Your attendance is {attendance_percent:.0f}%, which is "
            f"{short_by:.0f} points below the {EXAM_ELIGIBILITY_PERCENT}% "
            f"needed to sit the exam. Attend the remaining classes.")
    elif attendance_percent < 85:
        # The training data is blunt about this: risk stays high until
        # attendance clears roughly 85%, well above the 70% needed merely to
        # sit the exam. Saying so stops a good student wondering why they
        # were flagged.
        advice.append(
            f"Your attendance is {attendance_percent:.0f}%. That clears the "
            f"{EXAM_ELIGIBILITY_PERCENT}% needed to sit the exam, but students "
            f"below 85% attendance were still the most likely to struggle. "
            f"Raising your attendance is the single biggest change you can "
            f"make, it outweighs every other factor here.")

    rate = features.get("assignment_rate")
    if rate is not None and rate < 70:
        advice.append(
            f"Your assignment submission rate is {rate:.0f}%. Submitting the "
            f"outstanding work is the quickest way to improve your standing.")

    score = features.get("test_score")
    if score is not None and score < 20:
        advice.append(
            f"Your recent test score of {score:.0f} is weak. Ask your lecturer "
            f"about the topics you found difficult, or use available tutoring.")

    gpa = features.get("prior_gpa")
    if gpa is not None and gpa < 2.5:
        advice.append(
            f"Your previous GPA of {gpa:.2f} is low, so this semester matters "
            f"more than usual. Consider a study plan with your course adviser.")

    if at_risk:
        advice.append("The model classifies you as at risk of low performance. "
                      "Acting on the points above early is what changes the "
                      "outcome.")
    elif at_risk is False and not advice:
        advice.append("You are on track. Keep your attendance and submissions "
                      "where they are.")

    return advice


# ---------------------------------------------------------------------------
# The whole assessment in one call, in the order the chapters describe
# ---------------------------------------------------------------------------
def assess(attendance_percent: float, features: dict,
           model_name: str = DEPLOYED_MODEL,
           eligible_override: bool | None = None) -> dict:
    """
    Run the gate, then the model, then the rules.

    The model is deliberately NOT run for an ineligible student, exactly as
    the system flowchart specifies.
    """
    features = dict(features or {})
    features["attendance_rate"] = attendance_percent

    # The administrator can mark a student eligible in spite of the attendance
    # rule. When that happens the prediction must run for them, so the override
    # decides, not the raw percentage.
    eligible = (is_eligible(attendance_percent) if eligible_override is None
                else bool(eligible_override))
    result = {"eligible": eligible, "attendance_percent": attendance_percent,
              "at_risk": None, "probability": None, "provisional": False,
              "model": None, "model_missing": False}

    if eligible:
        prediction = predict(features, model_name)
        if prediction is None:
            result["model_missing"] = True
        else:
            result.update(prediction)

    result["advice"] = recommendations(features, result["at_risk"],
                                       attendance_percent, eligible)
    return result


# ---------------------------------------------------------------------------
# Running this file on its own prints three worked examples, so you can see
# the gate, the model, and the advice without opening the app.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    examples = [
        ("Low attendance, gate stops the model",
         52, {"prior_gpa": 3.4, "test_score": 28, "assignment_rate": 80}),
        ("Eligible but struggling",
         88, {"prior_gpa": 2.1, "test_score": 15, "assignment_rate": 45}),
        ("Eligible and doing well",
         95, {"prior_gpa": 3.7, "test_score": 30, "assignment_rate": 90}),
    ]

    if not available_models():
        print("No trained models found. Run:  python ml/train_models.py")
        raise SystemExit

    for title, attendance, features in examples:
        print("\n" + "=" * 62)
        print(title)
        print("=" * 62)
        result = assess(attendance, features)
        print(f"Attendance   : {attendance}%")
        print(f"Eligible     : {'yes' if result['eligible'] else 'no'}")
        if result["eligible"]:
            print(f"Prediction   : "
                  f"{'AT RISK' if result['at_risk'] else 'on track'} "
                  f"({result['probability']:.0%} probability, {result['model']})")
        else:
            print("Prediction   : not run, the eligibility rule stops here")
        print("Advice:")
        for line in result["advice"]:
            print("   -", line)