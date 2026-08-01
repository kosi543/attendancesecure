# AttendanceSecure

A secure web-based QR code attendance monitoring system with machine-learning
based early-warning student performance prediction.

The attendance system is the foundation, and the prediction layer is now
connected on top of it. Logistic Regression and Random Forest are trained and
compared, the 70% eligibility rule runs before the model, and each dashboard
shows the result with rule-based recommendations.

---

## What it does

**Landing page**: the user first chooses who they are: Student, Lecturer, or
Administrator. Each role then has its own separate portal.

**Student**
- Register with full name, matric number, department, level, email, +234 phone.
- Log in with matric number + password.
- Scan attendance: share location, then photograph the lecturer's live QR with
  the in-app camera. Three checks run, the QR must be valid and unexpired
  (refreshes every 8 s), the device must be inside the lecturer's geofence, and
  the device fingerprint is captured. A scan from outside the zone (or with no
  location) is still recorded but flagged for the lecturer.
- View attendance % per course and 70% exam-eligibility status.
- Prediction & advice tab: enter GPA, recent test score and assignment rate
  once; attendance comes from your own scans. Shows eligible / not eligible,
  then at risk / on track with a probability, and only the advice that matches
  your own features. You can switch between the two models to compare them.

**Lecturer**
- Register / log in with email + password.
- Create courses.
- Start a live session, set the class zone with an adjustable radius slider,
  and capture the classroom GPS centre. A dynamic QR refreshes every 8 s and
  the session auto-closes after 5 minutes.
- Review flagged students (with the reason) and Confirm / Reject each.
- Semester report with eligibility.
- At-risk prediction tab: the flagged students for a course, at-risk first,
  with attendance, eligibility, probability and which model was used.

**Administrator**
- Log in with a secret access key + password (no public registration).
- System overview, manage departments, and look up any student (by matric) or
  lecturer (by email).
- Institution-wide prediction overview, plus an automatic notification each
  time a student is flagged as at risk.

---

## Project structure

```
attendancesecure/
├── app.py                     # entry point (run this)
├── config.py                  # all settings (name, colours, QR window, keys)
├── requirements.txt
├── .streamlit/config.toml     # theme
├── core/
│   ├── database.py            # Firebase, with a local JSON fallback
│   ├── auth.py                # register / login for the three roles
│   ├── attendance.py          # courses, sessions, eligibility, flagged review
│   ├── qr_engine.py           # dynamic, time-limited QR codes
│   ├── geofence.py            # Haversine distance / geofence check
│   ├── location.py            # real browser GPS capture
│   ├── fingerprint.py         # browser device fingerprint
│   └── ui.py                  # shared theme + small UI helpers
├── views/
│   ├── intro.py               # landing page (choose role)
│   ├── student.py
│   ├── lecturer.py
│   └── admin.py
└── ml/
    ├── train_models.py        # trains and compares the two models
    ├── predictor.py           # eligibility gate, prediction, recommendations
    ├── check_dataset.py       # sanity check on the training data
    ├── models/                # saved .joblib models (already included)
    └── results/               # graphs and model_results.csv
```

Each file is short and commented so it is easy to read and explain.

---

## How to run

If you already have the old project's libraries installed, you can just borrow
that environment: no reinstalling:

```bash
# borrow the old app's environment (adjust the path to yours)
source /c/Users/Admin/Downloads/chrisland_attendance/venv/Scripts/activate
cd /c/Users/Admin/Downloads/attendancesecure
streamlit run app.py --server.sslCertFile=cert.pem --server.sslKeyFile=key.pem
python -m streamlit run app.py
```

Or install fresh:

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

The app opens in your browser. Data is saved to a local `demo_database.json`
until you connect Firebase, so it runs with no setup.

**Admin login:** access key `AS-ADMIN-2026`, password `Asadmin@2026`
(change both in `config.py`).

---

## Connecting Firebase (optional)

The app uses Firebase Firestore if it finds a `firebase_credentials.json`
service-account file in this folder; otherwise it uses the local demo store.
To go live:

1. Create a Firebase project and enable Firestore.
2. Project settings → Service accounts → Generate new private key.
3. Rename the downloaded file to `firebase_credentials.json` and put it next to
   `app.py`.
4. Restart the app. The sidebar will read **Database: Firebase Firestore (live)**.

The collections (`users`, `courses`, `sessions`, `attendance`, `departments`)
are created automatically. Never commit `firebase_credentials.json` to GitHub.

---

## The prediction layer

### Running it

The trained models are already in `ml/models/`, so the app works straight away
with nothing to run. Only retrain if you change the datasets:

```bash
python ml/train_models.py
```

That prints the results table, writes the graphs to `ml/results/`, and saves
the models. Both `.xlsx` datasets must sit beside `app.py`.

Your old project used scikit-learn for Isolation Forest, so borrowing that same
environment already gives you everything this needs. If `import sklearn` fails,
that one package is the only thing missing.

### How it runs, in order

1. **Eligibility gate**, a fixed rule: attendance against the 70% threshold. A
   student below it is told how far short they are, and the model is not run
   for them at all.
2. **Prediction**: for an eligible student, Logistic Regression or Random
   Forest returns at risk or on track, with a probability.
3. **Recommendations**, fixed rules: each rule reads one feature, so two
   students who are both flagged can get different advice.

### The two datasets

They have different columns and cannot be merged, so they run as two separate
experiments, which doubles as a check that the approach is not tied to one
source.

| | Dataset A | Dataset B |
|---|---|---|
| File | `3_student_performance.xlsx` | `1_student_performance.xlsx` |
| Rows | 1,439 | 3,016 |
| Features | prior GPA, test score, attendance rate, assignment rate | study hours, attendance %, participation rate |
| Label | risk_level, High or Low | grade D or F counted as at risk |

The app itself uses the Dataset A models, because those four features are the
ones Chapter 3 declares.

### Two things to know about the results

Run `python ml/check_dataset.py` to see both for yourself.

**Dataset A's near-perfect scores are a property of the data, not the models.**
Its `risk_level` column was produced by a threshold rule, and a decision tree of
depth 2 reproduces the label exactly. Both models are recovering a formula
rather than learning from observed outcomes. Report it as such.

**Dataset B is imbalanced**, with only 4.7% of students at risk. A model that
predicts "nobody is at risk" every time scores 0.954 accuracy, beating the
trained Random Forest. This is why precision, recall and F1 are reported
alongside accuracy, and why recall matters most here: missing a struggling
student is worse than a false alarm.

## Testing on a phone (location and camera permissions)

Browsers only allow GPS and the camera on a **secure context**: an `https://`
page, or `http://localhost` on the same machine. When a phone opens the app on
the laptop's LAN address (`http://192.168.x.x:8501`) the browser blocks both
**silently**, with no allow/deny popup. The app now detects this and says so on
the scan, location and camera screens.

To test on a real phone, use one of these:

* an https tunnel, e.g. `ngrok http 8501` or `npx localtunnel --port 8501`,
  then open the https link on the phone
* deploy to Streamlit Community Cloud (https by default)
* run Streamlit with a self-signed certificate:

```
streamlit run app.py --server.sslCertFile=cert.pem --server.sslKeyFile=key.pem
```

## Upgrading an existing database

If you already have `demo_database.json` from an earlier version, run this once
so old courses and enrolments pick up their department and lecturer:

```
python migrate_data.py
```
