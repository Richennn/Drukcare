"""DrukCare - Gradio prescription portal.

Run with:   python gradio_app.py          (opens http://127.0.0.1:7860)

Role of Gradio in this project (see the proposal):
  * the lightweight web portal where a provider (or the patient) ENTERS, VALIDATES, SAVES
    and PRINTS prescription summaries
  * a prescription can be added to the patient's medication schedule
  * a few quick healthcare tools: today's medicines, quick exercise log, BMI helper

What is better done in Streamlit: the full dashboards (Home, charts, 3-month analytics,
caregiver view, profile editing).  There is no account linking: a provider simply chooses the
patient from the list of patient accounts.  What is better done in Tkinter: pop-up reminders with
sound and the always-on-top desktop experience.  All three share the CSV files in data/.

HOW TO USE YOUR OWN PHOTOS: edit the "IMAGE PATHS" block in drukcare_core/config.py or save
pictures into assets/ with the listed names.  Missing pictures show a clean placeholder.
"""
import sys
from datetime import date, datetime
from html import escape

import gradio as gr

from drukcare_core import config as C
from drukcare_core import images as I
from drukcare_core import seed, storage
from drukcare_core import services as S
from drukcare_core.validators import ValidationError, time_choices, time_label, validate_number

storage.init_storage()
seed.remove_demo_data()

CSS = f"""
html, body, .dark, :root {{ --body-background-fill:{C.IVORY}; --background-fill-primary:{C.CARD}; --background-fill-secondary:{C.IVORY};
  --block-background-fill:{C.CARD}; --border-color-primary:{C.BORDER}; --input-background-fill:{C.SURFACE}; --panel-background-fill:{C.CARD}; --table-even-background-fill:{C.CARD}; --table-odd-background-fill:{C.IVORY_DARK}; }}
body {{ background:{C.IVORY} !important; }}
.tabs, .tabitem, .group, .form, .gap, .wrap, .gradio-container .block.padded {{ background:transparent !important; }}
button.secondary, button.lg.secondary, button.sm.secondary {{ background:{C.SURFACE} !important; color:{C.TEXT} !important; border:1px solid {C.BORDER} !important; }}
button.primary {{ background:{C.EMERALD} !important; color:#fff !important; }}
.gradio-container {{ background:{C.IVORY} !important; max-width:1180px !important; margin:auto; }}
.dc-banner {{ position:relative; height:220px; border-radius:18px; overflow:hidden; background-repeat:no-repeat;
  background-size:cover; background-position:right center; display:flex; align-items:center;
  box-shadow:0 6px 22px rgba(14,44,60,.14); margin-bottom:10px; }}
.dc-banner .t {{ position:relative; margin-left:20px; padding:16px 26px; border-radius:16px; background:rgba(250,254,254,.82); }}
.dc-logo {{ display:flex; align-items:center; gap:8px; font-size:1.9rem; font-weight:800; color:{C.TEXT}; font-family:Georgia,serif; }} .dc-logo img {{ height:42px; }} .dc-logo span {{ color:{C.EMERALD}; }}
.dc-title {{ font-family:'Palatino Linotype',Georgia,serif; font-style:italic; font-size:1.6rem; color:{C.TEXT}; }}
.dc-sub {{ color:{C.TEXT}; font-style:italic; }}
.dc-chip {{ position:absolute; top:12px; right:16px; background:rgba(255,255,255,.93); color:{C.TEXT}; border-radius:30px; padding:4px 14px 4px 6px;
  display:flex; align-items:center; gap:8px; font-weight:600; font-size:.88rem; box-shadow:0 2px 10px rgba(0,0,0,.1); }}
.dc-chip img {{ width:32px; height:32px; border-radius:50%; }}
.dc-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }}
.dc-card {{ background:{C.TINT_MINT}; border:1px solid {C.BORDER}; border-radius:18px; padding:16px 18px; box-shadow:0 4px 16px rgba(14,44,60,.06); color:{C.TEXT}; }}
.dc-card .l {{ color:{C.EMERALD_DARK}; font-size:.82rem; font-weight:700; }} .dc-card .b {{ font-size:1.4rem; font-weight:700; margin:.3rem 0; }}
.dc-card .s {{ color:{C.MUTED}; font-size:.88rem; }}
.dc-bar {{ height:9px; border-radius:6px; background:{C.TRACK}; overflow:hidden; margin:.5rem 0; }}
.dc-bar i {{ display:block; height:100%; background:linear-gradient(90deg,{C.EMERALD},{C.TEAL_LIGHT}); }}
.dc-ok {{ background:#DDF5E6; color:#14764A; border-radius:10px; padding:10px 14px; }}
.dc-err {{ background:#FDE3E3; color:#B02A2A; border-radius:10px; padding:10px 14px; }}
.dc-note {{ background:#FFF4D6; border:1px solid #F0D78A; color:#7A5B00; border-radius:10px; padding:8px 12px; font-size:.85rem; }}
.dc-rx {{ background:{C.CARD}; border:1px solid {C.BORDER}; border-radius:14px; padding:18px 22px; color:{C.TEXT}; }}
.dc-rx table {{ width:100%; border-collapse:collapse; margin-top:10px; }} .dc-rx th {{ background:{C.NAVY}; color:#fff; padding:8px; text-align:left; }}
.dc-rx td {{ border:1px solid {C.BORDER}; padding:8px; }}
.dc-foot {{ text-align:center; color:{C.MUTED}; font-size:.8rem; margin-top:14px; }}
@media print {{ .dc-rx .dc-logo {{ color:#000 !important; }} .dc-rx {{ background:#fff !important; color:#000 !important; }} .dc-rx td {{ color:#000; }} body * {{ visibility:hidden; }} .print-area, .print-area * {{ visibility:visible; }} .print-area {{ position:absolute; left:0; top:0; width:100%; }} }}
"""

THEME = gr.themes.Soft(primary_hue=gr.themes.colors.teal, neutral_hue=gr.themes.colors.gray,
                       font=("Segoe UI", "system-ui", "sans-serif"))


# ================================================================== html helpers
def ok(msg):
    return f'<div class="dc-ok">✅ {escape(str(msg))}</div>'


def err(e):
    text = str(e) if isinstance(e, (ValidationError, storage.StorageError)) else f"Something went wrong: {e}"
    return f'<div class="dc-err">⚠️ {escape(text)}</div>'


def t12(hhmm):
    return time_label(hhmm)            # '20:15' -> '8:15 PM' 


def initials(name):
    return "".join(w[0] for w in name.replace("Dr.", "").split()[:2]).upper() or "DC"


def header_html(user=None):
    bg = f"url('{I.card_uri(C.GRADIO_BANNER, (1400, 260))}')"
    logo_src = I.logo_uri(42)
    logo = f'<img src="{logo_src}" alt="DrukCare logo">' if logo_src else ""
    chip = ""
    if user:
        av = I.data_uri(I.profile_photo_path(user["User_ID"]), (64, 64), circle=True, initials=initials(user["Full_Name"]))
        chip = f'<div class="dc-chip"><img src="{av}">{escape(user["Full_Name"])} · {user["Role"]}</div>'
    return (f'<div class="dc-banner" style="background-image:{bg}"><div class="t">'
            f'<div class="dc-logo">{logo}<span>Druk<span>Care</span></span></div><div class="dc-title">Prescription Portal</div>'
            f'<div class="dc-sub">Enter, validate, save and print prescription summaries.</div></div>{chip}</div>')


def ring(pct, size=84):
    r, stroke = (size - 10) / 2, 10
    circ = 6.2832 * r
    return (f'<svg width="{size}" height="{size}"><circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{C.TRACK}" stroke-width="{stroke}"/>'
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{C.EMERALD}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ*(1-pct/100):.1f}" transform="rotate(-90 {size/2} {size/2})"/>'
            f'<text x="50%" y="50%" text-anchor="middle" dy=".35em" font-weight="700" font-size="{size*.21:.0f}" fill="{C.TEXT}">{pct}%</text></svg>')


def overview_html(user):
    if not user:
        return ""
    if user["Role"] == "Patient":
        uid = user["User_ID"]
        nxt, ex, wk = S.next_dose(uid), S.exercise_today(uid), S.week_adherence(uid)
        active = [i for i in S.list_prescription_items(patient_id=uid) if i["Status"] == "Active"]
        nxt_html = (f'<div class="b">{escape(nxt["Med_Name"])}</div><div class="s">{escape(nxt["Dosage"])} · {t12(nxt["Dosage_Time"])} · {nxt["Priority_Level"]} priority<br>{nxt["Status"]} · {nxt["When"]}</div>'
                    if nxt else '<div class="b">All done 🎉</div>')
        return f"""<div class="dc-cards">
          <div class="dc-card"><div class="l">💊 Next medication</div>{nxt_html}</div>
          <div class="dc-card"><div class="l">🚶 Today's exercise</div><div class="b">{ex['steps']:,} / {ex['steps_goal']:,} steps</div>
            <div class="dc-bar"><i style="width:{ex['steps_pct']}%"></i></div><div class="s">⏱ {ex['minutes']} min · 📍 {ex['distance_km']:g} km</div></div>
          <div class="dc-card"><div class="l">📈 Adherence (7 days)</div><div style="display:flex;gap:12px;align-items:center">{ring(wk['pct'])}<div class="s">{wk['taken']}/{wk['total']} doses taken</div></div></div>
          <div class="dc-card"><div class="l">📄 Active prescriptions</div><div class="b">{len(active)}</div><div class="s">medicines currently prescribed</div></div></div>"""
    if user["Role"] == "Provider":
        items = S.list_prescription_items(provider_id=user["User_ID"])
        return f"""<div class="dc-cards"><div class="dc-card"><div class="l">Medicines prescribed</div><div class="b">{len(items)}</div></div>
          <div class="dc-card"><div class="l">Patients</div><div class="b">{len(S.patients_of_provider(user['User_ID']))}</div></div>
          <div class="dc-card"><div class="l">Active medicines</div><div class="b">{sum(i['Status'] == 'Active' for i in items)}</div></div></div>"""
    return '<div class="dc-note">Caregivers: open the Streamlit dashboard (streamlit run app.py) to follow a patient\'s progress.</div>'


# ============================================================ prescription data
def rx_items_for(user):
    if not user:
        return []
    if user["Role"] == "Provider":
        return S.list_prescription_items(provider_id=user["User_ID"])
    if user["Role"] == "Patient":
        return S.list_prescription_items(patient_id=user["User_ID"])
    return []


def rx_rows(user):
    return [[i["Med_Name"], i["Dosage"], i["Frequency"], int(i["Duration_Days"]), i["Rx_Date"], i["Status"],
             i["Patient_Name"], i["Provider_Name"], "Yes" if i["Scheduled"] else "No"] for i in rx_items_for(user)]


def rx_choices(user):
    return [(f"{i['Med_Name']} · {i['Rx_Date']} · {i['Patient_Name']}", i["Item_ID"]) for i in rx_items_for(user)]


def summary_file(rx_id):
    folder = C.DATA_DIR / "summaries"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"prescription_{rx_id}.html"
    path.write_text(S.prescription_summary_html(rx_id), encoding="utf-8")
    return str(path)


def summary_block(rx_id):
    rx = S.get_prescription(rx_id)
    rows = "".join(f"<tr><td>{escape(i['Med_Name'])}</td><td>{escape(i['Dosage'])}</td><td>{escape(i['Frequency'])}</td>"
                   f"<td>{i['Duration_Days']} days</td><td>{i['Status']}</td></tr>" for i in rx["Items"])
    return (f'<div class="dc-rx print-area"><div class="dc-logo" style="font-size:1.4rem">Druk<span>Care</span> · Prescription Summary</div>'
            f'<p><b>Patient:</b> {escape(rx["Patient_Name"])} &nbsp; <b>Prescribed by:</b> {escape(rx["Provider_Name"])}<br>'
            f'<b>Date:</b> {rx["Rx_Date"]} &nbsp; <b>Reference:</b> {rx_id}<br><b>Diagnosis / note:</b> {escape(rx["Diagnosis_Note"] or "-")}</p>'
            f'<table><tr><th>Medicine</th><th>Dosage</th><th>Frequency</th><th>Duration</th><th>Status</th></tr>{rows}</table>'
            f'<p style="font-size:.8rem;color:{C.MUTED}">Generated by DrukCare.</p></div>')


# ============================================================== event handlers
def do_login(username, password):
    try:
        user = S.authenticate(username, password)
        return user, ""
    except Exception as e:
        return None, err(e)


def do_register(name, cid, username, password, confirm, role):
    try:
        user = S.register_user(name, username, password, confirm, role, cid=cid)
        return user, ""
    except Exception as e:
        return None, err(e)


def do_logout():
    return None, "", ""


def generate(user, patient_choice, rx_date, note, *cells):
    if not user:
        return err("Please log in first."), "", None
    try:
        items = []
        for k in range(0, len(cells), 4):
            name, dose, freq, days = cells[k:k + 4]
            if str(name or "").strip() or str(dose or "").strip():
                items.append({"Med_Name": name, "Dosage": dose, "Frequency": freq, "Duration_Days": days})
        if user["Role"] == "Provider":
            pid = S.patient_from_choice(patient_choice, user["User_ID"])["User_ID"]
        elif user["Role"] == "Patient":
            pid = user["User_ID"]
        else:
            raise ValidationError("Only providers and patients can create prescriptions.")
        rx_id = S.create_prescription(user["User_ID"], pid, rx_date, note, items)
        return ok(f"Prescription {rx_id} saved. You can print it below."), summary_block(rx_id), summary_file(rx_id)
    except Exception as e:
        return err(e), "", None


def view_summary(user, item_id):
    try:
        item = next(i for i in rx_items_for(user) if i["Item_ID"] == item_id)
        return summary_block(item["Rx_ID"]), summary_file(item["Rx_ID"]), ""
    except StopIteration:
        return "", None, err("Please pick a prescription from the list first.")
    except Exception as e:
        return "", None, err(e)


def schedule(user, item_id, time_text, priority):
    try:
        if not user or user["Role"] != "Patient":
            raise ValidationError("Only patients can add medicines to their own schedule.")
        if not item_id:
            raise ValidationError("Please pick a prescription from the list first.")
        rows = S.schedule_prescription_item(user["User_ID"], item_id, time_text, priority)
        return ok(f"Added to your schedule ({len(rows)} reminder{'s' if len(rows) > 1 else ''}). Open the desktop app to get pop-up reminders.")
    except Exception as e:
        return err(e)


def delete_item(user, item_id):
    try:
        if not item_id:
            raise ValidationError("Please pick a prescription from the list first.")
        S.delete_prescription_item(item_id, user["User_ID"])
        return ok("Prescription item deleted.")
    except Exception as e:
        return err(e)


def refresh_rx(user):
    return rx_rows(user), gr.update(choices=rx_choices(user), value=None), overview_html(user)


def dose_rows(user):
    if not user or user["Role"] != "Patient":
        return [], gr.update(choices=[], value=None)
    doses = S.doses_for_date(user["User_ID"])
    rows = [[d["Med_Name"], d["Dosage"], t12(d["Dosage_Time"]), d["Priority_Level"], d["Status"]] for d in doses]
    choices = [(f"{d['Med_Name']} · {t12(d['Dosage_Time'])} ({d['Status']})", f"{d['Med_ID']}|{d['Date'].isoformat()}") for d in doses]
    return rows, gr.update(choices=choices, value=None)


def mark(user, pick, status):
    try:
        if not pick:
            raise ValidationError("Please choose a dose first.")
        med_id, day = pick.split("|")
        S.set_dose_status(user["User_ID"], med_id, status, date.fromisoformat(day),
                          int(S.get_profile(user["User_ID"])["Snooze_Min"]))
        msg = ok("Marked as taken. Well done!" if status == "Taken" else "Marked as missed.")
    except Exception as e:
        msg = err(e)
    rows, pick_update = dose_rows(user)
    return msg, rows, pick_update, overview_html(user)


def log_exercise(user, kind, minutes, km, steps):
    try:
        S.log_activity(user["User_ID"], kind, minutes, km, steps or None)
        msg = ok("Activity saved. Great job!")
    except Exception as e:
        msg = err(e)
    return msg, overview_html(user)


def bmi(height, weight):
    try:
        h = validate_number(height, "Height (cm)", 50, 250)
        w = validate_number(weight, "Weight (kg)", 10, 300, integer=False)
    except ValidationError as e:
        return err(e)
    value = w / (h / 100) ** 2
    band = ("below the usual range" if value < 18.5 else "within the usual range" if value < 25
            else "above the usual range" if value < 30 else "well above the usual range")
    return (f'<div class="dc-card"><div class="l">Body mass index</div><div class="b">{value:.1f}</div>'
            f'<div class="s">This is {band} for adults. It is only a general guide — ask a health worker about your own targets.</div></div>')


def save_body(user, height, weight):
    try:
        S.save_profile(user["User_ID"], Height_Cm=height, Weight_Kg=weight)
        return ok("Height and weight saved to your profile.")
    except Exception as e:
        return err(e)


def save_photo(user, path):
    try:
        if not path:
            raise ValidationError("Please choose a photo first.")
        I.save_profile_photo(user["User_ID"], path)
        return ok("Profile photo updated."), header_html(user)
    except Exception as e:
        return err(e), header_html(user)


# ======================================================================= layout
with gr.Blocks(title="DrukCare Prescription Portal") as demo:
    user_state = gr.State(None)
    header = gr.HTML(header_html())

    # ---------------- login / register
    with gr.Group(visible=True) as auth_group:
        with gr.Tabs():
            with gr.Tab("Log in"):
                li_user = gr.Textbox(label="Username or CID", placeholder="e.g. sonam_p or 10805001234")
                li_pass = gr.Textbox(label="Password", type="password")
                li_btn = gr.Button("Log in", variant="primary")
                li_msg = gr.HTML()
            with gr.Tab("Create account"):
                with gr.Row():
                    rg_name = gr.Textbox(label="Full name")
                    rg_cid = gr.Textbox(label="CID (11 digits)", max_lines=1, placeholder="e.g. 10805001234")
                with gr.Row():
                    rg_user = gr.Textbox(label="Username (3-20 letters, numbers, _)")
                    rg_role = gr.Dropdown(S.ROLES, value="Patient", label="I am a")
                with gr.Row():
                    rg_pass = gr.Textbox(label="Password (at least 6 characters)", type="password")
                    rg_pass2 = gr.Textbox(label="Confirm password", type="password")
                rg_btn = gr.Button("Create account", variant="primary")
                rg_msg = gr.HTML()

    # ---------------- main app
    with gr.Group(visible=False) as main_group:
        with gr.Row():
            gr.HTML("")
            logout_btn = gr.Button("Log out", size="sm", scale=0)
        with gr.Tabs():
            with gr.Tab("🏠 Overview") as tab_overview:
                overview = gr.HTML()
                refresh_btn = gr.Button("Refresh", size="sm")
            with gr.Tab("📝 Prescription Generator") as tab_gen:
                gr.Markdown("Fill in the form. Every field is validated before it is saved to the shared CSV files.")
                gen_patient = gr.Dropdown(choices=[], label="Patient", info="Your linked patients. Link a new one in the Streamlit dashboard: My Patients → View patient (username + CID)",
                                          visible=False)
                with gr.Row():
                    gen_date = gr.Textbox(label="Prescription date (YYYY-MM-DD)", value=date.today().isoformat())
                    gen_note = gr.Textbox(label="Diagnosis / note (optional)", max_lines=1)
                cells = []
                for n in range(1, 5):
                    with gr.Row():
                        a = gr.Dropdown(C.MEDICINES, value=None, label=f"Medicine {n}" + ("" if n == 1 else " (optional)"), filterable=True)
                        b = gr.Dropdown(C.DOSAGE_OPTIONS, value=None, label="Dosage", allow_custom_value=True)
                        c = gr.Dropdown(S.FREQUENCIES, value="Once daily", label="Frequency")
                        d = gr.Number(label="Days", value=7 if n == 1 else None, precision=0)
                    # choosing a medicine fills in its usual dosage automatically
                    a.change(lambda m: C.MEDICINE_DOSES.get(m or "", None), a, b)
                    cells += [a, b, c, d]
                gen_btn = gr.Button("Validate & save prescription", variant="primary")
                gen_msg = gr.HTML()
                gen_summary = gr.HTML()
                with gr.Row():
                    gen_file = gr.File(label="Download printable summary (HTML)")
                    gen_print = gr.Button("🖨️ Print this summary")
            with gr.Tab("📋 Prescriptions") as tab_rx:
                rx_df = gr.Dataframe(headers=["Medicine", "Dosage", "Frequency", "Days", "Prescribed on", "Status", "Patient", "By", "In schedule"],
                                     interactive=False, wrap=True)
                rx_pick = gr.Dropdown(label="Choose a prescription", choices=[])
                with gr.Row():
                    rx_view = gr.Button("👁 View / print summary")
                    rx_del = gr.Button("🗑 Delete (only your own)", variant="stop")
                with gr.Row():
                    sch_time = gr.Dropdown(choices=time_choices(15), value="8:00 AM", allow_custom_value=True,
                                           label="First dose time", info="AM = morning, PM = afternoon / evening")
                    sch_prio = gr.Dropdown(S.PRIORITIES, value="Medium", label="Priority colour")
                    sch_btn = gr.Button("📅 Add to my schedule", variant="primary")
                rx_msg = gr.HTML()
                rx_summary = gr.HTML()
                with gr.Row():
                    rx_file = gr.File(label="Printable summary")
                    rx_print = gr.Button("🖨️ Print this summary")
            with gr.Tab("💊 Today's Medication") as tab_meds:
                dose_df = gr.Dataframe(headers=["Medicine", "Dosage", "Time", "Priority", "Status"], interactive=False)
                dose_pick = gr.Dropdown(label="Choose a dose", choices=[])
                with gr.Row():
                    taken_btn = gr.Button("✓ Mark as taken", variant="primary")
                    missed_btn = gr.Button("✗ Mark as missed")
                dose_msg = gr.HTML()
            with gr.Tab("🏃 Exercise Log") as tab_ex:
                with gr.Row():
                    ex_kind = gr.Dropdown(S.ACTIVITY_TYPES, value="Walking", label="Activity")
                    ex_min = gr.Number(label="Duration (min)", value=30, precision=0)
                    ex_km = gr.Number(label="Distance (km)", value=0)
                    ex_steps = gr.Number(label="Steps (0 = estimate)", value=0, precision=0)
                ex_btn = gr.Button("Save activity", variant="primary")
                ex_msg = gr.HTML()
            with gr.Tab("🧮 Health Tools") as tab_tools:
                with gr.Row():
                    bmi_h = gr.Number(label="Height (cm)", value=158, precision=0)
                    bmi_w = gr.Number(label="Weight (kg)", value=52)
                with gr.Row():
                    bmi_btn = gr.Button("Calculate BMI", variant="primary")
                    bmi_save = gr.Button("Save to my profile")
                bmi_out = gr.HTML()
            with gr.Tab("👤 Account") as tab_acct:
                gr.Markdown("Replace your profile photo (JPG, PNG or WEBP).")
                photo = gr.Image(type="filepath", sources=["upload"], label="Profile photo", height=240)
                photo_btn = gr.Button("Save photo", variant="primary")
                photo_msg = gr.HTML()

    # ---------------- wiring
    all_tabs = [tab_overview, tab_gen, tab_rx, tab_meds, tab_ex, tab_tools, tab_acct]

    def enter_app(user):
        """Show/hide parts of the page depending on who is logged in."""
        if not user:
            return ([gr.update(visible=True), gr.update(visible=False), header_html(None), gr.update(visible=False)]
                    + [gr.update(visible=True)] * len(all_tabs))
        role = user["Role"]
        patient = role == "Patient"
        vis = [True, role in ("Provider", "Patient"), role in ("Provider", "Patient"), patient, patient, patient, True]
        return ([gr.update(visible=False), gr.update(visible=True), header_html(user),
                 gr.update(visible=role == "Provider", choices=S.patient_choices(user["User_ID"]) if user else [], value=None)]
                + [gr.update(visible=v) for v in vis])

    def load_data(user):
        if not user:
            return ([], gr.update(choices=[], value=None), "", [], gr.update(choices=[], value=None))
        rx_update = refresh_rx(user)
        dr, dp = dose_rows(user)
        return rx_update[0], rx_update[1], rx_update[2], dr, dp

    enter_outputs = [auth_group, main_group, header, gen_patient] + all_tabs
    load_outputs = [rx_df, rx_pick, overview, dose_df, dose_pick]

    for btn, fn, ins, msg in ((li_btn, do_login, [li_user, li_pass], li_msg),
                              (rg_btn, do_register, [rg_name, rg_cid, rg_user, rg_pass, rg_pass2, rg_role], rg_msg)):
        btn.click(fn, ins, [user_state, msg]).then(enter_app, user_state, enter_outputs).then(load_data, user_state, load_outputs)
    li_pass.submit(do_login, [li_user, li_pass], [user_state, li_msg]).then(enter_app, user_state, enter_outputs).then(load_data, user_state, load_outputs)
    logout_btn.click(do_logout, None, [user_state, li_msg, rg_msg]).then(enter_app, user_state, enter_outputs)
    refresh_btn.click(load_data, user_state, load_outputs)

    gen_btn.click(generate, [user_state, gen_patient, gen_date, gen_note] + cells, [gen_msg, gen_summary, gen_file]).then(load_data, user_state, load_outputs)
    for printer in (gen_print, rx_print):
        printer.click(None, None, None, js="() => window.print()")
    rx_view.click(view_summary, [user_state, rx_pick], [rx_summary, rx_file, rx_msg])
    sch_btn.click(schedule, [user_state, rx_pick, sch_time, sch_prio], rx_msg).then(load_data, user_state, load_outputs)
    rx_del.click(delete_item, [user_state, rx_pick], rx_msg).then(load_data, user_state, load_outputs)
    taken_btn.click(lambda u, p: mark(u, p, "Taken"), [user_state, dose_pick], [dose_msg, dose_df, dose_pick, overview])
    missed_btn.click(lambda u, p: mark(u, p, "Missed"), [user_state, dose_pick], [dose_msg, dose_df, dose_pick, overview])
    ex_btn.click(log_exercise, [user_state, ex_kind, ex_min, ex_km, ex_steps], [ex_msg, overview])
    bmi_btn.click(bmi, [bmi_h, bmi_w], bmi_out)
    bmi_save.click(save_body, [user_state, bmi_h, bmi_w], bmi_out)
    photo_btn.click(save_photo, [user_state, photo], [photo_msg, header])


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=C.GRADIO_PORT, inbrowser="--no-browser" not in sys.argv,
                js="() => { document.body.classList.remove('dark'); }",
                favicon_path=(str(I.find_image(C.LOGO)) if I.find_image(C.LOGO) else None),
                theme=THEME, css=CSS, allowed_paths=[str(C.DATA_DIR)], show_error=True)
