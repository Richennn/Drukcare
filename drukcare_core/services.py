"""DrukCare business logic (no screens here).

All three apps call these functions, so a medicine added in Tkinter shows up
in Streamlit and Gradio, and every form is validated in exactly one place.
"""
import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta

from . import config
from . import storage as st
from .validators import (ValidationError, clean_text, validate_choice, validate_date,
                         validate_email, validate_full_name, validate_number,
                         validate_password, validate_phone, validate_time,
                         validate_username, validate_cid, time_label)

ROLES = ("Patient", "Caregiver", "Provider")
def validate_medicine(name, label="Medicine name"):
    """Return the correctly spelled name from config.MEDICINES, or raise ValidationError."""
    n = str(name or "").strip().lower()
    for m in config.MEDICINES:
        if m.lower() == n:
            return m
    raise ValidationError(f"{label}: please choose a medicine from the list.")


def validate_rx_dosage(value, label="Dosage"):
    """Prescription dosage: not empty and must contain a number, e.g. '1 tablet' or '5 ml'."""
    text = clean_text(value, label, 1, 50)
    if not any(ch.isdigit() for ch in text):
        raise ValidationError(f"{label} must contain a number, e.g. 1 tablet or 5 ml.")
    return text


FREQUENCIES = ("Once daily", "Twice daily", "Three times daily")
PRIORITIES = ("High", "Medium", "Low")
GOAL_TYPES = ("Steps", "Minutes", "Distance")          # Distance is stored in metres
ACTIVITY_TYPES = ("Walking", "Running", "Hiking", "Cycling", "Yoga", "Stretching", "Other")
BLOOD_TYPES = ("", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
GENDERS = ("", "Female", "Male", "Other", "Prefer not to say")
DEFAULT_GOALS = {"Steps": 6000, "Minutes": 60, "Distance": 5000}
PBKDF2_ROUNDS = 200_000


# =================================================================== accounts
def hash_password(password: str, salt: str = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    try:
        digest, _ = hash_password(password, salt)
    except ValueError:
        return False
    return hmac.compare_digest(digest, stored_hash)


def public_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k not in ("Password_Hash", "Salt")}


def get_user(user_id: str):
    for u in st.read_table("user_account"):
        if u["User_ID"] == user_id:
            return u
    return None


def find_user(username: str):
    username = str(username or "").strip().lower()
    for u in st.read_table("user_account"):
        if u["Username"] == username:
            return u
    return None


def find_user_by_cid(cid):
    try:
        cid = validate_cid(cid)
    except ValidationError:
        return None
    for u in st.read_table("user_account"):
        if u["CID"] == cid:
            return u
    return None


def register_user(full_name, username, password, confirm=None, role="Patient", dob="", phone="", cid=""):
    """Create an account. Raises ValidationError with a friendly message."""
    full_name = validate_full_name(full_name)
    cid = validate_cid(cid)
    username = validate_username(username)
    password = validate_password(password)
    if confirm is not None and password != confirm:
        raise ValidationError("Passwords do not match.")
    role = validate_choice(role, "Role", ROLES)
    dob = validate_date(dob, "Date of birth", required=False, allow_future=False)
    phone = validate_phone(phone)
    with st.locked():
        if find_user(username):
            raise ValidationError("That username is already taken. Please choose another.")
        if find_user_by_cid(cid):
            raise ValidationError("An account with this CID already exists. Please log in instead.")
        pw_hash, salt = hash_password(password)
        user = {"User_ID": st.new_id(), "Full_Name": full_name, "CID": cid, "Role": role,
                "Date_of_Birth": dob, "Phone": phone, "Created_On": st.today_str(),
                "Username": username, "Password_Hash": pw_hash, "Salt": salt}
        st.insert("user_account", user)
        if role == "Patient":
            ensure_goals(user["User_ID"])
    return public_user(user)


def authenticate(username_or_cid, password) -> dict:
    """Log in with the username OR the 11-digit CID, plus the password."""
    if not str(username_or_cid or "").strip() or not password:
        raise ValidationError("Please enter your username (or CID) and password.")
    text = str(username_or_cid).strip()
    user = find_user_by_cid(text) if text.replace(" ", "").replace("-", "").isdigit() else find_user(text)
    if not user or not verify_password(password, user["Password_Hash"], user["Salt"]):
        raise ValidationError("Invalid username/CID or password.")
    return public_user(user)


def update_cid(user_id, cid):
    """Add or change the CID (accounts made before CID existed can add it in My Profile)."""
    cid = validate_cid(cid)
    with st.locked():
        other = find_user_by_cid(cid)
        if other and other["User_ID"] != user_id:
            raise ValidationError("Another account already uses this CID.")
        st.update_where("user_account", lambda r: r["User_ID"] == user_id, {"CID": cid})
    return cid


def update_user(user_id, full_name, dob="", phone=""):
    full_name = validate_full_name(full_name)
    dob = validate_date(dob, "Date of birth", required=False, allow_future=False)
    phone = validate_phone(phone)
    st.update_where("user_account", lambda r: r["User_ID"] == user_id,
                    {"Full_Name": full_name, "Date_of_Birth": dob, "Phone": phone})


def change_password(user_id, old_password, new_password):
    user = get_user(user_id)
    if not user or not verify_password(old_password, user["Password_Hash"], user["Salt"]):
        raise ValidationError("Current password is incorrect.")
    new_password = validate_password(new_password)
    pw_hash, salt = hash_password(new_password)
    st.update_where("user_account", lambda r: r["User_ID"] == user_id,
                    {"Password_Hash": pw_hash, "Salt": salt})


# =================================================================== care team (linking)
# A caregiver or provider types the patient's USERNAME + CID once ("View patient").
# If both match, a CARE_LINK row is saved and the patient appears in their "My Patients" list:
# they can then see the patient's doses (taken / missed), exercise and analytics (read-only),
# and send a care plan.  The patient can remove the link from My Profile.
CARER_ROLES = ("Caregiver", "Provider")


def link_patient(carer_id, patient_username, patient_cid) -> dict:
    carer = get_user(carer_id)
    if not carer or carer["Role"] not in CARER_ROLES:
        raise ValidationError("Only caregiver and provider accounts can view a patient.")
    if not str(patient_username or "").strip():
        raise ValidationError("Please enter the patient's username.")
    cid = validate_cid(patient_cid)
    patient = find_user(patient_username)
    # one message for every mismatch, so nobody can guess which part was wrong
    if not patient or patient["Role"] != "Patient" or patient["CID"] != cid:
        raise ValidationError("No patient found with that username and CID. Please check both.")
    with st.locked():
        for link in st.read_table("care_link"):
            if link["Caregiver_ID"] == carer_id and link["Patient_ID"] == patient["User_ID"]:
                return public_user(patient)          # already linked - just open them
        st.insert("care_link", {"Link_ID": st.new_id(), "Caregiver_ID": carer_id,
                                "Patient_ID": patient["User_ID"], "Linked_On": st.today_str()})
    add_message(patient["User_ID"], carer_id, f"{carer['Full_Name']} can now follow your progress",
                f"{carer['Full_Name']} ({carer['Role'].lower()}) entered your username and CID and can now see "
                f"your medicines, doses and exercise. You can remove them in My Profile → Care team.")
    return public_user(patient)


def unlink(link_id, user_id):
    """Remove a link. Only the caregiver/provider or the patient of that link may do it."""
    if not st.delete_where("care_link", lambda r: r["Link_ID"] == link_id
                           and user_id in (r["Caregiver_ID"], r["Patient_ID"])):
        raise ValidationError("That link no longer exists.")


def linked_patients(carer_id) -> list:
    """Patients a caregiver / provider has linked (each row also has Link_ID)."""
    users = {u["User_ID"]: u for u in st.read_table("user_account")}
    out = []
    for link in st.read_table("care_link"):
        if link["Caregiver_ID"] == carer_id and link["Patient_ID"] in users:
            out.append(dict(public_user(users[link["Patient_ID"]]), Link_ID=link["Link_ID"], Linked_On=link["Linked_On"]))
    return sorted(out, key=lambda u: u["Full_Name"].lower())


def care_team(patient_id) -> list:
    """Caregivers and providers who can see this patient (each row also has Link_ID)."""
    users = {u["User_ID"]: u for u in st.read_table("user_account")}
    out = []
    for link in st.read_table("care_link"):
        if link["Patient_ID"] == patient_id and link["Caregiver_ID"] in users:
            out.append(dict(public_user(users[link["Caregiver_ID"]]), Link_ID=link["Link_ID"], Linked_On=link["Linked_On"]))
    return out


def is_linked(carer_id, patient_id) -> bool:
    return any(l["Caregiver_ID"] == carer_id and l["Patient_ID"] == patient_id for l in st.read_table("care_link"))


def can_view(viewer_id, patient_id) -> bool:
    return viewer_id == patient_id or is_linked(viewer_id, patient_id)


def patient_choices(carer_id) -> list:
    """Labels for drop-downs of a carer's linked patients: 'Sonam Pemo (somwang)'."""
    return [f"{p['Full_Name']} ({p['Username']})" for p in linked_patients(carer_id)]


def patient_from_choice(choice, carer_id=None):
    """Turn 'Sonam Pemo (somwang)' back into the patient (must be linked when carer_id is given)."""
    text = str(choice or "").strip()
    if text.endswith(")") and "(" in text:
        text = text[text.rindex("(") + 1:-1]
    user = find_user(text)
    if not user or user["Role"] != "Patient":
        raise ValidationError("Please choose a patient from the list.")
    if carer_id and not is_linked(carer_id, user["User_ID"]):
        raise ValidationError("Link this patient first (View patient: username + CID).")
    return public_user(user)


def patients_of_provider(provider_id) -> list:
    """Linked patients plus anyone the provider has prescribed for (for the provider's stat card)."""
    out = linked_patients(provider_id)
    seen = {p["User_ID"] for p in out}
    users = {u["User_ID"]: u for u in st.read_table("user_account")}
    for rx in st.read_table("prescription"):
        if rx["Provider_ID"] == provider_id and rx["Patient_ID"] in users and rx["Patient_ID"] not in seen:
            seen.add(rx["Patient_ID"])
            out.append(public_user(users[rx["Patient_ID"]]))
    return out


# =================================================================== messages
def add_message(patient_id, sender_id, title, body=""):
    st.insert("message", {"Msg_ID": st.new_id(), "Patient_ID": patient_id, "Sender_ID": sender_id,
                          "Sent_At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Title": title[:120],
                          "Body": body[:1500], "Is_Read": "False"})


def messages_for(patient_id, unread_only=False) -> list:
    users = {u["User_ID"]: u for u in st.read_table("user_account")}
    rows = [(m["Sent_At"], k, dict(m, Sender_Name=users.get(m["Sender_ID"], {}).get("Full_Name", "DrukCare"),
                                   Sender_Role=users.get(m["Sender_ID"], {}).get("Role", "")))
            for k, m in enumerate(st.read_table("message"))
            if m["Patient_ID"] == patient_id and (not unread_only or not st.to_bool(m["Is_Read"]))]
    return [r for _, _, r in sorted(rows, key=lambda x: (x[0], x[1]), reverse=True)]   # newest first


def mark_messages_read(patient_id, msg_ids=None):
    st.update_where("message", lambda r: r["Patient_ID"] == patient_id and (msg_ids is None or r["Msg_ID"] in msg_ids),
                    {"Is_Read": "True"})


# =================================================================== care plans
def send_care_plan(sender_id, patient_id, medicines=(), exercise_minutes=None, note="") -> dict:
    """A linked caregiver / provider sends a plan:
       medicines: [{'Med_Name','Dosage','Time','Frequency','Duration_Days','Priority'}, ...]
       exercise_minutes: new daily active-minutes goal (e.g. 60 = 1 hour), or None
    The medicines are added straight to the patient's reminders, the goal is updated and the
    patient gets a message (bell + pop-up)."""
    sender = get_user(sender_id)
    if not sender or sender["Role"] not in CARER_ROLES:
        raise ValidationError("Only caregiver and provider accounts can send a plan.")
    if not is_linked(sender_id, patient_id):
        raise ValidationError("Link this patient first (View patient: username + CID).")
    meds = [m for m in medicines if str(m.get("Med_Name") or "").strip()]
    minutes = None
    if exercise_minutes not in (None, "", 0, "0"):
        minutes = validate_number(exercise_minutes, "Exercise per day (minutes)", 5, 600)
    if not meds and minutes is None:
        raise ValidationError("Add at least one medicine or an exercise target.")
    times = [validate_time(m.get("Time") or "08:00", f"Medicine {i} time") for i, m in enumerate(meds, 1)]
    prios = [validate_choice(m.get("Priority") or "Medium", f"Medicine {i} priority", PRIORITIES) for i, m in enumerate(meds, 1)]
    lines = []
    rx_id = None
    if meds:
        rx_id = create_prescription(sender_id, patient_id, st.today_str(), note, meds, notify=False)
        items = [i for i in st.read_table("prescription_item") if i["Rx_ID"] == rx_id]
        for item, t, pr in zip(items, times, prios):
            schedule_prescription_item(patient_id, item["Item_ID"], t, pr)
            lines.append(f"• {item['Med_Name']}: {item['Dosage']} at {time_label(t)}, "
                         f"{item['Frequency'].lower()} for {item['Duration_Days']} days")
    if minutes is not None:
        g = get_goals(patient_id)
        set_goals(patient_id, int(float(g["Steps"]["Exercise_Target"])), minutes,
                  int(float(g["Distance"]["Exercise_Target"])) / 1000)
        lines.append(f"• Exercise: {minutes} minutes a day" + (f" ({minutes / 60:g} hour{'s' if minutes != 60 else ''})" if minutes % 30 == 0 else ""))
    note = clean_text(note, "Note", max_len=100, required=False)
    if note:
        lines.append(f"Note: {note}")
    title = f"New care plan from {sender['Full_Name']}" + (f" ({rx_id})" if rx_id else "")
    add_message(patient_id, sender_id, title,
                "\n".join(lines) + "\nYour reminders and exercise goal have been updated.")
    return {"Rx_ID": rx_id, "Medicines": len(meds), "Exercise_Minutes": minutes, "Lines": lines}


# =================================================================== profile
PROFILE_DEFAULTS = {"Email": "", "Gender": "", "Height_Cm": "", "Weight_Kg": "", "Blood_Type": "",
                    "Allergies": "", "Conditions": "", "Emergency_Name": "", "Emergency_Relation": "",
                    "Emergency_Phone": "", "Notify_Reminders": "True", "Notify_Weekly": "False",
                    "Snooze_Min": "10", "Sound_On": "True"}


def get_profile(user_id) -> dict:
    for row in st.read_table("health_profile"):
        if row["User_ID"] == user_id:
            merged = dict(PROFILE_DEFAULTS)
            merged.update({k: v for k, v in row.items() if v != ""})
            merged["User_ID"] = user_id
            return merged
    merged = dict(PROFILE_DEFAULTS)
    merged["User_ID"] = user_id
    return merged


def save_profile(user_id, **fields) -> dict:
    """Validate and save any subset of the profile fields."""
    clean = {}
    if "Email" in fields:
        clean["Email"] = validate_email(fields["Email"])
    if "Gender" in fields:
        clean["Gender"] = validate_choice(fields["Gender"], "Gender", GENDERS)
    if "Height_Cm" in fields:
        v = validate_number(fields["Height_Cm"], "Height (cm)", 50, 250, required=False)
        clean["Height_Cm"] = "" if v is None else v
    if "Weight_Kg" in fields:
        v = validate_number(fields["Weight_Kg"], "Weight (kg)", 10, 300, integer=False, required=False)
        clean["Weight_Kg"] = "" if v is None else v
    if "Blood_Type" in fields:
        clean["Blood_Type"] = validate_choice(fields["Blood_Type"], "Blood type", BLOOD_TYPES)
    for key, label in (("Allergies", "Allergies"), ("Conditions", "Health conditions")):
        if key in fields:
            clean[key] = clean_text(fields[key], label, max_len=120, required=False)
    if "Emergency_Name" in fields:
        clean["Emergency_Name"] = clean_text(fields["Emergency_Name"], "Emergency contact name",
                                             max_len=50, required=False)
    if "Emergency_Relation" in fields:
        clean["Emergency_Relation"] = clean_text(fields["Emergency_Relation"], "Relationship",
                                                 max_len=30, required=False)
    if "Emergency_Phone" in fields:
        clean["Emergency_Phone"] = validate_phone(fields["Emergency_Phone"])
    for key in ("Notify_Reminders", "Notify_Weekly", "Sound_On"):
        if key in fields:
            clean[key] = str(bool(fields[key]))
    if "Snooze_Min" in fields:
        clean["Snooze_Min"] = validate_number(fields["Snooze_Min"], "Snooze time (minutes)", 1, 60)
    with st.locked():
        current = get_profile(user_id)
        current.update({k: str(v) for k, v in clean.items()})
        rows = [r for r in st.read_table("health_profile") if r["User_ID"] != user_id]
        rows.append(current)
        st.write_table("health_profile", rows)
        if clean.get("Weight_Kg"):
            add_weight(user_id, clean["Weight_Kg"])
    return current


def add_weight(user_id, weight_kg, day=None):
    weight = validate_number(weight_kg, "Weight (kg)", 10, 300, integer=False)
    day = validate_date(day or st.today_str(), "Date", allow_future=False)
    with st.locked():
        rows = st.read_table("weight_log")
        for r in rows:
            if r["User_ID"] == user_id and r["Log_Date"] == day:
                r["Weight_Kg"] = str(weight)
                break
        else:
            rows.append({"Weight_ID": st.new_id(), "User_ID": user_id, "Log_Date": day,
                         "Weight_Kg": str(weight)})
        st.write_table("weight_log", rows)


def weight_series(user_id, start: date, end: date) -> list:
    out = []
    for r in st.read_table("weight_log"):
        if r["User_ID"] == user_id:
            d = st.parse_date(r["Log_Date"])
            if start <= d <= end:
                out.append({"date": d, "weight": float(r["Weight_Kg"])})
    return sorted(out, key=lambda x: x["date"])


# =================================================================== medication
def _shift_time(hhmm: str, hours: int) -> str:
    h, m = map(int, hhmm.split(":"))
    return f"{(h + hours) % 24:02d}:{m:02d}"


def slots_for(frequency: str, first_time: str) -> list:
    """Once daily -> [t]; Twice daily -> [t, t+12h]; Three times daily -> [t, t+6h, t+12h]."""
    if frequency == "Twice daily":
        return [first_time, _shift_time(first_time, 12)]
    if frequency == "Three times daily":
        return [first_time, _shift_time(first_time, 6), _shift_time(first_time, 12)]
    return [first_time]


def _clean_med(name, dosage, time, frequency, priority, start_date, end_date):
    name = validate_medicine(name)
    dosage = clean_text(dosage, "Dosage", 1, 50)
    time = validate_time(time, "Dosage time")
    frequency = validate_choice(frequency, "Frequency", FREQUENCIES)
    priority = validate_choice(priority, "Priority", PRIORITIES)
    start_date = validate_date(start_date or st.today_str(), "Start date")
    end_date = validate_date(end_date, "End date", required=False)
    if end_date and end_date < start_date:
        raise ValidationError("End date cannot be before the start date.")
    return name, dosage, time, frequency, priority, start_date, end_date


def add_medication(user_id, name, dosage, time, frequency="Once daily", priority="Medium",
                   start_date=None, end_date="", item_id="") -> list:
    """Add a medicine. Twice/three-times-daily creates one schedule row per dose time."""
    name, dosage, time, frequency, priority, start_date, end_date = _clean_med(
        name, dosage, time, frequency, priority, start_date, end_date)
    with st.locked():
        for m in list_medications(user_id):
            if m["Med_Name"].lower() == name.lower() and m["Dosage_Time"] == time:
                raise ValidationError(f"{name} is already scheduled at {time}.")
        slots = slots_for(frequency, time)
        ids = st.next_ids("medication", "Med_ID", "MED", len(slots))          # MED001, MED002 ...
        rows = [{"Med_ID": mid, "User_ID": user_id, "Item_ID": item_id, "Med_Name": name,
                 "Dosage": dosage, "Dosage_Time": t, "Frequency": frequency,
                 "Priority_Level": priority, "Start_Date": start_date, "End_Date": end_date,
                 "Is_Active": "True"} for mid, t in zip(ids, slots)]
        st.insert_many("medication", rows)
    return rows


def update_medication(med_id, user_id, name, dosage, time, frequency, priority,
                      start_date, end_date="", is_active=True):
    name, dosage, time, frequency, priority, start_date, end_date = _clean_med(
        name, dosage, time, frequency, priority, start_date, end_date)
    changed = st.update_where(
        "medication", lambda r: r["Med_ID"] == med_id and r["User_ID"] == user_id,
        {"Med_Name": name, "Dosage": dosage, "Dosage_Time": time, "Frequency": frequency,
         "Priority_Level": priority, "Start_Date": start_date, "End_Date": end_date,
         "Is_Active": str(bool(is_active))})
    if not changed:
        raise ValidationError("That medicine no longer exists.")


def delete_medication(med_id, user_id):
    with st.locked():
        if st.delete_where("medication", lambda r: r["Med_ID"] == med_id and r["User_ID"] == user_id):
            st.delete_where("compliance_log", lambda r: r["Med_ID"] == med_id)


def list_medications(user_id, active_only=False) -> list:
    rows = [m for m in st.read_table("medication") if m["User_ID"] == user_id]
    if active_only:
        rows = [m for m in rows if st.to_bool(m["Is_Active"])]
    return sorted(rows, key=lambda m: (m["Dosage_Time"], m["Med_Name"]))


def _med_active_on(m, day: date) -> bool:
    if not st.to_bool(m["Is_Active"]):
        return False
    if m["Start_Date"] and st.parse_date(m["Start_Date"]) > day:
        return False
    if m["End_Date"] and st.parse_date(m["End_Date"]) < day:
        return False
    return True


def when_text(target: datetime, now: datetime) -> str:
    secs = int((target - now).total_seconds())
    future = secs >= 0
    mins = abs(secs) // 60
    if mins < 1:
        return "Now"
    if mins < 60:
        text = f"{mins} minute{'s' if mins != 1 else ''}"
    else:
        hours = mins // 60
        text = f"{hours} hour{'s' if hours != 1 else ''}"
    return f"In {text}" if future else f"{text} ago"


def _display_status(log, scheduled: datetime, now: datetime):
    if log:
        status = log["Compliance_Status"]
        if status == "Taken":
            return "Taken"
        if status == "Missed":
            return "Missed"
        if status == "Snoozed":
            until = log.get("Snooze_Until", "")
            if until:
                try:
                    h, m = map(int, until.split(":"))
                    if scheduled.replace(hour=h, minute=m) > now:
                        return "Snoozed"
                except ValueError:
                    pass
            return "Overdue"
    return "Overdue" if scheduled <= now else "Upcoming"


def doses_between(user_id, start_day: date, end_day: date, now: datetime = None) -> list:
    """Every scheduled dose between two dates, with its current status."""
    now = now or datetime.now()
    meds = list_medications(user_id, active_only=False)
    logs = {}
    ids = {m["Med_ID"] for m in meds}
    for lg in st.read_table("compliance_log"):
        if lg["Med_ID"] in ids:
            logs[(lg["Med_ID"], lg["Log_Date"])] = lg
    doses = []
    day = start_day
    while day <= end_day:
        for m in meds:
            if not _med_active_on(m, day):
                continue
            h, mi = map(int, m["Dosage_Time"].split(":"))
            scheduled = datetime(day.year, day.month, day.day, h, mi)
            log = logs.get((m["Med_ID"], day.isoformat()))
            status = _display_status(log, scheduled, now)
            doses.append({
                "Med_ID": m["Med_ID"], "Med_Name": m["Med_Name"], "Dosage": m["Dosage"],
                "Dosage_Time": m["Dosage_Time"], "Priority_Level": m["Priority_Level"],
                "Frequency": m["Frequency"], "Date": day, "Scheduled": scheduled,
                "Status": status, "Action_Time": (log or {}).get("Action_Time", ""),
                "Snooze_Until": (log or {}).get("Snooze_Until", ""),
                "When": when_text(scheduled, now)})
        day += timedelta(days=1)
    doses.sort(key=lambda d: d["Scheduled"])
    return doses


def doses_for_date(user_id, day: date = None, now: datetime = None) -> list:
    day = day or date.today()
    return doses_between(user_id, day, day, now)


def upcoming_doses(user_id, days=3, now: datetime = None) -> list:
    now = now or datetime.now()
    end = now.date() + timedelta(days=days)
    return [d for d in doses_between(user_id, now.date(), end, now)
            if d["Status"] in ("Upcoming", "Snoozed") and d["Scheduled"] > now]


def next_dose(user_id, now: datetime = None):
    """The dose the user should think about next (overdue first, then the soonest upcoming)."""
    now = now or datetime.now()
    todays = doses_for_date(user_id, now.date(), now)
    pending = [d for d in todays if d["Status"] in ("Overdue", "Snoozed", "Upcoming")]
    if pending:
        overdue = [d for d in pending if d["Status"] == "Overdue"]
        return (overdue or pending)[0]
    future = upcoming_doses(user_id, 2, now)
    return future[0] if future else None


def set_dose_status(user_id, med_id, status, day: date = None, snooze_minutes=0):
    """Mark one dose Taken / Missed / Snoozed (creates or updates the compliance log)."""
    validate_choice(status, "Status", ("Taken", "Missed", "Snoozed"))
    day = day or date.today()
    med = next((m for m in list_medications(user_id) if m["Med_ID"] == med_id), None)
    if not med:
        raise ValidationError("That medicine no longer exists.")
    now = datetime.now()
    snooze_until = ""
    if status == "Snoozed":
        snooze_until = (now + timedelta(minutes=int(snooze_minutes or 10))).strftime("%H:%M")
    with st.locked():
        rows = st.read_table("compliance_log")
        for r in rows:
            if r["Med_ID"] == med_id and r["Log_Date"] == day.isoformat():
                r.update({"Compliance_Status": status, "Action_Time": now.strftime("%H:%M"),
                          "Snooze_Until": snooze_until})
                break
        else:
            rows.append({"Log_ID": st.new_id(), "Med_ID": med_id, "Log_Date": day.isoformat(),
                         "Scheduled_Time": med["Dosage_Time"], "Action_Time": now.strftime("%H:%M"),
                         "Compliance_Status": status, "Snooze_Until": snooze_until})
        st.write_table("compliance_log", rows)
    return snooze_until


def clear_dose_status(user_id, med_id, day: date = None):
    """Undo a Taken/Missed mark."""
    day = day or date.today()
    st.delete_where("compliance_log",
                    lambda r: r["Med_ID"] == med_id and r["Log_Date"] == day.isoformat())


def due_reminders(user_id, now: datetime = None, window_minutes=90) -> list:
    """Doses that need an alert right now (used by the Tkinter reminder thread)."""
    now = now or datetime.now()
    out = []
    for d in doses_for_date(user_id, now.date(), now):
        late = (now - d["Scheduled"]).total_seconds() / 60
        if d["Status"] == "Overdue" and 0 <= late <= window_minutes:
            out.append(d)
        elif d["Status"] == "Overdue" and d["Snooze_Until"]:
            out.append(d)  # a snooze has just ended
    return out


def adherence(user_id, start_day: date, end_day: date, now: datetime = None) -> dict:
    """Taken doses / doses that are due so far (unlogged past doses count as missed)."""
    now = now or datetime.now()
    doses = doses_between(user_id, start_day, end_day, now)
    due = [d for d in doses if d["Scheduled"] <= now or d["Status"] == "Taken"]
    taken = sum(1 for d in due if d["Status"] == "Taken")
    total = len(due)
    return {"taken": taken, "missed": total - taken, "total": total,
            "pct": round(100 * taken / total) if total else 0}


def week_adherence(user_id, now: datetime = None) -> dict:
    now = now or datetime.now()
    return adherence(user_id, now.date() - timedelta(days=6), now.date(), now)


def notifications(user_id, now: datetime = None) -> dict:
    """Everything the bell 🔔 shows for one patient today.

    Returns {"count": number for the red badge (doses that need attention),
             "attention": overdue doses, "upcoming": later doses today (incl. snoozed),
             "activity": what happened today (doses taken, exercise logged, goals reached)}
    """
    now = now or datetime.now()
    today = doses_for_date(user_id, now.date(), now)
    attention = [d for d in today if d["Status"] == "Overdue"]
    upcoming = [d for d in today if d["Status"] in ("Upcoming", "Snoozed")]
    activity = []
    for d in today:
        if d["Status"] == "Taken":
            activity.append({"icon": "✅", "text": f"{d['Med_Name']} taken",
                             "detail": f"at {d['Action_Time']}" if d["Action_Time"] else ""})
        elif d["Status"] == "Missed":
            activity.append({"icon": "📝", "text": f"{d['Med_Name']} marked as missed", "detail": ""})
    try:
        for a in activities_for_date(user_id, now.date()):
            bits = [f"{a['minutes']} min"] if a["minutes"] else []
            if a["distance_km"]:
                bits.append(f"{a['distance_km']:g} km")
            if a["steps"]:
                bits.append(f"{a['steps']:,} steps")
            activity.append({"icon": "🏃", "text": f"{a['Type']} logged", "detail": " · ".join(bits)})
        ex = exercise_today(user_id, now.date())
        for key, label in (("steps", "Steps"), ("minutes", "Active minutes"), ("km", "Distance")):
            if ex[f"{key}_pct"] >= 100:
                activity.append({"icon": "🎯", "text": f"{label} goal reached today!", "detail": ""})
    except (KeyError, ValueError):
        pass                                   # no exercise goals yet - nothing to report
    unread = messages_for(user_id, unread_only=True)
    return {"count": len(attention) + len(unread), "attention": attention, "upcoming": upcoming,
            "activity": activity, "messages": unread}


# =================================================================== exercise
def ensure_goals(user_id):
    with st.locked():
        have = {g["Goal_Type"] for g in st.read_table("exercise_goal")
                if g["User_ID"] == user_id and st.to_bool(g["Is_Active"])}
        new = [{"Goal_ID": st.new_id(), "User_ID": user_id, "Goal_Type": t,
                "Exercise_Target": str(DEFAULT_GOALS[t]), "Start_Date": st.today_str(),
                "Target_Date": "", "Is_Active": "True"} for t in GOAL_TYPES if t not in have]
        if new:
            st.insert_many("exercise_goal", new)


def get_goals(user_id) -> dict:
    ensure_goals(user_id)
    goals = {}
    for g in st.read_table("exercise_goal"):
        if g["User_ID"] == user_id and st.to_bool(g["Is_Active"]):
            goals[g["Goal_Type"]] = g
    return goals


def set_goals(user_id, steps, minutes, distance_km):
    steps = validate_number(steps, "Daily steps goal", 500, 50000)
    minutes = validate_number(minutes, "Active minutes goal", 5, 600)
    km = validate_number(distance_km, "Distance goal (km)", 0.5, 100, integer=False)
    ensure_goals(user_id)
    targets = {"Steps": steps, "Minutes": minutes, "Distance": int(round(km * 1000))}
    for gtype, value in targets.items():
        st.update_where("exercise_goal",
                        lambda r, t=gtype: r["User_ID"] == user_id and r["Goal_Type"] == t
                        and st.to_bool(r["Is_Active"]), {"Exercise_Target": value})


def estimate_steps(activity, minutes, distance_km) -> int:
    if activity in ("Walking", "Hiking"):
        return int(distance_km * 1300) if distance_km else int(minutes * 100)
    if activity == "Running":
        return int(distance_km * 1000) if distance_km else int(minutes * 160)
    return 0


def log_activity(user_id, activity_type, minutes, distance_km=0, steps=None, day=None) -> str:
    """Record one activity. It adds progress to the Steps, Minutes and Distance goals."""
    activity_type = validate_choice(activity_type, "Activity type", ACTIVITY_TYPES)
    minutes = validate_number(minutes, "Duration (minutes)", 1, 600)
    distance_km = validate_number(distance_km or 0, "Distance (km)", 0, 200, integer=False, required=False) or 0
    steps = validate_number(steps, "Steps", 0, 100000, required=False)
    if not steps:
        steps = estimate_steps(activity_type, minutes, distance_km)
    day = validate_date(day or st.today_str(), "Date", allow_future=False)
    goals = get_goals(user_id)
    activity_id = st.new_id()
    values = {"Steps": steps, "Minutes": minutes, "Distance": int(round(distance_km * 1000))}
    with st.locked():
        new_rows = []
        for gtype, value in values.items():
            if value > 0:
                new_rows.append({"Exercise_ID": st.new_id(), "Goal_ID": goals[gtype]["Goal_ID"],
                                 "Log_Date": day, "Progress_Value": str(value), "Progress_Percent": "0",
                                 "Activity_ID": activity_id, "Activity_Type": activity_type})
        st.insert_many("exercise_log", new_rows)
        _recompute_percent(user_id, day)
    return activity_id


def _recompute_percent(user_id, day: str):
    goals = {g["Goal_ID"]: g for g in st.read_table("exercise_goal") if g["User_ID"] == user_id}
    rows = st.read_table("exercise_log")
    running = {}
    for r in rows:
        g = goals.get(r["Goal_ID"])
        if g and r["Log_Date"] == day:
            running[g["Goal_ID"]] = running.get(g["Goal_ID"], 0) + int(float(r["Progress_Value"]))
            target = max(1, int(float(g["Exercise_Target"])))
            r["Progress_Percent"] = f"{min(100.0, 100 * running[g['Goal_ID']] / target):.1f}"
    st.write_table("exercise_log", rows)


def _user_logs(user_id):
    goals = {g["Goal_ID"]: g for g in st.read_table("exercise_goal") if g["User_ID"] == user_id}
    logs = [r for r in st.read_table("exercise_log") if r["Goal_ID"] in goals]
    return goals, logs


def exercise_series(user_id, start: date, end: date) -> list:
    """One entry per day: steps, minutes, distance_km."""
    goals, logs = _user_logs(user_id)
    days = {}
    d = start
    while d <= end:
        days[d.isoformat()] = {"date": d, "steps": 0, "minutes": 0, "distance_km": 0.0}
        d += timedelta(days=1)
    for r in logs:
        entry = days.get(r["Log_Date"])
        if not entry:
            continue
        value = int(float(r["Progress_Value"]))
        gtype = goals[r["Goal_ID"]]["Goal_Type"]
        if gtype == "Steps":
            entry["steps"] += value
        elif gtype == "Minutes":
            entry["minutes"] += value
        else:
            entry["distance_km"] = round(entry["distance_km"] + value / 1000, 2)
    return list(days.values())


def exercise_today(user_id, day: date = None) -> dict:
    """Today's totals, goals and percentages."""
    day = day or date.today()
    totals = exercise_series(user_id, day, day)[0]
    goals = get_goals(user_id)
    steps_goal = int(float(goals["Steps"]["Exercise_Target"]))
    min_goal = int(float(goals["Minutes"]["Exercise_Target"]))
    km_goal = int(float(goals["Distance"]["Exercise_Target"])) / 1000
    pct = lambda v, g: min(100, round(100 * v / g)) if g else 0
    return {**totals, "steps_goal": steps_goal, "minutes_goal": min_goal, "km_goal": km_goal,
            "steps_pct": pct(totals["steps"], steps_goal), "minutes_pct": pct(totals["minutes"], min_goal),
            "km_pct": pct(totals["distance_km"], km_goal)}


def activities_for_date(user_id, day: date = None) -> list:
    day = (day or date.today()).isoformat()
    goals, logs = _user_logs(user_id)
    acts = {}
    for r in logs:
        if r["Log_Date"] != day:
            continue
        a = acts.setdefault(r["Activity_ID"], {"Activity_ID": r["Activity_ID"], "Type": r["Activity_Type"],
                                                "steps": 0, "minutes": 0, "distance_km": 0.0})
        value = int(float(r["Progress_Value"]))
        gtype = goals[r["Goal_ID"]]["Goal_Type"]
        if gtype == "Steps":
            a["steps"] = value
        elif gtype == "Minutes":
            a["minutes"] = value
        else:
            a["distance_km"] = round(value / 1000, 2)
    return list(acts.values())


def delete_activity(user_id, activity_id):
    goals, _ = _user_logs(user_id)
    with st.locked():
        days = {r["Log_Date"] for r in st.read_table("exercise_log")
                if r["Activity_ID"] == activity_id and r["Goal_ID"] in goals}
        st.delete_where("exercise_log", lambda r: r["Activity_ID"] == activity_id and r["Goal_ID"] in goals)
        for d in days:
            _recompute_percent(user_id, d)


def daily_goal_checklist(user_id, day: date = None) -> list:
    t = exercise_today(user_id, day)
    return [
        {"label": f"Walk {t['steps_goal']:,} steps", "done": t["steps"] >= t["steps_goal"], "pct": t["steps_pct"]},
        {"label": f"Be active {t['minutes_goal']} minutes", "done": t["minutes"] >= t["minutes_goal"], "pct": t["minutes_pct"]},
        {"label": f"Cover {t['km_goal']:g} km", "done": t["distance_km"] >= t["km_goal"], "pct": t["km_pct"]},
    ]


# =================================================================== prescriptions
def create_prescription(provider_id, patient_id, rx_date, note, items: list, notify=True) -> str:
    """items: [{'Med_Name','Dosage','Frequency','Duration_Days'}, ...]"""
    patient = get_user(patient_id)
    if not patient or patient["Role"] != "Patient":
        raise ValidationError("The prescription must be for a patient account.")
    rx_date = validate_date(rx_date or st.today_str(), "Prescription date")
    note = clean_text(note, "Diagnosis / note", max_len=100, required=False)
    clean_items = []
    for i, it in enumerate(items, 1):
        clean_items.append({
            "Med_Name": validate_medicine(it.get("Med_Name"), f"Medicine {i}"),
            "Dosage": validate_rx_dosage(it.get("Dosage"), f"Medicine {i} dosage"),
            "Frequency": validate_choice(it.get("Frequency", "Once daily"), f"Medicine {i} frequency", FREQUENCIES),
            "Duration_Days": validate_number(it.get("Duration_Days"), f"Medicine {i} duration (days)", 1, 365)})
    if not clean_items:
        raise ValidationError("Add at least one medicine.")
    with st.locked():
        rx_id = st.next_ids("prescription", "Rx_ID", "RX")[0]               # RX001, RX002 ...
        st.insert("prescription", {"Rx_ID": rx_id, "Provider_ID": provider_id, "Patient_ID": patient_id,
                                   "Rx_Date": rx_date, "Diagnosis_Note": note})
        st.insert_many("prescription_item", [dict(it, Item_ID=st.new_id(), Rx_ID=rx_id,
                                                  Duration_Days=str(it["Duration_Days"])) for it in clean_items])
    if notify and provider_id != patient_id:
        who = (get_user(provider_id) or {}).get("Full_Name", "Your doctor")
        add_message(patient_id, provider_id, f"New prescription {rx_id} from {who}",
                    "\n".join(f"\u2022 {it['Med_Name']}: {it['Dosage']}, {it['Frequency'].lower()} for "
                              f"{it['Duration_Days']} days" for it in clean_items)
                    + "\nOpen Prescriptions and press \u201cAdd to my schedule\u201d to get reminders.")
    return rx_id


def _item_status(rx_date: str, duration: str) -> str:
    end = st.parse_date(rx_date) + timedelta(days=int(float(duration)) - 1)
    return "Active" if end >= date.today() else "Past"


def list_prescription_items(patient_id=None, provider_id=None) -> list:
    """Flat list of prescribed medicines, newest first."""
    users = {u["User_ID"]: u for u in st.read_table("user_account")}
    rxs = {r["Rx_ID"]: r for r in st.read_table("prescription")
           if (patient_id is None or r["Patient_ID"] == patient_id)
           and (provider_id is None or r["Provider_ID"] == provider_id)}
    scheduled = {m["Item_ID"] for m in st.read_table("medication") if m["Item_ID"]}
    out = []
    for it in st.read_table("prescription_item"):
        rx = rxs.get(it["Rx_ID"])
        if not rx:
            continue
        provider = users.get(rx["Provider_ID"], {})
        patient = users.get(rx["Patient_ID"], {})
        out.append({**it, "Rx_Date": rx["Rx_Date"], "Diagnosis_Note": rx["Diagnosis_Note"],
                    "Patient_ID": rx["Patient_ID"], "Provider_ID": rx["Provider_ID"],
                    "Patient_Name": patient.get("Full_Name", "?"),
                    "Provider_Name": ("Self-recorded" if rx["Provider_ID"] == rx["Patient_ID"]
                                      else provider.get("Full_Name", "Unknown")),
                    "Status": _item_status(rx["Rx_Date"], it["Duration_Days"]),
                    "Scheduled": it["Item_ID"] in scheduled})
    out.sort(key=lambda r: (r["Rx_Date"], r["Med_Name"]), reverse=True)
    return out


def get_prescription(rx_id) -> dict:
    rx = next((r for r in st.read_table("prescription") if r["Rx_ID"] == rx_id), None)
    if not rx:
        raise ValidationError("Prescription not found.")
    items = [i for i in list_prescription_items() if i["Rx_ID"] == rx_id]
    patient, provider = get_user(rx["Patient_ID"]), get_user(rx["Provider_ID"])
    return {**rx, "Items": items, "Patient_Name": (patient or {}).get("Full_Name", "?"),
            "Provider_Name": ("Self-recorded" if rx["Provider_ID"] == rx["Patient_ID"]
                              else (provider or {}).get("Full_Name", "Unknown"))}


def update_prescription_item(item_id, requester_id, med_name, dosage, frequency, duration_days,
                             rx_date=None, note=None):
    item = next((i for i in st.read_table("prescription_item") if i["Item_ID"] == item_id), None)
    rx = next((r for r in st.read_table("prescription") if item and r["Rx_ID"] == item["Rx_ID"]), None)
    if not item or not rx:
        raise ValidationError("Prescription not found.")
    if rx["Provider_ID"] != requester_id:
        raise ValidationError("Only the person who created this prescription can edit it.")
    changes = {"Med_Name": validate_medicine(med_name),
               "Dosage": validate_rx_dosage(dosage, "Dosage"),
               "Frequency": validate_choice(frequency, "Frequency", FREQUENCIES),
               "Duration_Days": validate_number(duration_days, "Duration (days)", 1, 365)}
    st.update_where("prescription_item", lambda r: r["Item_ID"] == item_id, changes)
    rx_changes = {}
    if rx_date:
        rx_changes["Rx_Date"] = validate_date(rx_date, "Prescription date")
    if note is not None:
        rx_changes["Diagnosis_Note"] = clean_text(note, "Diagnosis / note", max_len=100, required=False)
    if rx_changes:
        st.update_where("prescription", lambda r: r["Rx_ID"] == rx["Rx_ID"], rx_changes)


def delete_prescription_item(item_id, requester_id):
    item = next((i for i in st.read_table("prescription_item") if i["Item_ID"] == item_id), None)
    rx = next((r for r in st.read_table("prescription") if item and r["Rx_ID"] == item["Rx_ID"]), None)
    if not item or not rx:
        return
    if rx["Provider_ID"] != requester_id:
        raise ValidationError("Only the person who created this prescription can delete it.")
    with st.locked():
        st.delete_where("prescription_item", lambda r: r["Item_ID"] == item_id)
        st.update_where("medication", lambda r: r["Item_ID"] == item_id, {"Item_ID": ""})
        if not any(i["Rx_ID"] == rx["Rx_ID"] for i in st.read_table("prescription_item")):
            st.delete_where("prescription", lambda r: r["Rx_ID"] == rx["Rx_ID"])


def schedule_prescription_item(user_id, item_id, first_time="08:00", priority="Medium") -> list:
    """'Add to my schedule': turn a prescribed medicine into reminder rows."""
    item = next((i for i in list_prescription_items(patient_id=user_id) if i["Item_ID"] == item_id), None)
    if not item:
        raise ValidationError("Prescription item not found.")
    if item["Scheduled"]:
        raise ValidationError(f"{item['Med_Name']} is already in your schedule.")
    start = max(date.today(), st.parse_date(item["Rx_Date"]))
    end = st.parse_date(item["Rx_Date"]) + timedelta(days=int(item["Duration_Days"]) - 1)
    if end < date.today():
        raise ValidationError("This prescription has finished, so it cannot be scheduled.")
    return add_medication(user_id, item["Med_Name"], item["Dosage"], first_time, item["Frequency"],
                          priority, start.isoformat(), end.isoformat(), item_id=item_id)


def prescription_summary_html(rx_id) -> str:
    """A clean, printable HTML summary (open it in a browser and press Ctrl+P)."""
    from html import escape as e
    rx = get_prescription(rx_id)
    rows = "".join(
        f"<tr><td>{e(i['Med_Name'])}</td><td>{e(i['Dosage'])}</td><td>{e(i['Frequency'])}</td>"
        f"<td>{e(i['Duration_Days'])} days</td><td>{e(i['Status'])}</td></tr>" for i in rx["Items"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Prescription {e(rx_id)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:720px;margin:32px auto;color:#12303F}}
h1{{margin:0}} h1 span{{color:#2E9E78}} .bar{{height:4px;background:#2E9E78;margin:10px 0 20px}}
table{{width:100%;border-collapse:collapse;margin-top:16px}} th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#0E2C3C;color:#fff}} .meta p{{margin:4px 0}} .note{{margin-top:28px;font-size:12px;color:#666}}</style></head>
<body><h1>Druk<span>Care</span> &middot; Prescription Summary</h1><div class="bar"></div>
<div class="meta"><p><b>Patient:</b> {e(rx['Patient_Name'])}</p><p><b>Prescribed by:</b> {e(rx['Provider_Name'])}</p>
<p><b>Date:</b> {e(rx['Rx_Date'])} &nbsp; <b>Reference:</b> {e(rx_id)}</p>
<p><b>Diagnosis / note:</b> {e(rx['Diagnosis_Note'] or '-')}</p></div>
<table><tr><th>Medicine</th><th>Dosage</th><th>Frequency</th><th>Duration</th><th>Status</th></tr>{rows}</table>
<p class="note">Generated by DrukCare.</p></body></html>"""


# =================================================================== analytics
def analytics_data(user_id, days: int, now: datetime = None) -> dict:
    """Everything the analytics charts need for the last `days` days."""
    now = now or datetime.now()
    end = now.date()
    start = end - timedelta(days=days - 1)
    doses = doses_between(user_id, start, end, now)
    per_day = {}
    for d in doses:
        if d["Scheduled"] <= now or d["Status"] == "Taken":
            e = per_day.setdefault(d["Date"], {"taken": 0, "total": 0})
            e["total"] += 1
            e["taken"] += d["Status"] == "Taken"
    adherence_days = [{"date": day, "taken": v["taken"], "missed": v["total"] - v["taken"],
                       "pct": round(100 * v["taken"] / v["total"]) if v["total"] else None}
                      for day, v in sorted(per_day.items())]
    taken = sum(v["taken"] for v in per_day.values())
    total = sum(v["total"] for v in per_day.values())
    ex = exercise_series(user_id, start, end)
    goals = get_goals(user_id)
    active_days = [e for e in ex if e["steps"] or e["minutes"]]
    return {
        "start": start, "end": end, "adherence_days": adherence_days,
        "adherence": {"taken": taken, "missed": total - taken, "total": total,
                      "pct": round(100 * taken / total) if total else 0},
        "exercise": ex, "weight": weight_series(user_id, start, end),
        "avg_steps": round(sum(e["steps"] for e in active_days) / len(active_days)) if active_days else 0,
        "avg_minutes": round(sum(e["minutes"] for e in active_days) / len(active_days)) if active_days else 0,
        "steps_goal": int(float(goals["Steps"]["Exercise_Target"])),
        "minutes_goal": int(float(goals["Minutes"]["Exercise_Target"])),
        # the four metric tiles from the proposal presentation
        "full_dose_days": sum(1 for v in per_day.values() if v["total"] and v["taken"] == v["total"]),
        "dose_days": len(per_day),
        "avg_exercise_pct": round(sum(_steps_pct(e, goals) for e in ex) / len(ex)) if ex else 0,
        "goal_days": sum(1 for e in ex if _steps_pct(e, goals) >= 100),
        "days": len(ex),
    }


def _steps_pct(entry, goals) -> int:
    goal = int(float(goals["Steps"]["Exercise_Target"]))
    return min(100, round(100 * entry["steps"] / goal)) if goal else 0
