# Machine learning layer

## How to run

```
pip install -r requirements.txt
python ml/train_models.py
```

Both `.xlsx` datasets must sit in the same folder as `app.py`.
The script prints a results table, writes graphs to `ml/results/`, and saves
the trained models to `ml/models/`.

## What it does

Trains and compares two models on two independent datasets:

* **Logistic Regression** — linear, interpretable, inputs standardised first
* **Random Forest** — 200 trees, depth 8, non-linear

Both use `class_weight="balanced"` because at-risk students are the minority
class, and 5-fold cross validation so no single train/test split decides the
result.

## Results as they stand

| Dataset | Model | Accuracy | Precision | Recall | F1 | ROC AUC |
|---|---|---|---|---|---|---|
| A (1,439) | Logistic Regression | 0.990 | 0.994 | 0.988 | 0.991 | 1.000 |
| A (1,439) | Random Forest | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| B (3,016) | Logistic Regression | 0.866 | 0.232 | 0.821 | 0.362 | 0.943 |
| B (3,016) | Random Forest | 0.917 | 0.310 | 0.643 | 0.419 | 0.922 |

## Two problems with these numbers, and they must be disclosed

**1. Dataset A's label is a formula, not an observation.**
A decision tree of depth 2 reproduces `risk_level` exactly:

```
attendance_rate <= 84.5            -> High risk
else prior_gpa  <= 2.75            -> High risk
else                                  Low risk
```

Two lines of if-statements score 100% on this dataset. The models are not
predicting anything, they are recovering the rule the label was written with.
That is why `test_score` and `assignment_submission_rate` show 0.004
importance: they were never part of the rule.

**2. Dataset B's accuracy is inflated by class imbalance.**
Only 4.7% of the rows are at risk. A model that predicts "nobody is at risk"
for every single student scores **95.3% accuracy** and is worthless. The
Random Forest scores 91.7%, which is *lower*, yet far more useful because it
actually catches 64% of the students who are struggling.

This is why accuracy is not reported on its own here. Precision, recall, F1
and ROC AUC are what the comparison rests on.

**Leakage removed:** `total_score` is not used as a feature for Dataset B.
The grade is calculated directly from it (D is 40-55, F is below 40), so
including it would hand the model the answer.
