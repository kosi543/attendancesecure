"""
ml/check_dataset.py
===================
A sanity check on the training data, before trusting any accuracy figure.

The idea is simple. If a plain hand-written if-statement can score as well as
a trained model, then the model has not learned anything: the label was built
from the features by a rule, and both are just repeating that rule back.

Run it with:   python ml/check_dataset.py
"""

import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text

print("=" * 66)
print("DATASET A  (3_student_performance.xlsx)")
print("=" * 66)

df = pd.read_excel("3_student_performance.xlsx")
y = (df["risk_level"] == "High").astype(int)

# ---- Test 1: can one if-statement reproduce the label? --------------------
rule = ((df["attendance_rate(%)"] <= 84.5) | (df["Previous GPA"] <= 2.75)).astype(int)
print(f"\n1. Hand-written rule, no machine learning at all:")
print(f"   'attendance <= 84.5  OR  GPA <= 2.75  ->  High risk'")
print(f"   Agreement with the risk_level column: {(rule == y).mean() * 100:.2f}%")

# ---- Test 2: how deep must a tree go before it is perfect? ---------------
X = df[["Previous GPA", "Test_score", "attendance_rate(%)",
        "assignment_submission_rate(%)"]]
X.columns = ["prior_gpa", "test_score", "attendance_rate", "assignment_rate"]
print("\n2. Decision tree accuracy by depth:")
for depth in (1, 2, 3, 4):
    tree = DecisionTreeClassifier(max_depth=depth, random_state=0).fit(X, y)
    print(f"   depth {depth}: {tree.score(X, y) * 100:.2f}%")
print("   (real data does not become perfect at depth 2)")

# ---- Test 3: is there any contradiction anywhere in the data? ------------
# In real data, two students with identical scores sometimes end up different.
# If that never happens, the label is a formula, not an observation.
dupes = df.duplicated(subset=list(df.columns[1:-1]), keep=False)
conflict = 0
if dupes.any():
    grouped = df[dupes].groupby(list(df.columns[1:-1]))["risk_level"].nunique()
    conflict = int((grouped > 1).sum())
print(f"\n3. Students with identical features but different risk labels: {conflict}")
print("   (real data always has some; zero means the label is calculated)")

print("\n" + "=" * 66)
print("DATASET B  (1_student_performance.xlsx)")
print("=" * 66)

db = pd.read_excel("1_student_performance.xlsx")
yb = db["grade"].isin(["D", "F"]).astype(int)
print(f"\n1. Grade boundaries against total_score:")
print(db.groupby("grade")["total_score"].agg(["min", "max"]).to_string())
print("   grade is calculated from total_score, so total_score cannot be a feature")

print(f"\n2. Class balance: {int(yb.sum())} at risk out of {len(yb)} "
      f"({yb.mean() * 100:.1f}%)")
print("   a model that always says 'not at risk' would already score "
      f"{(1 - yb.mean()) * 100:.1f}% accuracy")

print("\n3. Correlation with being at risk:")
for col in ["study_hours", "attendance_percentage", "participation_rate"]:
    print(f"   {col:<24} {db[col].corr(yb):+.3f}")
