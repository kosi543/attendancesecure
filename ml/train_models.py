"""
ml/train_models.py
==================
Trains and compares the two models used in this project:

    * Logistic Regression  (linear, interpretable baseline)
    * Random Forest        (non-linear ensemble)

Both are trained on two independent external datasets, because the datasets
have different columns and cannot be merged:

    Dataset A (primary)   3_student_performance.xlsx   1,439 rows
        Previous GPA, Test_score, attendance_rate(%),
        assignment_submission_rate(%)          ->  risk_level (High / Low)

    Dataset B (secondary) 1_student_performance.xlsx   3,016 rows
        study_hours, attendance_percentage,
        participation_rate                     ->  grade D or F = at risk

Run it with:

    python ml/train_models.py

It prints a results table, saves the trained models to ml/models/, and writes
every graph to ml/results/.
"""

import os
import warnings

import matplotlib
matplotlib.use("Agg")            # save figures to file, no desktop window needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, roc_curve,
                             confusion_matrix, classification_report)
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")     # keep the output clean

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(HERE)          # datasets sit beside the app folder
RESULTS = os.path.join(HERE, "results")
MODELS = os.path.join(HERE, "models")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(MODELS, exist_ok=True)

RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Loading the two datasets
# ---------------------------------------------------------------------------
def load_dataset_a(path):
    """
    Primary dataset. The label is already given as risk_level, so we simply
    turn it into 1 = at risk, 0 = not at risk.
    """
    df = pd.read_excel(path)
    df = df.dropna()
    X = df[["Previous GPA", "Test_score", "attendance_rate(%)",
            "assignment_submission_rate(%)"]]
    X.columns = ["prior_gpa", "test_score", "attendance_rate",
                 "assignment_rate"]
    y = (df["risk_level"] == "High").astype(int)
    return X, y


def load_dataset_b(path):
    """
    Secondary dataset. A student is treated as at risk if the final grade is
    D or F.

    total_score is deliberately NOT used as a feature. The grade is worked out
    directly from total_score (D is 40-55, F is below 40), so feeding it to the
    model would be feeding it the answer. That produces a near-perfect score
    that means nothing, which is known as label leakage.
    """
    df = pd.read_excel(path)
    df = df.dropna()
    X = df[["study_hours", "attendance_percentage", "participation_rate"]]
    y = df["grade"].isin(["D", "F"]).astype(int)
    return X, y


# ---------------------------------------------------------------------------
# The two models
# ---------------------------------------------------------------------------
def build_models():
    """
    Logistic Regression needs its inputs on the same scale, so it is wrapped
    in a pipeline with a StandardScaler. Random Forest does not need scaling.

    class_weight='balanced' matters when one class is much rarer than the
    other: without it a model can score well simply by always predicting the
    majority class and never spotting a struggling student.
    """
    logistic = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000,
                                     class_weight="balanced",
                                     random_state=RANDOM_STATE)),
    ])

    forest = RandomForestClassifier(n_estimators=200,
                                    max_depth=8,
                                    min_samples_leaf=5,
                                    class_weight="balanced",
                                    random_state=RANDOM_STATE)
    return {"Logistic Regression": logistic, "Random Forest": forest}


# ---------------------------------------------------------------------------
# Training and scoring one dataset
# ---------------------------------------------------------------------------
def evaluate(name, X, y, tag):
    """Train both models on one dataset and return a table of their scores."""
    print("\n" + "=" * 70)
    print(f"{name}   ({len(X)} rows, {X.shape[1]} features)")
    print(f"At risk: {int(y.sum())}   Not at risk: {int((1 - y).sum())} "
          f"({y.mean() * 100:.1f}% of the data is at risk)")
    print("=" * 70)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    rows, fitted = [], {}

    for model_name, model in build_models().items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        proba = model.predict_proba(X_test)[:, 1]

        # 5-fold cross validation, so the score does not depend on one lucky split
        cv_scores = cross_val_score(model, X, y, cv=cv, scoring="f1")

        rows.append({
            "Dataset": tag,
            "Model": model_name,
            "Accuracy": accuracy_score(y_test, pred),
            "Precision": precision_score(y_test, pred, zero_division=0),
            "Recall": recall_score(y_test, pred, zero_division=0),
            "F1": f1_score(y_test, pred, zero_division=0),
            "ROC AUC": roc_auc_score(y_test, proba),
            "CV F1 (mean)": cv_scores.mean(),
            "CV F1 (std)": cv_scores.std(),
        })
        fitted[model_name] = model

        print(f"\n--- {model_name} ---")
        print(classification_report(y_test, pred,
                                    target_names=["Not at risk", "At risk"],
                                    zero_division=0))

    results = pd.DataFrame(rows)
    plot_confusion(fitted, X_test, y_test, tag)
    plot_roc(fitted, X_test, y_test, tag)
    plot_importance(fitted, X, tag)

    # keep the models so the app can load them later
    for model_name, model in fitted.items():
        fname = f"{tag}_{model_name.lower().replace(' ', '_')}.joblib"
        dump(model, os.path.join(MODELS, fname))

    return results, fitted


# ---------------------------------------------------------------------------
# Graphs
# ---------------------------------------------------------------------------
def plot_confusion(fitted, X_test, y_test, tag):
    """Where each model gets it right, and what kind of mistake it makes."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, (name, model) in zip(axes, fitted.items()):
        cm = confusion_matrix(y_test, model.predict(X_test))
        ax.imshow(cm, cmap="Blues")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, cm[i, j], ha="center", va="center",
                        color="black", fontsize=13)
        ax.set_title(name)
        ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
        ax.set_xticks([0, 1], ["Not at risk", "At risk"])
        ax.set_yticks([0, 1], ["Not at risk", "At risk"])
    fig.suptitle(f"Confusion matrices, {tag}")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, f"{tag}_confusion.png"), dpi=120)
    plt.close(fig)


def plot_roc(fitted, X_test, y_test, tag):
    """ROC curve: how well each model separates the two groups."""
    fig, ax = plt.subplots(figsize=(6, 5))
    for name, model in fitted.items():
        proba = model.predict_proba(X_test)[:, 1]
        fpr, tpr, _ = roc_curve(y_test, proba)
        ax.plot(fpr, tpr, label=f"{name} (AUC {roc_auc_score(y_test, proba):.3f})")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="Random guess")
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.set_title(f"ROC curve, {tag}"); ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, f"{tag}_roc.png"), dpi=120)
    plt.close(fig)


def plot_importance(fitted, X, tag):
    """
    Which features the models actually lean on. This is the graph that answers
    'does attendance really predict performance?' for this dataset.
    """
    forest = fitted["Random Forest"]
    importances = pd.Series(forest.feature_importances_,
                            index=X.columns).sort_values()

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(importances.index, importances.values, color="#D6336C")
    ax.set_xlabel("Importance")
    ax.set_title(f"Random Forest feature importance, {tag}")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, f"{tag}_importance.png"), dpi=120)
    plt.close(fig)

    print("\nFeature importance (Random Forest):")
    for feature, value in importances.sort_values(ascending=False).items():
        print(f"   {feature:<22} {value:.3f}")


def plot_comparison(all_results):
    """One bar chart comparing both models across both datasets."""
    fig, ax = plt.subplots(figsize=(9, 5))
    metrics = ["Accuracy", "Precision", "Recall", "F1"]
    labels = [f"{r['Model']}\n{r['Dataset']}" for _, r in all_results.iterrows()]
    x = np.arange(len(labels))
    width = 0.2
    for i, metric in enumerate(metrics):
        ax.bar(x + i * width, all_results[metric], width, label=metric)
    ax.set_xticks(x + width * 1.5, labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title("Logistic Regression vs Random Forest")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "model_comparison.png"), dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    a_path = os.path.join(DATA, "3_student_performance.xlsx")
    b_path = os.path.join(DATA, "1_student_performance.xlsx")

    Xa, ya = load_dataset_a(a_path)
    res_a, _ = evaluate("Dataset A, primary", Xa, ya, "dataset_a")

    Xb, yb = load_dataset_b(b_path)
    res_b, _ = evaluate("Dataset B, secondary", Xb, yb, "dataset_b")

    all_results = pd.concat([res_a, res_b], ignore_index=True)
    plot_comparison(all_results)
    all_results.to_csv(os.path.join(RESULTS, "model_results.csv"), index=False)

    print("\n" + "=" * 70)
    print("FINAL COMPARISON")
    print("=" * 70)
    print(all_results.round(3).to_string(index=False))
    print(f"\nGraphs saved to {RESULTS}")
    print(f"Models saved to {MODELS}")


if __name__ == "__main__":
    main()
