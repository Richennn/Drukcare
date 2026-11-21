# DrukCare — Medication Reminder and Daily Exercise Planner

Teal theme (same colours on every page and in all three apps) with the DrukCare logo (assets/logo.png). PRG304 Python GUI Programming project (B.Ed ICT 'C', Samtse College of Education).
Three Python apps share one set of local CSV files, so health data stays on your own computer.

| App | File | Role in the project | Command |
|---|---|---|---|
| **Tkinter** (desktop) | `tkinter_app.py` | Main app: login, medication CRUD, **pop-up + sound reminders with snooze** (background thread), exercise, prescriptions, analytics, profile | `python tkinter_app.py` |
| **Streamlit** (web) | `app.py` | Weekly analytics dashboard for patients and caregivers: all pages, charts, login + create-account validation | `python -m streamlit run app.py` |
| **Gradio** (web) | `gradio_app.py` | Prescription portal: enter, validate, save, **print** prescription summaries, add to schedule; quick medication / exercise / BMI tools | `python gradio_app.py` |

The three apps run independently (different ports: Streamlit 8501, Gradio 7860). The Tkinter app can also start the other two with the two buttons at the bottom of its sidebar and closes them when you quit.

## Folder structure

```
DrukCare/
├── app.py                 Streamlit web app
├── tkinter_app.py         Tkinter desktop app
├── gradio_app.py          Gradio prescription portal
├── requirements.txt       libraries to install
├── README.md              this file
├── assets/                YOUR PHOTOS GO HERE (see assets/README.txt)
│   └── icons/             optional small icons
├── data/                  created automatically: CSV files, backups/, profile_photos/, summaries/
└── drukcare_core/         code shared by all three apps (do not need to edit)
    ├── config.py          IMAGE PATHS + colours + ports   <-- edit image paths here
    ├── images.py          loads local images, placeholders, profile photos
    ├── storage.py         safe CSV storage: atomic writes, locks, daily backups, auto-restore
    ├── validators.py      all input validation rules
    ├── services.py        business logic (accounts, medication, exercise, prescriptions, analytics)
    └── seed.py            removes old demo accounts; --reset deletes all data
```

## Install on Windows (VS Code terminal)

1. Install Python 3.10+ from python.org (tick **"Add python.exe to PATH"**; keep **tcl/tk** ticked — that is Tkinter).
2. Open the `DrukCare` folder in VS Code, then **Terminal → New Terminal**.
3. ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   (If PowerShell blocks `activate`, run `Set-ExecutionPolicy -Scope Process Bypass` first.)
4. Run any app:
   ```
   python tkinter_app.py
   python -m streamlit run app.py
   python gradio_app.py
   ```

## Accounts and roles

Every account has a **CID** (Bhutanese Citizenship ID, 11 digits, unique). Log in with your **username or CID** and your password.

| Role | Uses | What they do |
|---|---|---|
| Patient | Desktop app (also Streamlit/Gradio) | Medicines, reminders, exercise, prescriptions, analytics; gets messages from their care team |
| Caregiver | Streamlit dashboard | **My Patients → View patient**: enter the patient's username + CID once, then see taken/missed doses, exercise and charts (read-only) and **send a care plan** |
| Provider | Streamlit + Gradio portal | Same as caregiver, plus prescriptions (only for linked patients) and printable summaries |

**Care plan:** a linked caregiver/provider picks medicines (dose, time, how often, days) and a daily exercise target (e.g. 60 minutes).
The medicines go straight into the patient's reminders, the exercise goal is updated and the patient gets a **message at once**
(pop-up with sound in the desktop app, bell + notice in Streamlit). Patients can remove anyone in **My Profile → Care Team**.

**Time zone:** all times are Bhutan time (Asia/Thimphu, UTC+6), also on servers such as Streamlit Cloud that run on UTC
(set in `drukcare_core/__init__.py`; change with the `DRUKCARE_TZ` environment variable).

## Medicine list (no typing)

Medicine names are picked from a dropdown of about 100 common medicines (`MEDICINE_DOSES` in `drukcare_core/config.py`).
Choosing a medicine fills in its usual dosage automatically, and dosage and time are dropdowns too.
In the desktop app, press a letter in the medicine box to jump to medicines starting with that letter.
To add a medicine, add one line to `MEDICINE_DOSES`, e.g. `"Cefixime 200 mg": "1 tablet",`.

## Adding your own photos

Put your pictures in the **`assets/`** folder using these names (jpg, jpeg, png, webp, bmp, gif):

| File | Size | Used for |
|---|---|---|
| `login_banner.jpg` | 1600×900 | login screen |
| `home_banner.jpg` (2448×864, shown whole on Home), `medication_banner.jpg`, `exercise_banner.jpg`, `prescriptions_banner.jpg`, `analytics_banner.jpg`, `profile_banner.jpg` | 1600×320 | page banners (also the Gradio header) |
| `banner_background.jpg` | 16:9 | teal dzong landscape behind every banner photo and the Home quote card |
| `proverb_banner.jpg` | 1600×200 | (not used any more) |
| `profile.jpg` | 400×400 | default profile photo |
| `logo.png` | 256×256 | logo (transparent PNG) |
| `mascot.png`, `sidebar_dragon.png`, `logo_sidebar.png`, `logo_full.png`, `waves.jpg`, `nav_*.jpg` | any | dragon doctor, sidebar dragon and logo, login logo, page-bottom wave, dashboard tile pictures |

Banners show the WHOLE photo in full colour on the right, blended into the teal dzong landscape (`banner_background.jpg`); the title sits on a frosted panel on the left. Pictures are never stretched. A missing or damaged image shows a clean placeholder instead of an error.

To use other file names or folders, edit the **IMAGE PATHS** block at the top of `drukcare_core/config.py`, e.g. `HOME_BANNER = "assets/my_dzong.jpg"`. Users can also replace their profile photo from inside the apps (My Profile → Change photo); it is saved in `data/profile_photos/`.

## Where data is saved

`data/*.csv` — one file per ERD entity: `user_account`, `care_link`, `message`, `prescription`, `prescription_item`, `medication`, `compliance_log`, `exercise_goal`, `exercise_log`; plus two small extra tables, `health_profile` (profile/settings) and `weight_log`. Daily copies go to `data/backups/YYYY-MM-DD/` (last 14 days). A damaged CSV is restored from the newest backup automatically.

## How the proposal maps to the code

* Login/sign-up + hashed passwords → `services.register_user / authenticate`
* Medication CRUD, High/Medium/Low priority colours → Tkinter + Streamlit Medication pages
* Reminder pop-up with sound, **Mark as taken**, **Snooze** → `ReminderWorker` thread + `queue` in `tkinter_app.py`
* Daily exercise targets and progress bars → Exercise pages
* Prescription portal, add to schedule, printable summary → `gradio_app.py` (also in Streamlit/Tkinter)
* Weekly adherence/exercise analytics with caregiver view → Streamlit Analytics (caregiver picks a patient, read-only)
* Safe storage (atomic writes, thread lock, daily backup) → `drukcare_core/storage.py`
* Out of scope (as in the proposal): wearables, SMS/e-mail refills. Nothing in DrukCare connects to hospitals, pharmacies or devices.

## Validation rules (as in the proposal presentation)

| Input | Rule |
|---|---|
| Time | `08:30`, `8:30 AM` or `20:15` |
| Medicine name, dosage | Cannot be empty (medicine chosen from the list) |
| Exercise numbers | Whole numbers above 0 |
| CID | Exactly 11 digits, unique |
| Username | 3–20 characters (a–z, 0–9, _) |
| Password | At least 6 characters |
| Prescription dosage | Must contain a number (e.g. `1 tablet`) |
| Prescription duration | 1–365 days |
| Delete | Confirmation required |

New records get readable ids: medicines `MED001`, `MED002` …, prescriptions `RX001`, `RX002` …

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named tkinter` | Re-run the Python installer → Modify → tick **tcl/tk and IDLE** |
| `No module named streamlit/gradio/...` | Activate the venv (`.venv\Scripts\activate`) and run `pip install -r requirements.txt` |
| `'streamlit' is not recognized` | Use `python -m streamlit run app.py` |
| Port already in use | Close the other copy, or change `STREAMLIT_PORT` / `GRADIO_PORT` in `drukcare_core/config.py` (Streamlit: add `--server.port 8600`) |
| "Data files are busy" | Another DrukCare app is saving; wait a second and retry. If it persists, delete `data/.drukcare.lock` |
| Photo not showing | Check the file is inside `assets/`, the name matches `config.py`, and it opens in Paint / Photos |
| No reminder pop-up | Log in as a patient in the desktop app, keep it open, and check My Profile → Notifications is on. Reminders appear for doses up to 90 minutes late |
| Want to wipe everything | Close all apps, delete the CSV files in `data/`, start an app again |

