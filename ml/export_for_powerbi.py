"""
ml/export_for_powerbi.py
========================
Writes clean CSV files that Power BI can open directly, so the analysis in
Chapter 4 is done on exactly the same data the models were trained on.

Run it with:

    python ml/export_for_powerbi.py

Four files appear in ml/powerbi/:

    dataset_a_clean.csv    the primary dataset, with banded columns for charts
    dataset_b_clean.csv    the secondary dataset, same treatment
    combined_attendance.csv  attendance and risk from both, stacked, so the two
                             can be compared on one chart
    model_results.csv        the scores both models earned

In Power BI: Get Data, Text/CSV, pick the file, Load.
"""

import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
OUT = os.path.join(HERE, "powerbi")
os.makedirs(OUT, exist_ok=True)


def band(series, edges, labels):
    """Group a numeric column into readable bands, which charts far better
    than a raw percentage."""
    return pd.cut(series, edges, labels=labels, include_lowest=True)


def main():
    # ---- Dataset A -------------------------------------------------------
    a = pd.read_excel(os.path.join(APP, "3_student_performance.xlsx")).dropna()
    a = a.rename(columns={"Previous GPA": "prior_gpa",
                          "Test_score": "test_score",
                          "attendance_rate(%)": "attendance_rate",
                          "assignment_submission_rate(%)": "assignment_rate"})
    a["at_risk"] = (a["risk_level"] == "High").astype(int)
    a["risk_label"] = a["risk_level"].map({"High": "At risk", "Low": "Not at risk"})
    a["attendance_band"] = band(a["attendance_rate"], [0, 50, 70, 85, 100],
                                ["Below 50%", "50-70%", "70-85%", "Above 85%"])
    a["gpa_band"] = band(a["prior_gpa"], [0, 2.0, 2.5, 3.5, 5.0],
                         ["Below 2.0", "2.0-2.5", "2.5-3.5", "Above 3.5"])
    a["meets_70_rule"] = a["attendance_rate"].ge(70).map({True: "Eligible",
                                                          False: "Not eligible"})
    a["dataset"] = "A (primary)"
    a.to_csv(os.path.join(OUT, "dataset_a_clean.csv"), index=False)

    # ---- Dataset B -------------------------------------------------------
    b = pd.read_excel(os.path.join(APP, "1_student_performance.xlsx")).dropna()
    b["at_risk"] = b["grade"].isin(["D", "F"]).astype(int)
    b["risk_label"] = b["at_risk"].map({1: "At risk", 0: "Not at risk"})
    b["attendance_band"] = band(b["attendance_percentage"], [0, 50, 70, 85, 100],
                                ["Below 50%", "50-70%", "70-85%", "Above 85%"])
    b["study_band"] = band(b["study_hours"], [0, 10, 20, 30, 100],
                           ["Under 10h", "10-20h", "20-30h", "Over 30h"])
    b["meets_70_rule"] = b["attendance_percentage"].ge(70).map(
        {True: "Eligible", False: "Not eligible"})
    b["dataset"] = "B (secondary)"
    b.to_csv(os.path.join(OUT, "dataset_b_clean.csv"), index=False)

    # ---- both stacked, so one chart can compare them ---------------------
    combined = pd.concat([
        a[["dataset", "attendance_rate", "attendance_band", "risk_label", "at_risk"]],
        b[["dataset", "attendance_percentage", "attendance_band", "risk_label",
           "at_risk"]].rename(columns={"attendance_percentage": "attendance_rate"}),
    ], ignore_index=True)
    combined.to_csv(os.path.join(OUT, "combined_attendance.csv"), index=False)

    # ---- the model scores ------------------------------------------------
    scores = os.path.join(HERE, "results", "model_results.csv")
    if os.path.exists(scores):
        pd.read_csv(scores).to_csv(os.path.join(OUT, "model_results.csv"),
                                   index=False)

    print(f"Written to {OUT}")
    for f in sorted(os.listdir(OUT)):
        print("   ", f)

    print("""
Charts worth building in Power BI:

  1. Pie: risk_label, share of students at risk in each dataset
  2. Bar: attendance_band on the axis, count of at-risk students as the value
     This is the one that shows attendance and risk moving together in
     dataset A, and barely moving at all in dataset B.
  3. Bar: study_band against at-risk count, dataset B only. Study hours is
     the feature that actually carries that dataset.
  4. Bar: model_results, Recall by Model, filtered to dataset B. This is the
     chart that justifies deploying Logistic Regression.
  5. Card: count of 'Not eligible' from meets_70_rule, which ties the analysis
     back to the 70% rule in the attendance system.""")


if __name__ == "__main__":
    main()
