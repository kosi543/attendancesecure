"""
ml/compare_models.py
====================
For YOUR testing, not for students.

The application shows one answer from one model. This script is where you can
see both models side by side and satisfy yourself that the right one was
deployed. Two things happen:

    1. It prints the scores both models earned during training.
    2. It lets you type a student's figures and shows what each model says
       about that same student.

Run it with:

    python ml/compare_models.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml import predictor

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results", "model_results.csv")


def show_scores():
    """The table produced by train_models.py."""
    if not os.path.exists(RESULTS):
        print("No results yet. Run:  python ml/train_models.py")
        return
    table = pd.read_csv(RESULTS)
    print("\nHow the two models scored during training")
    print("-" * 78)
    print(table.round(3).to_string(index=False))
    print("""
Reading this table:
  Accuracy   of everyone, how many were labelled correctly
  Precision  when the model says 'at risk', how often it is right
  Recall     of the students really heading for failure, how many were caught
  F1         one number balancing precision and recall

Dataset A scores near 1.00 because its risk column was written by a formula,
not observed from students. Dataset B is the honest one.

The system deploys Logistic Regression because on dataset B it caught 82% of
the students genuinely at risk, against Random Forest's 64%. A missed student
costs more than a false alarm.""")


def ask(label, default):
    """Ask for a number. Enter keeps the default, anything odd is re-asked."""
    while True:
        answer = input(f"{label} [{default}]: ").strip()
        if not answer:
            return float(default)
        try:
            return float(answer)
        except ValueError:
            print("   Please type a number, or press Enter for the default.")


def compare_one_student():
    print("\nEnter one student's figures, or press Enter to accept each default.")
    attendance = ask("Attendance %", 88)
    assignments = ask("Assignment submission %", 45)
    test_score = ask("Recent test score out of 100", 15)
    gpa = ask("Previous GPA out of 5", 2.1)

    features = {"prior_gpa": gpa, "test_score": test_score,
                "assignment_rate": assignments}

    print("\n" + "-" * 78)
    print(f"Attendance {attendance:.0f}%   assignments {assignments:.0f}%   "
          f"test {test_score:.0f}   GPA {gpa:.2f}")
    print("-" * 78)

    for name in ("logistic_regression", "random_forest"):
        result = predictor.assess(attendance, features, model_name=name)
        deployed = " (deployed)" if name == predictor.DEPLOYED_MODEL else ""
        label = name.replace("_", " ").title() + deployed

        if not result["eligible"]:
            print(f"{label:<32} not eligible, the model is not run")
        else:
            verdict = "AT RISK" if result["at_risk"] else "on track"
            print(f"{label:<32} {verdict:<9} "
                  f"{result['probability']:.0%} chance of failing")

    print("\nAdvice the student would see:")
    for line in predictor.assess(attendance, features)["advice"]:
        print("   -", line)


if __name__ == "__main__":
    show_scores()
    if not predictor.available_models():
        print("\nNo trained models found. Run:  python ml/train_models.py")
        raise SystemExit
    while True:
        compare_one_student()
        if input("\nTry another student? (y/n): ").strip().lower() != "y":
            break
