"""Data housekeeping for DrukCare.

The fictional demo accounts have been removed from DrukCare. Every app calls
remove_demo_data() when it starts: if an older version created the demo accounts
(demo_patient, demo_caregiver, demo_provider), they are deleted together with all
their medicines, logs, prescriptions and profile data. Real accounts are never touched.

Run   python -m drukcare_core.seed --reset   to delete ALL data and start empty
(a backup copy is made first in data/backups/).
"""
import sys

from . import config
from . import storage as st

DEMO_USERNAMES = {"demo_patient", "demo_caregiver", "demo_provider"}


def remove_demo_data() -> int:
    """Delete the old demo accounts and everything linked to them. Returns how many accounts were removed."""
    st.init_storage()
    with st.locked():
        ids = {u["User_ID"] for u in st.read_table("user_account") if u["Username"] in DEMO_USERNAMES}
        if not ids:
            return 0
        rx_ids = {r["Rx_ID"] for r in st.read_table("prescription")
                  if r["Provider_ID"] in ids or r["Patient_ID"] in ids}
        med_ids = {m["Med_ID"] for m in st.read_table("medication") if m["User_ID"] in ids}
        goal_ids = {g["Goal_ID"] for g in st.read_table("exercise_goal") if g["User_ID"] in ids}
        st.delete_where("compliance_log", lambda r: r["Med_ID"] in med_ids)
        st.delete_where("medication", lambda r: r["Med_ID"] in med_ids)
        st.delete_where("prescription_item", lambda r: r["Rx_ID"] in rx_ids)
        st.delete_where("prescription", lambda r: r["Rx_ID"] in rx_ids)
        st.delete_where("exercise_log", lambda r: r["Goal_ID"] in goal_ids)
        st.delete_where("exercise_goal", lambda r: r["Goal_ID"] in goal_ids)
        st.delete_where("health_profile", lambda r: r["User_ID"] in ids)
        st.delete_where("weight_log", lambda r: r["User_ID"] in ids)
        st.delete_where("user_account", lambda r: r["User_ID"] in ids)
    for uid in ids:
        for f in config.PHOTO_DIR.glob(f"{uid}.*"):
            try:
                f.unlink()
            except OSError:
                pass
    return len(ids)


def reset_all():
    """Delete every CSV (a backup copy is made first). DrukCare then starts empty."""
    st.init_storage()
    with st.locked():
        st.backup_if_needed()
        for name in st.SCHEMAS:
            path = st.table_path(name)
            if path.exists():
                path.unlink()
    st.init_storage()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_all()
        print("All data deleted. Create a new account in any DrukCare app.")
    else:
        print(f"Removed {remove_demo_data()} demo account(s).")
