"""DrukCare - Streamlit web app (the main, most complete version).

Run with:   streamlit run app.py

Role of Streamlit in this project (see the proposal):
  * login + create-account with validation
  * Home, Medication, Exercise, Prescriptions, Analytics, My Profile
  * weekly / monthly analytics charts for patients AND family caregivers
    (a caregiver picks a patient from the list - read-only; there is no account linking)
All data lives in the shared CSV files inside the data/ folder.

HOW TO USE YOUR OWN PHOTOS: open drukcare_core/config.py (block "IMAGE PATHS")
or just save your pictures in the assets/ folder using the file names listed there.
"""
import math
import re
from datetime import date, datetime, time, timedelta
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from drukcare_core import config as C
from drukcare_core import images as I
from drukcare_core import seed, storage
from drukcare_core import services as S
from drukcare_core.validators import ValidationError, live_check, time_choices, time_label, validate_time

st.set_page_config(page_title="DrukCare", page_icon=(I.logo_image(64) or "🌿"), layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_resource
def _boot():
    storage.init_storage()
    seed.remove_demo_data()    # deletes the old fictional demo accounts if they still exist
    return True


_boot()

# ======================================================================= CSS
CSS = f"""
<style>
:root {{ --navy:{C.NAVY}; --emerald:{C.EMERALD}; --ivory:{C.IVORY}; --text:{C.TEXT}; --muted:{C.MUTED}; --border:{C.BORDER}; }}
.stApp {{ background:{C.IVORY}; color:var(--text); }}
.stApp h1,.stApp h2,.stApp h3,.stApp p,.stApp label,.stApp li {{ color:{C.TEXT}; }}
[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stToolbar"], #MainMenu, footer {{ visibility:hidden; }}
.block-container {{ padding-top:1rem; padding-bottom:2rem; max-width:1280px; }}
/* ---------- sidebar */
[data-testid="stSidebar"] {{ background:linear-gradient(180deg,{C.NAVY} 0%,{C.NAVY_DARK} 100%); min-width:250px; }}
[data-testid="stSidebar"] * {{ color:#E8F5F4; }}
[data-testid="stSidebar"] .stButton > button {{ background:transparent; border:none; width:100%; justify-content:flex-start;
   padding:.62rem .95rem; border-radius:14px; font-size:1.02rem; box-shadow:none; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background:rgba(255,255,255,.10); }}
[data-testid="stSidebar"] .stButton > button[kind="primary"], [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {{
   background:{C.NAV_ACTIVE}; color:white; font-weight:600; box-shadow:0 4px 14px rgba(0,0,0,.25); }}
[data-testid="stSidebar"] .stButton > button p {{ text-align:left; }}
.logo {{ display:flex; flex-direction:column; align-items:center; text-align:center; margin:.2rem 0 1rem; }}
.logo img.lg {{ width:100%; height:auto; border-radius:0; }}
.logo .nm {{ font-family:'Palatino Linotype','Book Antiqua',Georgia,serif; font-size:2.1rem; font-weight:700; line-height:1.05; color:#fff; }}
.logo .d, .logo .c {{ color:#fff; }}
.logo .tg {{ font-size:.74rem; color:#CFE9E7; margin-top:4px; }}
.side-foot {{ text-align:center; margin-top:1rem; opacity:.9; font-size:.78rem; line-height:1.3; }}
.side-dragon {{ width:100%; margin-top:.4rem; opacity:.9; }}
/* ---------- banner */
.banner {{ position:relative; height:240px; border-radius:20px; overflow:hidden; background-repeat:no-repeat;
   background-size:cover; background-position:right center; display:flex; align-items:center;
   box-shadow:0 6px 22px rgba(0,60,70,.12); margin-bottom:1rem; }}
.banner .txt {{ position:relative; margin-left:22px; padding:18px 28px; max-width:58%; border-radius:18px;
   background:rgba(250,254,254,.80); border:2px solid rgba(255,255,255,.9); backdrop-filter:blur(3px); }}
.banner .bt {{ font-family:'Palatino Linotype','Book Antiqua',Georgia,serif; font-style:italic; font-weight:700; font-size:2.35rem; line-height:1.08; color:{C.TEXT}; }}
.banner .bs {{ color:{C.TEXT}; margin-top:.35rem; font-size:1.02rem; font-style:italic; }}
.topbar {{ position:absolute; top:12px; right:18px; display:flex; align-items:center; gap:14px; background:rgba(255,255,255,.92);
   backdrop-filter:blur(6px); padding:5px 12px 5px 8px; border-radius:40px; box-shadow:0 2px 10px rgba(0,60,70,.12); color:{C.TEXT}; }}
/* clickable bell: a real Streamlit popover placed in the banner's top-right corner */
.st-key-bannerwrap {{ position:relative; gap:0 !important; }}
.st-key-bannerwrap > .st-key-bellpop, .st-key-bannerwrap > div:has(> .st-key-bellpop) {{
   position:absolute !important; top:12px; right:18px; z-index:20; width:auto !important; }}
.st-key-bellpop button {{ border-radius:40px !important; background:rgba(255,255,255,.95) !important; border:none !important;
   box-shadow:0 2px 10px rgba(0,60,70,.15); min-height:44px; padding:0 14px !important; }}
.st-key-bellpop button p {{ font-weight:700; color:#D64545; }}
.banner .topbar {{ right:104px; }}
.chip {{ display:flex; align-items:center; gap:8px; font-weight:600; font-size:.88rem; color:{C.TEXT}; }}
.chip img {{ width:32px; height:32px; border-radius:50%; object-fit:cover; }}
.chip small {{ display:block; font-weight:400; color:{C.MUTED}; font-size:.7rem; margin-top:-2px; }}
/* ---------- cards */
[class*="st-key-card"] {{ background:{C.CARD}; border:1px solid {C.BORDER}; border-radius:18px; padding:16px 18px;
   box-shadow:0 4px 16px rgba(0,60,70,.07); }}
.st-key-card_tint_blue {{ background:{C.TINT_BLUE}; }} .st-key-card_tint_mint, .st-key-card_tint_mint2 {{ background:{C.TINT_MINT}; }} .st-key-card_tint_peach {{ background:{C.TINT_PEACH}; }}
.cardtitle {{ display:flex; align-items:center; gap:10px; font-family:'Palatino Linotype','Book Antiqua',Georgia,serif; font-size:1.2rem; font-weight:700; color:{C.TEXT}; margin-bottom:.5rem; }}
.cardtitle .ic {{ color:{C.EMERALD}; font-size:1.25rem; }}
.lbl {{ color:{C.EMERALD_DARK}; font-size:.84rem; font-weight:700; letter-spacing:.2px; margin-bottom:.35rem; }}
.big {{ font-size:1.45rem; font-weight:700; color:{C.TEXT}; line-height:1.2; }}
.big small {{ font-size:.9rem; color:{C.MUTED}; font-weight:500; }}
.sub {{ color:{C.MUTED}; font-size:.88rem; margin-top:.2rem; }}
.pill {{ display:inline-block; padding:2px 11px; border-radius:20px; font-size:.76rem; font-weight:600; white-space:nowrap; }}
.bar {{ height:9px; border-radius:6px; background:{C.TRACK}; margin:.55rem 0 .25rem; overflow:hidden; }}
.bar i {{ display:block; height:100%; background:linear-gradient(90deg,{C.EMERALD},{C.TEAL_LIGHT}); border-radius:6px; }}
.pillicon {{ width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:1.3rem; }}
.stat {{ display:flex; align-items:center; gap:14px; }}
.stat .si {{ width:56px; height:56px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.7rem; color:#fff; flex:none; }}
.stat .sv {{ font-family:'Palatino Linotype',Georgia,serif; font-size:2.2rem; font-weight:700; line-height:1; color:{C.TEXT}; }}
.stat .sn {{ font-family:'Palatino Linotype',Georgia,serif; font-size:.95rem; font-weight:700; color:{C.TEXT}; }}
.proverb {{ position:relative; border-radius:18px; overflow:hidden; background-repeat:no-repeat; background-size:contain, cover;
   background-position:right center, center; min-height:180px; display:flex; align-items:center;
   box-shadow:0 4px 16px rgba(0,60,70,.10); }}
.proverb div {{ position:relative; margin-left:18px; padding:18px 28px; border-radius:16px; background:rgba(250,254,254,.8); font-family:'Palatino Linotype',Georgia,serif; font-style:italic; font-size:1.55rem; color:{C.TEXT}; }}
.proverb span {{ display:block; font-size:.95rem; color:{C.MUTED}; font-style:normal; margin-top:6px; }}
.empty {{ text-align:center; padding:26px 10px; color:{C.MUTED}; }} .empty b {{ color:{C.TEXT}; display:block; margin:.4rem 0; font-size:1.05rem; }}
.th {{ color:{C.MUTED}; font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.4px; padding:0 .2rem; }}
.note {{ color:{C.MUTED}; font-size:.8rem; text-align:center; margin-top:1.5rem; }}
.sample {{ background:#FFF4D6; border:1px solid #F0D78A; color:#7A5B00; border-radius:10px; padding:6px 12px; font-size:.82rem; margin-bottom:.7rem; }}
.medrow {{ display:flex; align-items:center; gap:12px; padding:9px 0; border-bottom:1px solid {C.BORDER}; }}
.medrow:last-child {{ border-bottom:none; }}
.medrow .mi {{ width:42px; height:42px; border-radius:12px; background:{C.TINT_MINT}; display:flex; align-items:center; justify-content:center; font-size:1.25rem; flex:none; }}
.step {{ display:flex; align-items:center; gap:12px; padding:8px 0; }}
.step .dot {{ width:22px; height:22px; border-radius:50%; border:2px solid {C.TRACK}; flex:none; display:flex; align-items:center; justify-content:center; font-size:.72rem; color:#fff; }}
.step .dot.ok {{ background:{C.EMERALD}; border-color:{C.EMERALD}; }}
.step .dot.late {{ background:#D64545; border-color:#D64545; }}
.quick {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }}
.quick div {{ background:{C.TINT_MINT}; border:1px solid {C.BORDER}; border-radius:14px; text-align:center; padding:12px 6px; font-size:.85rem; font-weight:600; color:{C.TEXT}; }}
.quick span {{ display:block; font-size:1.5rem; margin-bottom:2px; }}
.mascot {{ position:absolute; right:0; bottom:0; height:165px; border-radius:18px 0 18px 0; }}
/* ---------- widgets */
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {{ background:{C.EMERALD}; border:none; color:#fff; border-radius:12px; font-weight:600; }}
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{ background:{C.EMERALD_DARK}; color:#fff; }}
.stButton > button, [data-testid="stBaseButton-secondary"] {{ border-radius:12px; border-color:{C.BORDER}; background:#fff; color:{C.TEXT}; }}
[data-testid="stSidebar"] .stButton > button[kind="secondary"], [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{ background:transparent; color:#E8F5F4; }}
.stTabs [aria-selected="true"] p {{ color:{C.EMERALD_DARK} !important; font-weight:700; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:{C.EMERALD}; height:3px; }}
[data-testid="stSidebar"] .stButton > button > div {{ justify-content:flex-start; }}
[data-testid="stForm"] {{ background:{C.CARD}; border:1px solid {C.BORDER}; border-radius:18px; }}
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stDateInputField"], [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{ background:{C.SURFACE} !important; border-color:{C.BORDER} !important; }}
[data-baseweb="input"] input, [data-baseweb="base-input"] input, textarea {{ color:{C.TEXT} !important; background:transparent !important; }}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {{ color:#E8F5F4 !important; }}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primary"] span, [data-testid="stBaseButton-primaryFormSubmit"] p, [data-testid="stBaseButton-primaryFormSubmit"] span {{ color:#fff !important; }}
[data-testid="stBaseButton-primaryFormSubmit"] {{ background:{C.EMERALD}; border:none; border-radius:12px; }}
.banner.hero {{ height:auto; aspect-ratio:2448/864; min-height:260px; border-radius:22px; background-size:cover; background-position:center; }}
.banner.hero .txt {{ padding:22px 32px; }}
.banner.hero .bw {{ font-family:'Palatino Linotype',Georgia,serif; font-size:2.3rem; line-height:1.1; color:{C.TEXT}; }}
.banner.hero .bn {{ font-family:'Palatino Linotype',Georgia,serif; font-size:3.1rem; font-weight:800; line-height:1.05; color:{C.TEXT}; }}
.banner.hero .bs {{ font-family:'Palatino Linotype',Georgia,serif; font-size:1.35rem; margin-top:.5rem; }}
.swoosh {{ width:250px; height:5px; border-radius:5px; margin-top:6px; background:linear-gradient(90deg,{C.EMERALD},transparent); }}
.stat .si {{ width:54px; height:54px; border-radius:50%; background:{C.EMERALD}; color:#fff; display:flex; align-items:center; justify-content:center; font-size:1.5rem; flex:none; }}
.stat .up {{ font-family:'Source Sans Pro',sans-serif; font-size:.8rem; color:{C.EMERALD}; font-weight:600; }}
[class*="st-key-card_stat"] {{ background:linear-gradient(135deg,#F7FDFD 0%,{C.TINT_MINT} 100%); padding:12px 16px; }}
[class*="st-key-card_stat"] button, [class*="st-key-card_stat"] [data-testid="stBaseButton-secondary"] {{ background:transparent !important; border:none !important; color:{C.EMERALD_DARK} !important; padding:0 !important; min-height:0; font-size:.82rem; box-shadow:none; }}
[class*="st-key-card_stat"] button p {{ color:{C.EMERALD_DARK} !important; font-size:.82rem; }}
[class*="st-key-card_nav"] {{ padding:0 0 14px; overflow:hidden; background:linear-gradient(180deg,{C.TINT_MINT} 0%,#fff 62%); }}
.navpic {{ aspect-ratio:640/330; min-height:150px; background-size:cover; background-position:center; display:flex; align-items:center; justify-content:center; border-radius:16px 16px 0 0; }}
.navpic .av {{ width:104px; height:104px; border-radius:50%; object-fit:cover; border:3px solid #fff; box-shadow:0 2px 10px rgba(0,60,70,.2); }}
.navt {{ text-align:center; font-family:'Palatino Linotype',Georgia,serif; font-size:1.2rem; font-weight:700; margin-top:.2rem; color:{C.TEXT}; }}
.navd {{ text-align:center; font-size:.8rem; color:{C.MUTED}; padding:2px 12px 8px; min-height:42px; }}
[class*="st-key-card_nav"] .stButton {{ padding:0 16px; }}
[class*="st-key-card_nav"] button {{ background:{C.NAVY_DARK} !important; border:none !important; border-radius:22px !important; }}
[class*="st-key-card_nav"] button p {{ color:#fff !important; font-size:.82rem; font-weight:600; }}
.rem {{ display:flex; align-items:center; gap:12px; padding:9px 0; }}
.rem .mi {{ font-size:1.3rem; width:34px; text-align:center; }}
.rem .chk {{ width:30px; height:30px; border-radius:50%; border:2px solid {C.TRACK}; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; }}
.rem .chk.on {{ background:{C.EMERALD}; border-color:{C.EMERALD}; }}
.quote {{ position:relative; border-radius:20px; background-size:cover; background-position:center; min-height:300px; display:flex; align-items:center; justify-content:center;
   text-align:center; color:#fff; font-family:'Palatino Linotype',Georgia,serif; font-style:italic; font-size:1.45rem; line-height:1.3; padding:24px; box-shadow:0 4px 16px rgba(0,60,70,.15); overflow:hidden; }}
.quote:before {{ content:""; position:absolute; inset:0; background:linear-gradient(180deg,rgba(0,60,70,.35),rgba(0,60,70,.55)); }}
.quote div {{ position:relative; }} .quote .knot {{ display:block; font-size:2rem; font-style:normal; margin-bottom:.5rem; }}
.quote small {{ display:block; font-size:.95rem; margin-top:.7rem; font-style:normal; }}
.waves {{ height:130px; border-radius:18px; background-size:cover; background-position:0 86%; margin-top:1.4rem; display:flex; align-items:center; justify-content:center; }}
.waves span {{ background:rgba(255,255,255,.75); padding:3px 18px; border-radius:20px; color:{C.TEXT}; font-weight:600; font-size:.9rem; }}
.js-plotly-plot .plotly .modebar {{ display:none !important; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ==================================================================== helpers
def h(markup: str) -> str:
    """Collapse whitespace so Streamlit's markdown never turns HTML into a code block."""
    return re.sub(r"\n\s*", "", markup)


def html(markup: str):
    st.markdown(h(markup), unsafe_allow_html=True)


def flash(message: str, icon: str = "✅"):
    st.session_state["flash"] = (message, icon)
    # remember it for the bell's "Recent" list: (time, icon, message, read?)
    recent = st.session_state.setdefault("recent", [])
    recent.append((datetime.now().strftime("%I:%M %p").lstrip("0"), icon, message, False))
    del recent[:-20]


def clean_error(err: Exception) -> str:
    return str(err) if isinstance(err, (ValidationError, storage.StorageError)) else f"Something went wrong: {err}"


def t12(hhmm: str) -> str:
    return time_label(hhmm)            # '20:15' -> '8:15 PM'


def time_select(where, label, hhmm, key):
    """AM/PM time drop-down (15-minute steps; type to search, e.g. '8:3'). Returns 'HH:MM' for saving."""
    choices = time_choices(15)
    current = time_label(hhmm)
    if current not in choices:                   # an older time such as 8:10 AM stays selectable
        choices = sorted(choices + [current], key=validate_time)
    picked = where.selectbox(label, choices, index=choices.index(current), key=key,
                             help="Times are shown with AM (morning) and PM (afternoon / evening).")
    return validate_time(picked)


def pill(text: str, color: str, bg: str = None) -> str:
    bg = bg or color + "22"
    return f'<span class="pill" style="color:{color};background:{bg}">{escape(text)}</span>'


def priority_pill(priority: str) -> str:
    return pill(f"{priority} priority", C.PRIORITY_COLORS[priority], C.PRIORITY_BG[priority])


def status_pill(status: str) -> str:
    return pill(status, C.STATUS_COLORS.get(status, C.MUTED))


def ring(pct: int, size: int = 112, stroke: int = 12) -> str:
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    off = circ * (1 - max(0, min(100, pct)) / 100)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{C.TRACK}" stroke-width="{stroke}"/>'
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{C.EMERALD}" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}" '
            f'transform="rotate(-90 {size/2} {size/2})"/>'
            f'<text x="50%" y="50%" text-anchor="middle" dy=".35em" font-size="{size*0.21:.0f}" font-weight="700" '
            f'fill="{C.TEXT}">{pct}%</text></svg>')


def bar(pct: int) -> str:
    return f'<div class="bar"><i style="width:{max(0, min(100, pct))}%"></i></div>'


def current() -> dict:
    return st.session_state["user"]


def viewer_id():
    """Whose health data is on screen: yourself, or (for caregivers) the chosen patient."""
    u = current()
    if u["Role"] == "Patient":
        return u["User_ID"]
    if u["Role"] in ("Caregiver", "Provider"):           # read-only view of a linked patient
        vid = st.session_state.get("viewing_id")
        return vid if vid and S.is_linked(u["User_ID"], vid) else None
    return None


def readonly() -> bool:
    return viewer_id() != current()["User_ID"]


def viewer_name() -> str:
    vid = viewer_id()
    user = S.get_user(vid) if vid else None
    return user["Full_Name"] if user else ""


def go_to(page: str):
    st.session_state["page"] = page


def initials(name: str) -> str:
    return "".join(w[0] for w in name.replace("Dr.", "").split()[:2]).upper() or "DC"


def avatar_uri(user: dict, size=96) -> str:
    return I.data_uri(I.profile_photo_path(user["User_ID"]), (size, size), circle=True,
                      initials=initials(user["Full_Name"]))


def logo_img(height: int) -> str:
    uri = I.logo_uri(height)
    return f'<img src="{uri}" alt="DrukCare logo" style="height:{height}px">' if uri else ""


def banner(page: str, title: str, subtitle: str):
    u = current()
    path = C.PAGE_BANNERS[page]          # whole photo on the right + its own colours behind the title
    bg = f"url('{I.card_uri(path)}')"
    show_banner(f"""<div class="banner" style="background-image:{bg}">
      <div class="txt"><div class="bt">{escape(title)}</div><div class="bs">{escape(subtitle)}</div></div>
      <div class="topbar"><div class="chip"><img src="{avatar_uri(u, 64)}"><div>{escape(u['Full_Name'])}<small>{u['Role']}</small></div></div></div></div>""")


def show_banner(markup):
    """Banner picture + the clickable notification bell on top of it (top-right corner)."""
    with st.container(key="bannerwrap"):
        html(markup)
        bell()


def bell():
    """🔔 button with a red count. Clicking it opens the notifications panel."""
    vid = viewer_id()
    data = S.notifications(vid) if vid else {"count": 0, "attention": [], "upcoming": [], "activity": [], "messages": []}
    if vid and readonly():                       # a patient's messages are private to the patient
        data["count"] -= len(data["messages"])
        data["messages"] = []
    recent = st.session_state.get("recent", [])
    unread = sum(1 for r in recent if not r[3])
    count = data["count"] + unread
    with st.container(key="bellpop"):
        with st.popover(f"🔔 {count}" if count else "🔔", help="Notifications"):
            notification_panel(vid, data, recent)


def read_messages(uid):
    S.mark_messages_read(uid)
    flash("Messages marked as read.", "📨")


def notification_panel(vid, data, recent):
    st.markdown("**Notifications**")
    if data.get("messages"):
        st.markdown(":blue[**New messages**]")
        for m in data["messages"]:
            body = "<br>".join(escape(line) for line in m["Body"].splitlines())
            html(f'<div style="background:#EAF5F9;border-radius:10px;padding:8px 10px;margin:4px 0">'
                 f'📨 <b>{escape(m["Title"])}</b><div class="sub">{body}</div>'
                 f'<div class="sub"><small>{escape(m["Sender_Name"])} · {escape(m["Sent_At"][:16])}</small></div></div>')
        st.button("Mark messages as read", key="nt_msgread", on_click=read_messages, args=(vid,))
    if vid and readonly():
        st.caption(f"For {viewer_name()} (read-only)")
    if not vid:
        st.caption("Medicine and exercise notifications appear here once you are viewing a patient.")
    if data["attention"]:
        st.markdown(":red[**Needs attention**]")
        for d in data["attention"]:
            c = st.columns([3, 1, 1], vertical_alignment="center")
            c[0].markdown(h(f'⏰ <b>{escape(d["Med_Name"])}</b> <span class="sub">{escape(d["Dosage"])} · '
                            f'{t12(d["Dosage_Time"])} · {d["When"]}</span>'), unsafe_allow_html=True)
            if not readonly():
                c[1].button("Taken", key=f"nt_t_{d['Med_ID']}", type="primary",
                            on_click=mark_dose, args=(vid, d["Med_ID"], d["Date"], "Taken"))
                c[2].button("Snooze", key=f"nt_s_{d['Med_ID']}",
                            on_click=mark_dose, args=(vid, d["Med_ID"], d["Date"], "Snoozed"))
    if data["upcoming"]:
        st.markdown("**Later today**")
        for d in data["upcoming"][:5]:
            extra = f" · snoozed until {t12(d['Snooze_Until'])}" if d["Status"] == "Snoozed" and d["Snooze_Until"] else ""
            html(f'<div class="sub">💊 <b>{escape(d["Med_Name"])}</b> at {t12(d["Dosage_Time"])}{extra}</div>')
    if data["activity"]:
        st.markdown("**Today**")
        for a in data["activity"]:
            html(f'<div class="sub">{a["icon"]} {escape(a["text"])} {escape(a["detail"])}</div>')
    if recent:
        st.markdown("**Recent**")
        for when, icon, msg, _ in reversed(recent[-6:]):
            html(f'<div class="sub">{icon} {escape(msg)} <small>· {when}</small></div>')
        if any(not r[3] for r in recent):
            st.button("Mark all as read", key="nt_read",
                      on_click=lambda: st.session_state.update(recent=[(a, b, c, True) for a, b, c, _ in recent]))
    if vid and not (data["attention"] or data["upcoming"] or data["activity"] or recent):
        st.caption("Nothing new. You're all caught up 🎉")


def footer():
    w = I.data_uri(C.WAVES, (1400, 160), label="")
    html(f'<div class="waves" style="background-image:url(\'{w}\')"><span>DrukCare &nbsp;•&nbsp; {escape(C.TAGLINE)}</span></div>')


def need_patient() -> bool:
    """Show a friendly message when there is no patient data to display."""
    if viewer_id():
        if readonly():
            st.info(f"👁️ You are viewing **{viewer_name()}** (read-only). Change patient from the sidebar.")
        return True
    if current()["Role"] in ("Caregiver", "Provider"):
        st.info("No patient chosen yet. Open **My Patients** → **View patient** and enter the patient's username and CID.")
        st.button("Open My Patients →", type="primary", on_click=go_to, args=("My Patients",), key="np_go")
    else:
        st.info("This page shows a patient's health data. Providers can use the Prescriptions page.")
    return False


def sample_note():
    """Demo accounts were removed - nothing to show."""
    return None


# =================================================================== sign in
def auth_screen():
    bg = I.data_uri(C.LOGIN_FULL, (1672, 941), label=f"Add your photo: {C.LOGIN_FULL}", quality=88)
    st.markdown(f"""<style>[data-testid='stSidebar']{{display:none}}
      .block-container{{max-width:1500px;padding-top:1rem}}
      /* The picture box keeps the photo's shape as a MINIMUM size, but grows taller when the
         Create-account form (with its live messages) needs more room - so nothing hides behind the footer.
         The photo is always scaled by WIDTH only ("100% auto"), so the DrukCare logo in it keeps the same
         size and place on both tabs; any extra height below the photo is a soft teal fill (2nd layer). */
      .st-key-loginwrap{{background:url('{bg}') center top/100% auto no-repeat,
         linear-gradient(180deg, #CFEBEC 0%, #E6F5F5 45%, #F4FBFB 100%);border-radius:22px;height:auto;
         min-height:max(560px, calc((min(100vw, 1500px) - 6rem) * 941 / 1672));
         padding:14.5% 4.5% 2.5rem 0;box-shadow:0 8px 28px rgba(0,60,70,.15);overflow:visible;}}
      .st-key-loginform{{background:#F4FBFB;border:2px solid #9BD3D2;border-radius:22px;padding:22px 28px 18px;}}
      .st-key-loginform [role="tablist"]{{gap:10px !important;border:none !important;box-shadow:none !important;background:transparent !important}}
      .st-key-loginform [data-testid="stTab"]{{flex:1;justify-content:center;background:#E3F1F2 !important;border-radius:12px !important;height:46px !important;margin:0 !important}}
      .st-key-loginform [data-testid="stTab"][aria-selected="true"]{{background:{C.EMERALD} !important}}
      .st-key-loginform [data-testid="stTab"][aria-selected="true"] p{{color:#fff !important}}
      .st-key-loginform [data-testid="stTab"] p{{font-weight:600}}
      .st-key-loginform [data-baseweb="tab-highlight"], .st-key-loginform [data-baseweb="tab-border"]{{display:none !important}}
      .st-key-loginform [data-testid="stForm"]{{border:none;background:transparent;padding:6px 0 0}}
      .livemsg{{color:#B02A2A;font-size:.8rem;line-height:1.25;margin:-.7rem 0 .2rem .1rem}}
      .liveok{{color:#1E8E5A;font-size:.8rem;line-height:1.25;margin:-.7rem 0 .2rem .1rem}}
      .loginfoot{{text-align:center;color:{C.EMERALD};letter-spacing:.12em;font-size:.78rem;margin-top:.6rem}}
    </style>""", unsafe_allow_html=True)
    with st.container(key="loginwrap"):
        _, mid = st.columns([1.45, 1])
        with mid, st.container(key="loginform"):
            tab_in, tab_up = st.tabs(["Log in", "Create account"])
            # No st.form here: a form only checks fields when its button is pressed.
            # Plain inputs re-run the page as soon as the user leaves a box (Tab, click or Enter),
            # so each message appears straight away under the box.
            with tab_in:
                username = st.text_input("Username or CID", key="li_user", placeholder="e.g. sonam_p or 10805001234")
                live_msg("login_username", username, "li_tried")
                password = st.text_input("Password", type="password", key="li_pw")
                if st.session_state.get("li_tried") and not password:
                    html('<div class="livemsg">⚠ Password is required</div>')
                if st.button("Log in", type="primary", width="stretch", key="li_btn",
                             on_click=lambda: st.session_state.update(li_tried=True)):
                    if live_check("login_username", username) or not password:
                        st.error("Please fix the fields marked in red.")
                    else:
                        try:
                            st.session_state["user"] = S.authenticate(username, password)
                            st.session_state["page"] = "Home"
                            st.rerun()
                        except Exception as err:
                            st.error(clean_error(err))
            with tab_up:
                taken = lambda n: S.find_user(n) is not None
                cid_taken = lambda c: S.find_user_by_cid(c) is not None
                n1, n2 = st.columns(2)
                with n1:
                    name = st.text_input("Full name", key="su_name")
                    bad = [live_msg("name", name, "su_tried")]
                with n2:
                    cid = st.text_input("CID (11 digits)", key="su_cid", max_chars=13, placeholder="e.g. 10805001234",
                                        help="Your Bhutanese Citizenship ID. You can log in with it, and your caregiver or "
                                             "doctor needs it (with your username) to follow your progress.")
                    bad.append(live_msg("cid", cid, "su_tried", taken=cid_taken))
                c1, c2 = st.columns(2)
                with c1:
                    username = st.text_input("Username", key="su_user", help="3-20 letters, numbers or _")
                    bad.append(live_msg("username", username, "su_tried", taken=taken))
                role = c2.selectbox("I am a", S.ROLES, help="Patients track their own health. Caregivers view a patient's progress. Providers write prescriptions.")
                e1, e2 = st.columns(2)
                with e1:
                    email = st.text_input("Email (optional)", key="su_email", placeholder="name@gmail.com")
                    bad.append(live_msg("email", email, "su_tried"))
                with e2:
                    phone = st.text_input("Phone (optional)", key="su_phone", placeholder="+975 17 123456")
                    bad.append(live_msg("phone", phone, "su_tried"))
                p1, p2 = st.columns(2)
                with p1:
                    pw = st.text_input("Password", type="password", key="su_pw",
                                       help="At least 6 characters")
                    bad.append(live_msg("password", pw, "su_tried"))
                with p2:
                    pw2 = st.text_input("Confirm password", type="password", key="su_pw2")
                    bad.append(live_msg("confirm", pw2, "su_tried", password=pw))
                dob = st.date_input("Date of birth", value=None, min_value=date(1900, 1, 1), max_value=date.today())
                if st.button("Create account", type="primary", width="stretch", key="su_btn",
                             on_click=lambda: st.session_state.update(su_tried=True)):
                    if any(bad):
                        st.error("Please fix the fields marked in red.")
                    else:
                        try:
                            user = S.register_user(name, username, pw, pw2, role, dob or "", phone, cid=cid)
                            if email.strip():
                                S.save_profile(user["User_ID"], Email=email.strip())
                            st.session_state["user"] = user
                            st.session_state["page"] = "Home"
                            flash(f"Welcome to DrukCare, {user['Full_Name']}!", "🌿")
                            st.rerun()
                        except Exception as err:
                            st.error(clean_error(err))
            html('<div class="loginfoot">HEALTH &nbsp;•&nbsp; COMPASSION &nbsp;•&nbsp; CARE</div>')
    footer()


def live_msg(field, value, tried_key, **kw) -> str:
    """Show a short red message under a sign-up / log-in box as soon as the user leaves it.
    Nothing is shown for a box the user has not filled in yet, until they press the button."""
    if not value and not st.session_state.get(tried_key):
        return ""
    msg = live_check(field, value, **kw)
    if msg:
        html(f'<div class="livemsg">⚠ {escape(msg)}</div>')
    elif value and field != "login_username":
        html('<div class="liveok">✓ Looks good</div>')
    return msg


# ===================================================================== pages
def hero():
    """Large welcome banner of the dashboard."""
    u = current()
    bg = I.full_uri(C.HOME_BANNER, 1800)
    first = u["Full_Name"].replace("Dr. ", "").split()[0] if u["Full_Name"] else "friend"
    show_banner(f"""<div class="banner hero" style="background-image:url('{bg}')">
      <div class="txt"><div class="bw">Welcome back,</div><div class="bn">{escape(first)}!</div>
      <div class="bs">Take care. You&rsquo;re in good hands.</div><div class="swoosh"></div></div>
      <div class="topbar"><div class="chip"><img src="{avatar_uri(u, 64)}"><div>{escape(u['Full_Name'])}<small>{u['Role']}</small></div></div></div></div>""")


def page_home():
    u = current()
    hero()
    sample_note()
    if u["Role"] == "Provider":
        return provider_home()
    if not need_patient():
        return footer()
    vid = viewer_id()
    wk = S.week_adherence(vid)
    now = datetime.now()
    prev = S.adherence(vid, now.date() - timedelta(days=13), now.date() - timedelta(days=7), now)
    ex = S.exercise_today(vid)
    items = S.list_prescription_items(patient_id=vid)
    active_rx = [i for i in items if i["Status"] == "Active"]
    pending_rx = [i for i in active_rx if not i["Scheduled"]]
    doses = S.doses_for_date(vid)
    meds = {d["Med_Name"] for d in doses}
    todo = sum(1 for p in (ex["steps_pct"], ex["minutes_pct"], ex["km_pct"]) if p < 100)

    # ---- four stat cards
    def stat(icon, value, name, extra=""):
        return (f'<div class="stat"><div class="si">{icon}</div><div><div class="sn">{name}</div>'
                f'<div class="sv">{value}{extra}</div></div></div>')

    c1, c2, c3, c4 = st.columns(4)
    delta = wk["pct"] - prev["pct"]
    with c1, st.container(key="card_stat_1"):
        html(stat("♥", f"{wk['pct']}%", "Health Score",
                  f' <span class="up">{"↑" if delta >= 0 else "↓"} {delta:+d}%</span>'))
        st.button("View Analytics →", key="st1", on_click=go_to, args=("Analytics",))
    with c2, st.container(key="card_stat_2"):
        html(stat("💊", len(meds), "Active Medications"))
        st.button("View Details →", key="st2", on_click=go_to, args=("Medication",))
    with c3, st.container(key="card_stat_3"):
        html(stat("📅", todo, "Upcoming Exercises"))
        st.button("View Schedule →", key="st3", on_click=go_to, args=("Exercise",))
    with c4, st.container(key="card_stat_4"):
        html(stat("📄", len(pending_rx), "Pending Prescriptions"))
        st.button("View Prescriptions →", key="st4", on_click=go_to, args=("Prescriptions",))
    st.write("")

    # ---- five navigation cards with pictures
    cards = [("Medication", "Manage your medications and set reminders.", "Go to Medication"),
             ("Exercise", "Follow your exercise plan for better health.", "Go to Exercises"),
             ("Prescriptions", "View and manage your prescriptions.", "Go to Prescriptions"),
             ("Analytics", "Track your health progress with insights.", "Go to Analytics"),
             ("My Profile", "Update your profile and personal details.", "Go to Profile")]
    cols = st.columns(5)
    for col, (page, desc, btn) in zip(cols, cards):
        with col, st.container(key=f"card_nav_{page.replace(' ', '')}"):
            if page == "My Profile":
                pic = f'<div class="navpic"><img class="av" src="{avatar_uri(S.get_user(vid) or current(), 200)}"></div>'
            else:
                pic = f'<div class="navpic" style="background-image:url(\'{I.data_uri(C.NAV_IMAGES[page], (560, 300))}\')"></div>'
            label = "Exercises" if page == "Exercise" else page
            html(f'{pic}<div class="navt">{label}</div><div class="navd">{desc}</div>')
            st.button(btn + " →", key=f"nav_go_{page}", on_click=go_to, args=(page,), width="stretch")
    st.write("")

    # ---- reminders | overview | quote
    a, b, c = st.columns([1.05, 1.5, 1])
    with a, st.container(key="card_remind"):
        html('<div class="cardtitle"><span class="ic">🔔</span>Upcoming Reminders</div>')
        if not doses:
            html('<div class="empty">No medicines scheduled today.</div>')
        for d in doses[:4]:
            done = d["Status"] == "Taken"
            html(f"""<div class="rem"><div class="mi">💊</div><div style="flex:1"><b>{escape(d['Med_Name'])}</b>
              <div class="sub">{t12(d['Dosage_Time'])} • {d['Status']}</div></div>
              <div class="chk {'on' if done else ''}">{'✓' if done else ''}</div></div>""")
    with b, st.container(key="card_overview"):
        html('<div class="cardtitle"><span class="ic">📊</span>Health Overview</div>')
        data = S.analytics_data(vid, 7)
        adh = {r["date"]: r["pct"] for r in data["adherence_days"]}
        days = [e["date"] for e in data["exercise"]]
        goal = max(1, data["steps_goal"])
        x = [d.strftime("%a") for d in days]
        fig = go.Figure()
        fig.add_scatter(x=x, y=[min(100, round(100 * e["steps"] / goal)) for e in data["exercise"]], name="Steps",
                        mode="lines+markers", line=dict(color=C.TEAL_LIGHT, width=3, shape="linear"), fill="tozeroy",
                        fillcolor="rgba(31,181,165,.15)")
        fig.add_scatter(x=x, y=[adh.get(d) for d in days], name="Medication", mode="lines+markers",
                        line=dict(color="#1E78C8", width=3, shape="linear"), fill="tozeroy", fillcolor="rgba(30,120,200,.10)", connectgaps=False)
        style_fig(fig, 250)
        fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.12, x=0.3), yaxis=dict(range=[0, 100]))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with c:
        quote, who = C.WELLNESS_MESSAGES[date.today().toordinal() % len(C.WELLNESS_MESSAGES)]
        qbg = I.data_uri(C.BANNER_BACKGROUND, (900, 520), label="")
        html(f"""<div class="quote" style="background-image:url('{qbg}')"><div>&ldquo;{escape(quote)}&rdquo;<small>— {escape(who)}</small></div></div>""")
    footer()


def provider_home():
    items = S.list_prescription_items(provider_id=current()["User_ID"])
    patients = S.patients_of_provider(current()["User_ID"])
    c1, c2, c3 = st.columns(3)
    for col, label, value in ((c1, "Medicines prescribed", len(items)), (c2, "Patients", len(patients)),
                              (c3, "Active medicines", sum(1 for i in items if i["Status"] == "Active"))):
        with col, st.container(key=f"card_p_{label[:4]}"):
            html(f'<div class="lbl">{label}</div><div class="big">{value}</div>')
    st.write("")
    b1, b2 = st.columns(2)
    b1.button("My Patients →", type="primary", on_click=go_to, args=("My Patients",), width="stretch")
    b2.button("Write a prescription →", on_click=go_to, args=("Prescriptions",), width="stretch")
    footer()


def mark_dose(uid, med_id, day, status):
    try:
        S.set_dose_status(uid, med_id, status, day, int(S.get_profile(uid)["Snooze_Min"]))
        flash({"Taken": "Marked as taken. Well done!", "Missed": "Marked as missed.",
               "Snoozed": "Snoozed."}[status], "✅" if status == "Taken" else "📝")
    except Exception as err:
        flash(clean_error(err), "⚠️")


def undo_dose(uid, med_id, day):
    S.clear_dose_status(uid, med_id, day)
    flash("Status cleared.", "↩️")


# ------------------------------------------------------------------ medication
def med_select(label, current, key):
    """Dropdown of correctly spelled medicines (type to search)."""
    opts = list(C.MEDICINES)
    idx = opts.index(current) if current in opts else None
    return st.selectbox(label, opts, index=idx, key=key, placeholder="Choose a medicine")


def dose_select(col, name, current, key):
    """Dosage dropdown - leave it on 'Usual dose' and the medicine's usual dosage is used."""
    opts = list(C.DOSAGE_OPTIONS)
    if current and current not in opts:
        opts.insert(0, current)
    choice = col.selectbox("Dosage", opts, index=opts.index(current) if current else None, key=key,
                           placeholder="Usual dose (filled in automatically)")
    return choice or C.MEDICINE_DOSES.get(name or "", "")


def med_form_fields(prefix, med=None):
    """Shared widgets for the add / edit medication dialogs."""
    med = med or {}
    name = med_select("Medicine name", med.get("Med_Name", ""), f"{prefix}_name")
    c1, c2 = st.columns(2)
    dosage = dose_select(c1, name, med.get("Dosage", ""), f"{prefix}_dose")
    tm = time_select(c2, "Time", med.get("Dosage_Time", "08:00"), f"{prefix}_time")
    c3, c4 = st.columns(2)
    freq = c3.selectbox("Frequency", S.FREQUENCIES, index=S.FREQUENCIES.index(med.get("Frequency", "Once daily")), key=f"{prefix}_freq",
                        help="When adding, 'Twice daily' creates a second reminder 12 hours later.")
    prio = c4.selectbox("Priority", S.PRIORITIES, index=S.PRIORITIES.index(med.get("Priority_Level", "Medium")), key=f"{prefix}_prio")
    c5, c6 = st.columns(2)
    start = c5.date_input("Start date", value=st_date(med.get("Start_Date")) or date.today(), key=f"{prefix}_start")
    end = c6.date_input("End date (optional)", value=st_date(med.get("End_Date")), key=f"{prefix}_end")
    return name, dosage, tm, freq, prio, start, end


def st_date(text):
    return storage.parse_date(text) if text else None


@st.dialog("Add medication")
def add_med_dialog(uid):
    with st.form("add_med_form", border=False):
        name, dosage, tm, freq, prio, start, end = med_form_fields("add")
        if st.form_submit_button("Save medication", type="primary", width="stretch"):
            try:
                rows = S.add_medication(uid, name, dosage, tm, freq, prio, start, end or "")
                flash(f"{name} added ({len(rows)} reminder{'s' if len(rows) > 1 else ''}).")
                st.rerun()
            except Exception as err:
                st.error(clean_error(err))


@st.dialog("Edit medication")
def edit_med_dialog(uid, med):
    with st.form("edit_med_form", border=False):
        name, dosage, tm, freq, prio, start, end = med_form_fields("edit", med)
        active = st.checkbox("Active (reminders on)", value=storage.to_bool(med["Is_Active"]))
        if st.form_submit_button("Save changes", type="primary", width="stretch"):
            try:
                S.update_medication(med["Med_ID"], uid, name, dosage, tm, freq, prio, start, end or "", active)
                flash("Medication updated.")
                st.rerun()
            except Exception as err:
                st.error(clean_error(err))


@st.dialog("Delete medication?")
def delete_med_dialog(uid, med):
    st.write(f"This removes **{med['Med_Name']}** ({t12(med['Dosage_Time'])}) and its history.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, delete", type="primary", width="stretch"):
        S.delete_medication(med["Med_ID"], uid)
        flash("Medication deleted.", "🗑️")
        st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


def med_menu(uid, med_id, key):
    """The ⋮ menu with Edit / Delete for one medicine."""
    med = next((m for m in S.list_medications(uid) if m["Med_ID"] == med_id), None)
    if not med or readonly():
        return
    with st.popover("⋮", width="stretch"):
        if st.button("✏️ Edit", key=f"ed_{key}", width="stretch"):
            edit_med_dialog(uid, med)
        if st.button("🗑️ Delete", key=f"del_{key}", width="stretch"):
            delete_med_dialog(uid, med)


def dose_row(uid, d, key, actions=True):
    color = C.PRIORITY_COLORS[d["Priority_Level"]]
    with st.container(key=f"card_dose_{key}"):
        c = st.columns([0.7, 2.7, 1.8, 3.2, 0.7], vertical_alignment="center")
        c[0].markdown(h(f'<div class="pillicon" style="background:{C.PRIORITY_BG[d["Priority_Level"]]};color:{color}">💊</div>'), unsafe_allow_html=True)
        c[1].markdown(h(f'<div style="font-weight:700">{escape(d["Med_Name"])}</div><div class="sub">{escape(d["Dosage"])} · {t12(d["Dosage_Time"])}</div>'
                        f'<div style="margin-top:4px">{priority_pill(d["Priority_Level"])}</div>'), unsafe_allow_html=True)
        extra = f' <span class="sub">at {d["Action_Time"]}</span>' if d["Status"] == "Taken" and d["Action_Time"] else ""
        sub = "" if d["Status"] in ("Taken", "Missed") else f'<div class="sub" style="margin-top:4px">{d["When"]}</div>'
        c[2].markdown(h(f'{status_pill(d["Status"])}{extra}{sub}'), unsafe_allow_html=True)
        if actions and not readonly():
            if d["Status"] in ("Taken", "Missed"):
                c[3].button("↩ Undo", key=f"undo_{key}", on_click=undo_dose, args=(uid, d["Med_ID"], d["Date"]))
            else:
                b1, b2 = c[3].columns(2)
                b1.button("✓ Taken", key=f"tk_{key}", type="primary", on_click=mark_dose, args=(uid, d["Med_ID"], d["Date"], "Taken"), width="stretch")
                b2.button("✗ Missed", key=f"ms_{key}", on_click=mark_dose, args=(uid, d["Med_ID"], d["Date"], "Missed"), width="stretch")
        with c[4]:
            med_menu(uid, d["Med_ID"], key)


def page_medication():
    banner("Medication", "Medication", "Your daily dose. Your better tomorrow.")
    sample_note()
    if not need_patient():
        return footer()
    vid = viewer_id()
    left, right = st.columns([2.3, 1])
    with left:
        top = st.columns([3, 1.3])
        top[1].button("➕ Add medication", type="primary", width="stretch", disabled=readonly(), on_click=lambda: st.session_state.update(open_add=True))
        if st.session_state.pop("open_add", False):
            add_med_dialog(vid)
        t_today, t_up, t_hist, t_all = st.tabs(["Today", "Upcoming", "History", "All medicines"])
        with t_today:
            doses = S.doses_for_date(vid)
            if not doses:
                html('<div class="empty">📭<b>No medicines scheduled today</b>Use “Add medication” to create one.</div>')
            for i, d in enumerate(doses):
                dose_row(vid, d, f"t{i}")
        with t_up:
            ups = S.upcoming_doses(vid, 3)
            if not ups:
                html('<div class="empty">Nothing coming up in the next 3 days.</div>')
            for i, d in enumerate(ups):
                st.markdown(f"**{d['Date'].strftime('%a %d %b')}**")
                dose_row(vid, d, f"u{i}", actions=False)
        with t_hist:
            now = datetime.now()
            past = [d for d in S.doses_between(vid, now.date() - timedelta(days=29), now.date(), now)
                    if d["Scheduled"] <= now or d["Status"] == "Taken"]
            choice = st.selectbox("Show", ["All", "Taken", "Missed", "Overdue"], key="hist_filter")
            rows = [{"Date": d["Date"].strftime("%d %b %Y"), "Medicine": d["Med_Name"], "Dosage": d["Dosage"],
                     "Scheduled": t12(d["Dosage_Time"]), "Priority": d["Priority_Level"],
                     "Status": "Missed" if d["Status"] == "Overdue" and d["Date"] < now.date() else d["Status"],
                     "Logged at": d["Action_Time"]} for d in reversed(past)]
            if choice != "All":
                rows = [r for r in rows if r["Status"] == choice or (choice == "Overdue" and r["Status"] == "Overdue")]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=420)
            else:
                html('<div class="empty">No records for this filter.</div>')
        with t_all:
            meds = S.list_medications(vid)
            if not meds:
                html('<div class="empty">No medicines yet.</div>')
            for m in meds:
                with st.container(key=f"card_all_{m['Med_ID']}"):
                    c = st.columns([3.2, 1.6, 1.8, 0.7], vertical_alignment="center")
                    end = f" → {m['End_Date']}" if m["End_Date"] else ""
                    c[0].markdown(h(f'<b>{escape(m["Med_Name"])}</b><div class="sub">{escape(m["Dosage"])} · {m["Frequency"]} · from {m["Start_Date"]}{end}</div>'), unsafe_allow_html=True)
                    c[1].markdown(h(f'{t12(m["Dosage_Time"])}'), unsafe_allow_html=True)
                    c[2].markdown(h(priority_pill(m["Priority_Level"]) + ("" if storage.to_bool(m["Is_Active"]) else " " + pill("Paused", C.MUTED))), unsafe_allow_html=True)
                    with c[3]:
                        med_menu(vid, m["Med_ID"], f"all{m['Med_ID']}")
    with right:
        wk = S.week_adherence(vid)
        with st.container(key="card_summary"):
            html(f"""<div class="big" style="font-size:1.2rem">You're doing great! 🌿</div>
              <div class="sub">You've taken {wk['taken']} out of {wk['total']} doses this week.</div>
              <div style="text-align:center;margin:14px 0">{ring(wk['pct'], 130, 14)}</div>
              <div class="sub" style="text-align:center">Adherence over the last 7 days</div>""")
        st.write("")
        html(f'<div class="sample">Always follow your doctor\'s instructions.</div>')
    footer()


# ------------------------------------------------------------------- exercise
def page_exercise():
    banner("Exercise", "Exercise", "Move more. Feel better. Live longer.")
    sample_note()
    if not need_patient():
        return footer()
    vid = viewer_id()
    ex = S.exercise_today(vid)
    c1, c2, c3 = st.columns(3)
    for col, icon, label, value, unit, goal, pct in (
            (c1, "👣", "Steps today", f"{ex['steps']:,}", "steps", f"Goal: {ex['steps_goal']:,}", ex["steps_pct"]),
            (c2, "⏱", "Active minutes", f"{ex['minutes']}", "min", f"Goal: {ex['minutes_goal']} min", ex["minutes_pct"]),
            (c3, "📍", "Distance", f"{ex['distance_km']:g}", "km", f"Goal: {ex['km_goal']:g} km", ex["km_pct"])):
        with col, st.container(key=f"card_s_{label[:4]}"):
            html(f"""<div class="lbl">{icon} {label}</div><div class="big">{value} <small>{unit}</small></div>{bar(pct)}
              <div class="sub">{goal} · {pct}%</div>""")
    st.write("")
    l, r = st.columns([2, 1])
    with l, st.container(key="card_week"):
        html('<div class="lbl">Your weekly progress (steps)</div>')
        series = S.exercise_series(vid, date.today() - timedelta(days=6), date.today())
        fig = go.Figure(go.Bar(x=[s["date"].strftime("%a") for s in series], y=[s["steps"] for s in series],
                               marker_color=C.EMERALD, customdata=[[s["minutes"], s["distance_km"]] for s in series],
                               hovertemplate="%{x}<br><b>%{y:,} steps</b><br>%{customdata[0]} min · %{customdata[1]} km<extra></extra>"))
        fig.add_hline(y=ex["steps_goal"], line_dash="dash", line_color="#D4A017", annotation_text="Goal")
        st.plotly_chart(style_fig(fig, 280), width="stretch", config={"displayModeBar": False})
    with r, st.container(key="card_goals"):
        html("<div class='lbl'>Today's goals</div>")
        for g in S.daily_goal_checklist(vid):
            tag = pill("✓ Done", C.EMERALD) if g["done"] else pill(f"{g['pct']}%", C.MUTED)
            html(f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid {C.BORDER}"><span>{escape(g["label"])}</span>{tag}</div>')
    st.write("")
    l, r = st.columns(2)
    with l:
        st.markdown("##### Record an activity")
        with st.form("log_activity", clear_on_submit=True):
            a1, a2 = st.columns(2)
            kind = a1.selectbox("Activity type", S.ACTIVITY_TYPES)
            day = a2.date_input("Date", value=date.today(), max_value=date.today())
            b1, b2, b3 = st.columns(3)
            minutes = b1.number_input("Duration (min)", 0, 600, 30)
            km = b2.number_input("Distance (km)", 0.0, 200.0, 0.0, step=0.1)
            steps = b3.number_input("Steps (0 = estimate)", 0, 100000, 0, step=100)
            if st.form_submit_button("Save activity", type="primary", width="stretch", disabled=readonly()):
                try:
                    S.log_activity(vid, kind, minutes, km, steps or None, day)
                    flash("Activity saved. Great job!", "🏃")
                    st.rerun()
                except Exception as err:
                    st.error(clean_error(err))
    with r:
        st.markdown("##### Daily goals")
        with st.form("set_goals"):
            g = S.get_goals(vid)
            a1, a2, a3 = st.columns(3)
            gs = a1.number_input("Steps", 500, 50000, int(float(g["Steps"]["Exercise_Target"])), step=500)
            gm = a2.number_input("Active min", 5, 600, int(float(g["Minutes"]["Exercise_Target"])), step=5)
            gk = a3.number_input("Distance km", 0.5, 100.0, int(float(g["Distance"]["Exercise_Target"])) / 1000, step=0.5)
            if st.form_submit_button("Update goals", width="stretch", disabled=readonly()):
                try:
                    S.set_goals(vid, gs, gm, gk)
                    flash("Goals updated.", "🎯")
                    st.rerun()
                except Exception as err:
                    st.error(clean_error(err))
        acts = S.activities_for_date(vid)
        st.markdown("##### Today's activities")
        if not acts:
            html('<div class="empty">No activity recorded yet today.</div>')
        for a in acts:
            c = st.columns([4, 1], vertical_alignment="center")
            c[0].markdown(f"**{a['Type']}** · {a['minutes']} min · {a['distance_km']:g} km · {a['steps']:,} steps")
            c[1].button("🗑️", key=f"delact_{a['Activity_ID']}", disabled=readonly(), help="Delete this activity",
                        on_click=lambda aid=a["Activity_ID"]: (S.delete_activity(vid, aid), flash("Activity deleted.", "🗑️")))
    footer()


def style_fig(fig, height=300):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color=C.TEXT, size=13), showlegend=False,
                      hoverlabel=dict(bgcolor=C.CARD, font_color=C.TEXT, font_size=13), bargap=0.35)
    fig.update_xaxes(showgrid=False, linecolor=C.BORDER)
    fig.update_yaxes(gridcolor=C.GRID, zeroline=False)
    return fig


# -------------------------------------------------------------- prescriptions
def rx_fields(prefix, item=None, rx=None):
    item = item or {}
    name = med_select("Medicine", item.get("Med_Name", ""), f"{prefix}_n")
    c1, c2, c3 = st.columns([1.3, 1.3, 1])
    dosage = dose_select(c1, name, item.get("Dosage", ""), f"{prefix}_d")
    freq = c2.selectbox("Frequency", S.FREQUENCIES, index=S.FREQUENCIES.index(item.get("Frequency", "Once daily")), key=f"{prefix}_f")
    dur = c3.number_input("Days", 1, 365, int(item.get("Duration_Days", 7) or 7), key=f"{prefix}_u")
    return {"Med_Name": name, "Dosage": dosage, "Frequency": freq, "Duration_Days": dur}


@st.dialog("New prescription", width="large")
def add_rx_dialog():
    me = current()
    provider = me["Role"] == "Provider"
    count = st.number_input("Number of medicines", 1, 6, 1, key="rx_count")
    with st.form("add_rx_form", border=False):
        patient_choice = ""
        if provider:
            patient_choice = st.selectbox("Patient", S.patient_choices(current()["User_ID"]), index=None,
                                          placeholder="Choose a linked patient",
                                          help="Only patients you linked in My Patients (username + CID) are listed.")
        c1, c2 = st.columns([1, 2])
        rx_date = c1.date_input("Prescription date", value=date.today(), max_value=date.today() + timedelta(days=1))
        note = c2.text_input("Diagnosis / note (optional)", max_chars=100)
        items = [rx_fields(f"rx{i}") for i in range(int(count))]
        if st.form_submit_button("Save prescription", type="primary", width="stretch"):
            try:
                if provider:
                    pid = S.patient_from_choice(patient_choice, current()["User_ID"])["User_ID"]
                else:
                    pid = viewer_id()
                S.create_prescription(me["User_ID"], pid, rx_date, note, items)
                flash("Prescription saved.", "📄")
                st.rerun()
            except Exception as err:
                st.error(clean_error(err))


@st.dialog("Prescription details", width="large")
def view_rx_dialog(rx_id):
    rx = S.get_prescription(rx_id)
    html(f"""<div class="sub">Patient</div><b>{escape(rx['Patient_Name'])}</b>
      <div class="sub" style="margin-top:8px">Prescribed by</div><b>{escape(rx['Provider_Name'])}</b> · {rx['Rx_Date']}
      <div class="sub" style="margin-top:8px">Diagnosis / note</div>{escape(rx['Diagnosis_Note'] or '-')}""")
    st.dataframe(pd.DataFrame([{"Medicine": i["Med_Name"], "Dosage": i["Dosage"], "Frequency": i["Frequency"],
                                "Days": i["Duration_Days"], "Status": i["Status"]} for i in rx["Items"]]),
                 hide_index=True, width="stretch")
    st.download_button("⬇️ Download printable summary (HTML)", S.prescription_summary_html(rx_id),
                       file_name=f"prescription_{rx_id}.html", mime="text/html", width="stretch")
    st.caption("Open the downloaded file in your browser and press Ctrl+P to print.")


@st.dialog("Edit prescription")
def edit_rx_dialog(item):
    with st.form("edit_rx_form", border=False):
        fields = rx_fields("erx", item)
        rx_date = st.date_input("Prescription date", value=storage.parse_date(item["Rx_Date"]))
        note = st.text_input("Diagnosis / note", value=item["Diagnosis_Note"], max_chars=100)
        if st.form_submit_button("Save changes", type="primary", width="stretch"):
            try:
                S.update_prescription_item(item["Item_ID"], current()["User_ID"], fields["Med_Name"], fields["Dosage"],
                                           fields["Frequency"], fields["Duration_Days"], rx_date, note)
                flash("Prescription updated.")
                st.rerun()
            except Exception as err:
                st.error(clean_error(err))


@st.dialog("Add to my schedule")
def schedule_rx_dialog(item):
    st.write(f"Create reminders for **{item['Med_Name']}** ({item['Frequency'].lower()}).")
    tm = time_select(st, "First dose time", "08:00", f"rx_time_{item['Item_ID']}")
    prio = st.selectbox("Priority colour", S.PRIORITIES, index=1)
    if st.button("Add to schedule", type="primary", width="stretch"):
        try:
            S.schedule_prescription_item(viewer_id(), item["Item_ID"], tm, prio)
            flash("Added to your medication schedule.", "📅")
            st.rerun()
        except Exception as err:
            st.error(clean_error(err))


@st.dialog("Delete prescription item?")
def delete_rx_dialog(item):
    st.write(f"Delete **{item['Med_Name']}** from this prescription?")
    if st.button("Yes, delete", type="primary", width="stretch"):
        try:
            S.delete_prescription_item(item["Item_ID"], current()["User_ID"])
            flash("Deleted.", "🗑️")
            st.rerun()
        except Exception as err:
            st.error(clean_error(err))


def rx_table(items, tag):
    if not items:
        html("""<div class="empty">📄<b>No prescriptions here yet</b>When your doctor adds a prescription it will appear here.</div>""")
        return
    me = current()
    head = st.columns([2.4, 1.8, 1.4, 1.2, 2.2])
    for col, text in zip(head, ["Medicine", "Dosage", "Prescribed on", "Status", "Actions"]):
        col.markdown(f'<div class="th">{text}</div>', unsafe_allow_html=True)
    for n, it in enumerate(items):
        key = f"{tag}{n}{it['Item_ID']}"
        with st.container(key=f"card_rx_{key}"):
            c = st.columns([2.4, 1.8, 1.4, 1.2, 2.2], vertical_alignment="center")
            c[0].markdown(h(f'<b>{escape(it["Med_Name"])}</b><div class="sub">by {escape(it["Provider_Name"])}'
                            + (f' · for {escape(it["Patient_Name"])}' if me["Role"] == "Provider" else "") + '</div>'), unsafe_allow_html=True)
            c[1].markdown(h(f'{escape(it["Dosage"])}<div class="sub">{it["Frequency"]} · {it["Duration_Days"]} days</div>'), unsafe_allow_html=True)
            c[2].markdown(storage.parse_date(it["Rx_Date"]).strftime("%d %b %Y"))
            c[3].markdown(h(pill("● " + it["Status"], C.EMERALD if it["Status"] == "Active" else C.MUTED)), unsafe_allow_html=True)
            a = c[4].columns(4)
            if a[0].button("👁", key=f"v{key}", help="View / print"):
                view_rx_dialog(it["Rx_ID"])
            own = it["Provider_ID"] == me["User_ID"]
            if a[1].button("✏️", key=f"e{key}", help="Edit", disabled=not own):
                edit_rx_dialog(it)
            if a[2].button("🗑️", key=f"d{key}", help="Delete", disabled=not own):
                delete_rx_dialog(it)
            can_schedule = me["Role"] == "Patient" and it["Status"] == "Active" and not it["Scheduled"]
            if a[3].button("📅" if not it["Scheduled"] else "✔", key=f"s{key}", disabled=not can_schedule,
                           help="Add to my schedule" if not it["Scheduled"] else "Already in your schedule"):
                schedule_rx_dialog(it)


def page_prescriptions():
    me = current()
    banner("Prescriptions", "Prescriptions", "Your doctor's plan, in your hands.")
    sample_note()
    if me["Role"] == "Provider":
        items = S.list_prescription_items(provider_id=me["User_ID"])
    elif not need_patient():
        return footer()
    else:
        items = S.list_prescription_items(patient_id=viewer_id())
    left, right = st.columns([2.6, 1])
    with left:
        t_active, t_past, t_all = st.tabs(["Active", "Past", "All"])
        with t_active:
            rx_table([i for i in items if i["Status"] == "Active"], "a")
        with t_past:
            rx_table([i for i in items if i["Status"] == "Past"], "p")
        with t_all:
            rx_table(items, "l")
    with right:
        with st.container(key="card_rxside"):
            if items:
                html(f'<div class="lbl">Summary</div><div class="big">{sum(i["Status"] == "Active" for i in items)} <small>active</small></div>'
                     f'<div class="sub">{len(items)} medicines in total</div>')
            else:
                html('<div class="empty">📄<b>No new prescription yet</b>Your doctor will add your prescriptions here.</div>')
            if me["Role"] == "Provider" or not readonly():
                if st.button("➕ Add prescription", type="primary", width="stretch"):
                    add_rx_dialog()
        st.caption("Doctors can also write prescriptions in the Gradio prescription portal.")
    footer()


# ------------------------------------------------------------------ analytics
def page_analytics():
    banner("Analytics", "Analytics", "Track your progress. See the bigger picture.")
    sample_note()
    if not need_patient():
        return footer()
    vid = viewer_id()
    choice = st.segmented_control("Range", ["7 days", "30 days", "3 months"], default="7 days",
                                  label_visibility="collapsed", key="range") or "7 days"
    days = {"7 days": 7, "30 days": 30, "3 months": 90}[choice]
    data = S.analytics_data(vid, days)
    ex = pd.DataFrame(data["exercise"])
    ex["label"] = ex["date"].map(lambda d: d.strftime("%d %b"))
    a = data["adherence"]
    # four metric tiles (proposal presentation): adherence, days with every dose, avg exercise %, goal days
    c1, c2, c3, c4 = st.columns(4)
    with c1, st.container(key="card_m1"):
        html(f'<div class="lbl">Medication adherence</div><div style="display:flex;gap:12px;align-items:center">{ring(a["pct"], 90, 10)}'
             f'<div class="sub">{a["taken"]}/{a["total"]} doses<br>taken</div></div>')
    with c2, st.container(key="card_m2"):
        html(f'<div class="lbl">Days with every dose</div><div class="big">{data["full_dose_days"]} <small>/ {data["dose_days"]} days</small></div>'
             f'<div class="sub">all doses taken that day</div>')
    with c3, st.container(key="card_m3"):
        html(f'<div class="lbl">Average exercise</div><div class="big">{data["avg_exercise_pct"]}% <small>of goal</small></div>'
             f'<div class="sub">daily steps goal {data["steps_goal"]:,}</div>')
    with c4, st.container(key="card_m4"):
        html(f'<div class="lbl">Days goal reached</div><div class="big">{data["goal_days"]} <small>/ {data["days"]} days</small></div>'
             f'<div class="sub">steps goal met</div>')
    st.write("")
    l, r = st.columns(2)
    with l, st.container(key="card_c1"):
        html('<div class="lbl">Doses taken vs missed</div>')
        adf = pd.DataFrame(data["adherence_days"])
        if adf.empty:
            html('<div class="empty">No doses yet.</div>')
        else:
            if days > 31:  # group by week so 3 months stays readable
                adf["date"] = pd.to_datetime(adf["date"])
                adf = adf.groupby(pd.Grouper(key="date", freq="W-MON", label="left", closed="left"))[["taken", "missed"]].sum().reset_index()
                adf["label"] = adf["date"].dt.strftime("wk %d %b")
            else:
                adf["label"] = adf["date"].map(lambda d: d.strftime("%d %b"))
            fig = go.Figure()
            fig.add_bar(x=adf["label"], y=adf["taken"], name="Taken", marker_color=C.EMERALD, hovertemplate="%{x}<br>Taken: <b>%{y}</b><extra></extra>")
            fig.add_bar(x=adf["label"], y=adf["missed"], name="Missed", marker_color="#E58A8A", hovertemplate="%{x}<br>Missed: <b>%{y}</b><extra></extra>")
            fig.update_layout(barmode="stack", showlegend=True, legend=dict(orientation="h", y=1.12))
            st.plotly_chart(style_fig(fig, 280).update_layout(showlegend=True), width="stretch", config={"displayModeBar": False})
    with r, st.container(key="card_c2"):
        html('<div class="lbl">Steps per day</div>')
        fig = go.Figure(go.Bar(x=ex["label"], y=ex["steps"], marker_color=C.EMERALD,
                               hovertemplate="%{x}<br><b>%{y:,} steps</b><extra></extra>"))
        fig.add_hline(y=data["steps_goal"], line_dash="dash", line_color="#D4A017", annotation_text="Goal")
        st.plotly_chart(style_fig(fig, 280), width="stretch", config={"displayModeBar": False})
    l, r = st.columns(2)
    with l, st.container(key="card_c3"):
        html('<div class="lbl">Active minutes</div>')
        fig = go.Figure(go.Scatter(x=ex["label"], y=ex["minutes"], mode="lines+markers", fill="tozeroy",
                                   line=dict(color=C.EMERALD, width=3), fillcolor="rgba(1,138,148,.15)",
                                   hovertemplate="%{x}<br><b>%{y} min</b><extra></extra>"))
        st.plotly_chart(style_fig(fig, 280), width="stretch", config={"displayModeBar": False})
    with r, st.container(key="card_c4"):
        html('<div class="lbl">Weight (kg)</div>')
        if data["weight"]:
            wdf = pd.DataFrame(data["weight"])
            fig = go.Figure(go.Scatter(x=wdf["date"], y=wdf["weight"], mode="lines+markers", line=dict(color="#3D7EA6", width=3),
                                       hovertemplate="%{x|%d %b}<br><b>%{y} kg</b><extra></extra>"))
            fig.update_yaxes(range=[min(wdf["weight"]) - 2, max(wdf["weight"]) + 2])
            st.plotly_chart(style_fig(fig, 280), width="stretch", config={"displayModeBar": False})
        else:
            html('<div class="empty">Add your weight in My Profile → Health Information.</div>')
    footer()


# -------------------------------------------------------------------- profile
def page_profile():
    me = S.get_user(current()["User_ID"])
    prof = S.get_profile(me["User_ID"])
    banner("My Profile", "My Profile", "Your information. Your health journey.")
    sample_note()
    left, right = st.columns([1, 2.2])
    with left, st.container(key="card_prof"):
        html(f'<div style="text-align:center"><img src="{avatar_uri(me, 200)}" style="width:110px;height:110px;border-radius:50%;object-fit:cover;box-shadow:0 4px 14px rgba(0,0,0,.15)">'
             f'<div class="big" style="font-size:1.2rem;margin-top:8px">{escape(me["Full_Name"])}</div><div class="sub">{escape(prof["Email"] or "@" + me["Username"])}</div>'
             f'<div style="margin-top:6px">{pill(me["Role"], C.EMERALD)}</div></div>')
        with st.expander("📷 Change profile photo"):
            up = st.file_uploader("Choose a JPG, PNG or WEBP image", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed")
            if up and st.button("Save photo", type="primary", width="stretch"):
                try:
                    I.save_profile_photo(me["User_ID"], up.getvalue())
                    flash("Profile photo updated.", "📷")
                    st.rerun()
                except Exception as err:
                    st.error(str(err))
            if st.button("Remove my photo", width="stretch"):
                I.remove_profile_photo(me["User_ID"])
                st.rerun()
        sections = ["Personal Details", "Health Information", "Emergency Contact", "Notifications", "Settings"]
        if me["Role"] == "Patient":
            sections.insert(3, "Care Team")
        section = st.radio("Section", sections, label_visibility="collapsed", key="prof_section")
    with right, st.container(key="card_pform"):
        st.markdown(f"##### {section}")
        try:
            if section == "Personal Details":
                with st.form("pf_personal", border=False):
                    name = st.text_input("Full name", me["Full_Name"])
                    c1, c2 = st.columns(2)
                    dob = c1.date_input("Date of birth", value=st_date(me["Date_of_Birth"]), min_value=date(1900, 1, 1), max_value=date.today())
                    gender = c2.selectbox("Gender", S.GENDERS, index=S.GENDERS.index(prof["Gender"]) if prof["Gender"] in S.GENDERS else 0)
                    c3, c4 = st.columns(2)
                    email = c3.text_input("Email", prof["Email"])
                    phone = c4.text_input("Phone", me["Phone"], placeholder="+975 17 123456")
                    cid = st.text_input("CID (11 digits)", me["CID"], max_chars=13,
                                        help="Needed to log in with your CID and for your caregiver or doctor to follow you.")
                    if st.form_submit_button("Save changes", type="primary"):
                        if cid.strip() != me["CID"]:
                            S.update_cid(me["User_ID"], cid)
                        S.update_user(me["User_ID"], name, dob or "", phone)
                        S.save_profile(me["User_ID"], Email=email, Gender=gender)
                        st.session_state["user"] = S.public_user(S.get_user(me["User_ID"]))
                        flash("Personal details saved.")
                        st.rerun()
            elif section == "Health Information":
                with st.form("pf_health", border=False):
                    c1, c2, c3 = st.columns(3)
                    height = c1.number_input("Height (cm)", 0, 250, int(float(prof["Height_Cm"] or 0)))
                    weight = c2.number_input("Weight (kg)", 0.0, 300.0, float(prof["Weight_Kg"] or 0), step=0.5)
                    blood = c3.selectbox("Blood type", S.BLOOD_TYPES, index=S.BLOOD_TYPES.index(prof["Blood_Type"]) if prof["Blood_Type"] in S.BLOOD_TYPES else 0)
                    allergies = st.text_input("Allergies", prof["Allergies"])
                    cond = st.text_input("Health conditions", prof["Conditions"])
                    if st.form_submit_button("Save changes", type="primary"):
                        S.save_profile(me["User_ID"], Height_Cm=height or "", Weight_Kg=weight or "", Blood_Type=blood, Allergies=allergies, Conditions=cond)
                        flash("Health information saved.")
                        st.rerun()
                if prof["Height_Cm"] and prof["Weight_Kg"]:
                    bmi = float(prof["Weight_Kg"]) / (float(prof["Height_Cm"]) / 100) ** 2
                    st.caption(f"Body mass index (BMI): **{bmi:.1f}** — a general guide only, ask a health worker about your own targets.")
            elif section == "Emergency Contact":
                with st.form("pf_emerg", border=False):
                    name = st.text_input("Name", prof["Emergency_Name"])
                    c1, c2 = st.columns(2)
                    rel = c1.text_input("Relationship", prof["Emergency_Relation"])
                    phone = c2.text_input("Phone", prof["Emergency_Phone"], placeholder="+975 17 123456")
                    if st.form_submit_button("Save changes", type="primary"):
                        S.save_profile(me["User_ID"], Emergency_Name=name, Emergency_Relation=rel, Emergency_Phone=phone)
                        flash("Emergency contact saved.")
                        st.rerun()
            elif section == "Care Team":
                care_team_section(me)
            elif section == "Notifications":
                with st.form("pf_notif", border=False):
                    rem = st.toggle("Medication reminder pop-ups (desktop app)", value=storage.to_bool(prof["Notify_Reminders"]))
                    week = st.toggle("Weekly progress summary", value=storage.to_bool(prof["Notify_Weekly"]))
                    if st.form_submit_button("Save changes", type="primary"):
                        S.save_profile(me["User_ID"], Notify_Reminders=rem, Notify_Weekly=week)
                        flash("Notification settings saved.")
                        st.rerun()
                st.caption("Reminders appear as pop-ups with sound in the Tkinter desktop app while it is open.")
            else:
                with st.form("pf_settings", border=False):
                    snooze = st.number_input("Snooze length (minutes)", 1, 60, int(prof["Snooze_Min"] or 10))
                    sound = st.toggle("Play a sound with reminders", value=storage.to_bool(prof["Sound_On"]))
                    if st.form_submit_button("Save changes", type="primary"):
                        S.save_profile(me["User_ID"], Snooze_Min=snooze, Sound_On=sound)
                        flash("Settings saved.")
                        st.rerun()
                with st.expander("🔒 Change password"):
                    with st.form("pf_pw", border=False, clear_on_submit=True):
                        old = st.text_input("Current password", type="password")
                        new = st.text_input("New password", type="password")
                        if st.form_submit_button("Update password"):
                            try:
                                S.change_password(me["User_ID"], old, new)
                                st.success("Password updated.")
                            except Exception as err:
                                st.error(clean_error(err))
                st.caption(f"Your data is stored only on this computer, in the folder: `{C.DATA_DIR}`")
        except Exception as err:
            st.error(clean_error(err))
    footer()



# ------------------------------------------------------------ my patients (caregiver / provider)
def open_patient(patient_id, page="Analytics"):
    st.session_state["viewing_id"] = patient_id
    go_to(page)


def unlink_patient(link_id, name):
    try:
        S.unlink(link_id, current()["User_ID"])
        if st.session_state.get("viewing_id") not in [p["User_ID"] for p in S.linked_patients(current()["User_ID"])]:
            st.session_state.pop("viewing_id", None)
        flash(f"{name} removed from your patients.", "🔗")
    except Exception as err:
        flash(clean_error(err), "⚠️")


@st.dialog("Send a care plan", width="large")
def send_plan_dialog(patient):
    st.write(f"For **{patient['Full_Name']}** (@{patient['Username']}). The medicines are added to the patient's "
             "reminders straight away, and the patient gets a message.")
    count = st.radio("Medicines in this plan", [0, 1, 2, 3], index=1, horizontal=True, key="plan_n")
    meds = []
    for i in range(count):
        st.markdown(f"**Medicine {i + 1}**")
        a, b = st.columns([2, 1])
        with a:
            name = med_select("Medicine", "", f"plan_name_{i}")
        dosage = dose_select(b, name, "", f"plan_dose_{i}")
        c, d, e, f = st.columns(4)
        tm = time_select(c, "Time", "08:00", f"plan_time_{i}")
        freq = d.selectbox("How often", S.FREQUENCIES, key=f"plan_freq_{i}")
        days = e.number_input("For how many days", 1, 365, 7, key=f"plan_days_{i}")
        prio = f.selectbox("Priority", S.PRIORITIES, index=1, key=f"plan_prio_{i}")
        meds.append({"Med_Name": name or "", "Dosage": dosage, "Time": tm, "Frequency": freq,
                     "Duration_Days": days, "Priority": prio})
    st.markdown("**Exercise**")
    minutes = st.number_input("Exercise per day (minutes) — 0 = no change", 0, 600, 0, step=15,
                              help="For example 30 = half an hour, 60 = 1 hour.", key="plan_min")
    note = st.text_input("Note to the patient (optional)", max_chars=100, key="plan_note")
    if st.button("Send plan", type="primary", width="stretch", key="plan_send"):
        try:
            if any(not m["Med_Name"] for m in meds):
                raise ValidationError("Choose a medicine in every medicine row (or lower the number of medicines).")
            out = S.send_care_plan(current()["User_ID"], patient["User_ID"], meds, minutes or None, note)
            flash(f"Plan sent to {patient['Full_Name']} ({len(out['Lines'])} item{'s' if len(out['Lines']) != 1 else ''}).", "📨")
            st.rerun()
        except Exception as err:
            st.error(clean_error(err))


def page_my_patients():
    me = current()
    banner("Prescriptions", "My Patients", "Follow your patients' progress and send them a plan.")
    with st.container(key="card_view_patient"):
        st.markdown("##### View patient")
        st.caption("Enter the patient's **username** and **CID**. They find both in their DrukCare My Profile.")
        with st.form("view_patient_form", clear_on_submit=True, border=False):
            c = st.columns([2, 2, 1], vertical_alignment="bottom")
            uname = c[0].text_input("Patient's username", placeholder="e.g. sonam_p")
            cid = c[1].text_input("Patient's CID (11 digits)", max_chars=13, placeholder="e.g. 10805001234")
            if c[2].form_submit_button("View patient", type="primary", width="stretch"):
                try:
                    msg = live_check("cid", cid)
                    if msg:
                        raise ValidationError(msg + ".")
                    p = S.link_patient(me["User_ID"], uname, cid)
                    flash(f"You can now follow {p['Full_Name']}.", "🤝")
                    open_patient(p["User_ID"])
                    st.rerun()
                except Exception as err:
                    st.error(clean_error(err))
    st.write("")
    people = S.linked_patients(me["User_ID"])
    st.markdown(f"##### Your patients ({len(people)})")
    if not people:
        html('<div class="empty">No patients yet. Use View patient above with the patient\'s username and CID.</div>')
    for p in people:
        today = S.doses_for_date(p["User_ID"])
        taken = sum(1 for d in today if d["Status"] == "Taken")
        missed = sum(1 for d in today if d["Status"] in ("Missed", "Overdue"))
        wk = S.week_adherence(p["User_ID"])
        ex = S.exercise_today(p["User_ID"])
        with st.container(key=f"card_pt_{p['User_ID']}"):
            c = st.columns([0.6, 3.2, 1.3, 1.3, 1.1], vertical_alignment="center")
            c[0].markdown(f'<img src="{avatar_uri(p, 64)}" style="width:46px;border-radius:50%">', unsafe_allow_html=True)
            c[1].markdown(h(f'<b>{escape(p["Full_Name"])}</b> <span class="sub">@{escape(p["Username"])}</span>'
                            f'<div class="sub">Today: <b>{taken}</b> taken · <b style="color:#D64545">{missed}</b> missed/overdue '
                            f'of {len(today)} · exercise {ex["minutes"]}/{ex["minutes_goal"]} min · '
                            f'this week {wk["pct"]}% adherence</div>'), unsafe_allow_html=True)
            c[2].button("View progress", key=f"pv_{p['User_ID']}", on_click=open_patient, args=(p["User_ID"],), width="stretch")
            if c[3].button("Send plan", key=f"ps_{p['User_ID']}", type="primary", width="stretch"):
                send_plan_dialog(p)
            c[4].button("Unlink", key=f"pu_{p['User_ID']}", on_click=unlink_patient, args=(p["Link_ID"], p["Full_Name"]), width="stretch")
    footer()


def remove_carer(link_id, name):
    try:
        S.unlink(link_id, current()["User_ID"])
        flash(f"{name} can no longer see your progress.", "🔗")
    except Exception as err:
        flash(clean_error(err), "⚠️")


def care_team_section(me):
    """Patient's view: who can see my progress (linked with my username + CID)."""
    st.caption(f"Your caregiver or doctor needs your username **{me['Username']}** and your CID to follow your "
               "progress and send you a plan. Remove anyone you no longer want.")
    if not me["CID"]:
        st.warning("You have not added your CID yet. Add it under Personal Details.")
    team = S.care_team(me["User_ID"])
    if not team:
        html('<div class="empty">Nobody is following your progress yet.</div>')
    for t in team:
        c = st.columns([3, 1], vertical_alignment="center")
        c[0].markdown(h(f'<b>{escape(t["Full_Name"])}</b> <span class="sub">{t["Role"]} · since {t["Linked_On"]}</span>'),
                      unsafe_allow_html=True)
        c[1].button("Remove", key=f"ct_{t['Link_ID']}", on_click=remove_carer, args=(t["Link_ID"], t["Full_Name"]), width="stretch")


@st.fragment(run_every=10)
def message_watch():
    """Every 10 s: show a pop-up (toast) for each new message from a caregiver / doctor."""
    me = st.session_state.get("user")
    if not me or me["Role"] != "Patient":
        return
    seen = st.session_state.setdefault("msg_seen", set())
    for m in S.messages_for(me["User_ID"], unread_only=True):
        if m["Msg_ID"] not in seen:
            seen.add(m["Msg_ID"])
            st.toast(f"**{m['Title']}** — open the bell 🔔 to read it.", icon="📨")


# ======================================================================= main
PAGES = {
    "Home": ("home", page_home), "Medication": ("medication", page_medication),
    "Exercise": ("directions_walk", page_exercise), "Prescriptions": ("description", page_prescriptions),
    "Analytics": ("bar_chart", page_analytics), "My Patients": ("group", page_my_patients),
    "My Profile": ("person", page_profile),
}
VIEW = ["Medication", "Exercise", "Analytics"]
ROLE_PAGES = {
    "Patient": ["Home", "Medication", "Exercise", "Prescriptions", "Analytics", "My Profile"],
    # caregivers and providers: link a patient (username + CID), then see that patient read-only
    "Caregiver": ["Home", "My Patients", *VIEW, "Prescriptions", "My Profile"],
    "Provider": ["Home", "My Patients", "Prescriptions", *VIEW, "My Profile"],
}


NAV_LABELS = {"Home": "Dashboard", "Exercise": "Exercises"}


def sidebar():
    me = current()
    with st.sidebar:
        lg = I.png_uri(C.LOGO_SIDEBAR, 420)
        html(f'<div class="logo"><img class="lg" src="{lg}"><div class="tg">{C.TAGLINE}</div></div>')
        allowed = ROLE_PAGES[me["Role"]]
        if st.session_state.get("page") not in allowed:
            st.session_state["page"] = "Home"
        for name in allowed:
            icon, _ = PAGES[name]
            st.button(NAV_LABELS.get(name, name), key=f"nav_{name}", icon=f":material/{icon}:", width="stretch",
                      type="primary" if st.session_state["page"] == name else "secondary", on_click=go_to, args=(name,))
        if me["Role"] in ("Caregiver", "Provider"):
            people = S.linked_patients(me["User_ID"])
            st.divider()
            if people:
                ids = [p["User_ID"] for p in people]
                names = {p["User_ID"]: p["Full_Name"] for p in people}
                if st.session_state.get("viewing_id") not in ids:
                    st.session_state["viewing_id"] = ids[0]
                # the drop-down has its own key; "viewing_id" is the plain value the pages read
                if st.session_state.get("viewing_pick") != st.session_state["viewing_id"]:
                    st.session_state["viewing_pick"] = st.session_state["viewing_id"]
                st.selectbox("Viewing patient", ids, format_func=names.get, key="viewing_pick",
                             on_change=lambda: st.session_state.update(viewing_id=st.session_state["viewing_pick"]))
            else:
                st.session_state["viewing_id"] = None
        st.divider()
        if st.button("Log out", key="logout", icon=":material/logout:", width="stretch"):
            for k in ("user", "page", "viewing_id", "viewing_pick", "recent", "msg_seen"):
                st.session_state.pop(k, None)
            st.rerun()
        dr = I.png_uri(C.SIDEBAR_DRAGON, 520)
        html(f'<img class="side-dragon" src="{dr}">')


def main():
    if "user" not in st.session_state:
        auth_screen()
        if "flash" in st.session_state:
            msg, icon = st.session_state.pop("flash")
            st.toast(msg, icon=icon)
        return
    # always use the newest account details (name, role) from the CSV file
    fresh = S.get_user(st.session_state["user"]["User_ID"])
    if not fresh:
        st.session_state.pop("user")
        st.rerun()
    st.session_state["user"] = S.public_user(fresh)
    sidebar()
    message_watch()
    if "flash" in st.session_state:
        msg, icon = st.session_state.pop("flash")
        st.toast(msg, icon=icon)
    try:
        PAGES[st.session_state["page"]][1]()
    except storage.StorageError as err:
        st.error(str(err))


main()
