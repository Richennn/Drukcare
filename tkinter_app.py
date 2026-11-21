"""DrukCare - Tkinter desktop application.

Run with:   python tkinter_app.py

Role of Tkinter in this project (see the proposal):
  * the MAIN desktop app: secure login / sign-up, medication CRUD, exercise tracker,
    prescriptions, analytics chart and profile
  * a background reminder THREAD that checks every 2 seconds and shows a pop-up with
    sound, "Mark as taken" and "Snooze" (the window never freezes: the thread only puts
    messages in a queue and the main window shows them)
  * can start the Streamlit dashboard and the Gradio portal as background programs
    and closes them when you quit

HOW TO USE YOUR OWN PHOTOS: edit the "IMAGE PATHS" block in drukcare_core/config.py
or save your pictures in the assets/ folder with the file names listed there.
Pillow (PIL) loads every picture; see load_photo() below.
"""
import os
import queue
import socket
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk

from drukcare_core import config as C
from drukcare_core import images as I
from drukcare_core import seed, storage
from drukcare_core import services as S
from drukcare_core.validators import ValidationError, live_check, time_choices, time_label, validate_email

FONT = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
SERIF = "Georgia" if sys.platform.startswith("win") else "DejaVu Serif"
NAV = [("Home", "⌂"), ("Medication", "✚"), ("Exercise", "☺"), ("Prescriptions", "☰"),
       ("Analytics", "▤"), ("My Profile", "☻")]
NAV_OTHER = [("Home", "⌂"), ("My Profile", "☻")]     # caregivers and providers use the web tools


# ============================================================ small UI helpers
def label(parent, text="", size=11, bold=False, color=C.TEXT, bg=C.CARD, italic=False, family=None, **kw):
    style = ("bold " if bold else "") + ("italic" if italic else "")
    return tk.Label(parent, text=text, bg=bg, fg=color, font=(family or FONT, size, style.strip()), **kw)


def button(parent, text, command, kind="primary", **kw):
    colors = {"primary": (C.EMERALD, "white", C.EMERALD_DARK), "ghost": (C.SURFACE, C.TEXT, "#DDEFF0"),
              "danger": (C.SURFACE, "#C23A3A", "#FDE3E3"), "nav": (C.NAVY, "white", C.EMERALD_DARK)}
    bg, fg, active = colors[kind]
    b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=active, activeforeground=fg,
                  relief="flat", bd=0, cursor="hand2", padx=14, pady=7, font=(FONT, 10, "bold"),
                  highlightthickness=1 if kind in ("ghost", "danger") else 0, highlightbackground=C.BORDER, **kw)
    return b


def card(parent, **kw):
    return tk.Frame(parent, bg=C.CARD, highlightbackground=C.BORDER, highlightthickness=1, padx=16, pady=14, **kw)


def priority_chip(parent, priority):
    return tk.Label(parent, text=f" {priority} priority ", bg=C.PRIORITY_BG[priority], fg=C.PRIORITY_COLORS[priority],
                    font=(FONT, 9, "bold"))


def fmt12(hhmm):
    return time_label(hhmm)            # '20:15' -> '8:15 PM' 


def logo_photo(size):
    """The DrukCare logo (assets/logo.png) for Tkinter, or None when the file is missing."""
    img = I.logo_image(size)
    return ImageTk.PhotoImage(img) if img else None


def load_photo(path, size, **kw):
    """Load a local image with Pillow and make it usable in Tkinter.

    Missing / damaged files give a clean placeholder instead of an error.
    """
    return ImageTk.PhotoImage(I.load_image(path, size, **kw))


class ScrollFrame(tk.Frame):
    """A frame that scrolls vertically when its content is taller than the window."""

    def __init__(self, parent, bg=C.IVORY):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", lambda e: self._unbind_wheel())

    def _bind_wheel(self, _):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

    def _unbind_wheel(self):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(ev)

    def _wheel(self, e):
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120) if e.delta else 0, "units")


def make_tree(parent, columns, height=8):
    """columns: [(id, heading, width, anchor)]. Returns (frame, tree)."""
    frame = tk.Frame(parent, bg=C.CARD)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height, selectmode="browse")
    for cid, heading, width, anchor in columns:
        tree.heading(cid, text=heading)
        tree.column(cid, width=width, anchor=anchor, stretch=True)
    bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    tree.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    for p in S.PRIORITIES:
        tree.tag_configure(p, background=C.PRIORITY_BG[p], foreground=C.TEXT)
    tree.tag_configure("done", foreground="#7A8C99")
    return frame, tree


def style_fig(fig):
    """Dark chart colours that match the black theme."""
    for ax in fig.axes:
        ax.set_facecolor(C.CARD)
        ax.tick_params(colors=C.MUTED)
        ax.title.set_color(C.TEXT)
        ax.yaxis.label.set_color(C.MUTED)
        ax.grid(axis="y", color=C.GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for name, sp in ax.spines.items():
            sp.set_color(C.BORDER)
        for name in ("top", "right"):
            ax.spines[name].set_visible(False)
        legend = ax.get_legend()
        if legend:
            for t in legend.get_texts():
                t.set_color(C.TEXT)


def draw_ring(parent, pct, size=120, stroke=13, bg=C.CARD):
    cv = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
    pad = stroke / 2 + 2
    box = (pad, pad, size - pad, size - pad)
    cv.create_arc(*box, start=90, extent=359.9, style="arc", outline=C.TRACK, width=stroke)
    if pct > 0:
        cv.create_arc(*box, start=90, extent=-min(359.9, pct * 3.6), style="arc", outline=C.EMERALD, width=stroke)
    cv.create_text(size / 2, size / 2, text=f"{pct}%", font=(FONT, int(size / 6), "bold"), fill=C.TEXT)
    return cv


# ====================================================================== banner
class Banner(tk.Canvas):
    """A big photo banner: the WHOLE photo in full colour, a frosted panel with the title, and the user chip.

    Home uses a taller banner sized to the photo's own shape, so the full picture is visible.
    """

    def __init__(self, parent, app, page, title, subtitle, height=230):
        super().__init__(parent, height=height, highlightthickness=0, bg=C.IVORY)
        self.app, self.page, self.title, self.subtitle, self.h = app, page, title, subtitle, height
        path = C.PAGE_BANNERS.get(page, C.HOME_BANNER)
        self._src = I.load_image(path, None, label=f"Add your photo: {path}")
        self._ratio = self._src.width / max(1, self._src.height)
        self._job = None
        self._photo = None
        self._last = None
        self.chip = self._make_chip()
        self.bind("<Configure>", self._schedule)

    def _make_chip(self):
        user = self.app.user
        chip = tk.Frame(self, bg=C.CARD, padx=10, pady=4, highlightbackground=C.BORDER, highlightthickness=1)
        overdue = self.app.notification_count()
        bell = tk.Label(chip, text="🔔" if overdue == 0 else f"🔔 {overdue}", bg=C.CARD, cursor="hand2",
                        fg="#D64545" if overdue else C.MUTED, font=(FONT, 11, "bold"))
        bell.pack(side="left", padx=(0, 10))
        bell.bind("<Button-1>", lambda e: self.app.show_notifications(bell))   # click -> notifications window
        self.avatar = load_photo(I.profile_photo_path(user["User_ID"]), (30, 30), circle=True,
                                 initials="".join(w[0] for w in user["Full_Name"].replace("Dr.", "").split()[:2]).upper())
        tk.Label(chip, image=self.avatar, bg=C.CARD).pack(side="left")
        tk.Label(chip, text=user["Full_Name"], bg=C.CARD, fg=C.TEXT, font=(FONT, 10, "bold")).pack(side="left", padx=(8, 0))
        return chip

    def _schedule(self, event):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(60, lambda: self._draw(event.width))

    def _draw(self, w):
        if w < 60:
            return
        h = self.h
        if self.page == "Home":                         # tall enough to show the whole picture
            h = int(min(420, max(220, w / self._ratio)))
            if int(self.cget("height")) != h:
                self.configure(height=h)
        if self._last == (w, h):
            return
        self._last = (w, h)
        img = I.photo_card(self._src, (w, h))
        # frosted panel behind the title so the text is easy to read on any photo
        tf, sf = tkfont.Font(family=SERIF, size=26, slant="italic", weight="bold"), tkfont.Font(family=FONT, size=12)
        pw = max(tf.measure(self.title), sf.measure(self.subtitle)) + 56
        py0, py1 = h // 2 - 58, h // 2 + 52
        panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(panel).rounded_rectangle((18, py0, 18 + pw, py1), 18, fill=(250, 254, 254, 200),
                                                outline=(255, 255, 255, 230), width=2)
        self._photo = ImageTk.PhotoImage(Image.alpha_composite(img, panel))
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)
        self.create_text(44, h // 2 - 18, anchor="w", text=self.title, font=tf, fill=C.TEXT)
        self.create_text(46, h // 2 + 24, anchor="w", text=self.subtitle, font=sf, fill=C.TEXT)
        self.create_window(w - 16, 14, anchor="ne", window=self.chip)


# ============================================================ background tools
class WebLauncher:
    """Starts the Streamlit dashboard and the Gradio portal as background programs."""

    def __init__(self):
        self.procs = {}

    def _command(self, name):
        if name == "streamlit":
            return [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(C.STREAMLIT_PORT),
                    "--server.headless", "true", "--browser.gatherUsageStats", "false"], C.STREAMLIT_PORT
        return [sys.executable, "gradio_app.py", "--no-browser"], C.GRADIO_PORT

    @staticmethod
    def _port_open(port):
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            return True
        except OSError:
            return False

    def open(self, name, on_error):
        cmd, port = self._command(name)

        def work():
            try:
                if not self._port_open(port):
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    self.procs[name] = subprocess.Popen(cmd, cwd=str(C.BASE_DIR), stdout=subprocess.DEVNULL,
                                                        stderr=subprocess.DEVNULL, creationflags=flags)
                    for _ in range(80):  # wait up to ~20 seconds for the server
                        if self._port_open(port):
                            break
                        if self.procs[name].poll() is not None:
                            raise RuntimeError(f"The {name} program stopped. Did you run: pip install -r requirements.txt ?")
                        threading.Event().wait(0.25)
                webbrowser.open(f"http://localhost:{port}")
            except Exception as err:
                on_error(str(err))

        threading.Thread(target=work, daemon=True).start()

    def stop_all(self):
        for proc in self.procs.values():
            if proc.poll() is None:
                proc.terminate()


class ReminderWorker(threading.Thread):
    """Checks for due doses every 2 seconds. It NEVER touches widgets: it only fills a queue."""

    def __init__(self, out_queue, get_uid):
        super().__init__(daemon=True)
        self.out, self.get_uid, self.stop_event = out_queue, get_uid, threading.Event()
        self.alerted = set()

    def run(self):
        while not self.stop_event.wait(2.0):
            uid = self.get_uid()
            if not uid:
                continue
            try:
                # messages from a caregiver / provider (e.g. a new care plan) - always shown
                for msg in S.messages_for(uid, unread_only=True):
                    if ("msg", msg["Msg_ID"]) not in self.alerted:
                        self.alerted.add(("msg", msg["Msg_ID"]))
                        self.out.put(msg)
                if not storage.to_bool(S.get_profile(uid)["Notify_Reminders"]):
                    continue
                for dose in S.due_reminders(uid):
                    key = (dose["Med_ID"], dose["Date"], dose["Snooze_Until"])
                    if key not in self.alerted:
                        self.alerted.add(key)
                        self.out.put(dose)
            except Exception as err:
                # a temporary file problem must never stop the reminders - but say what happened
                print(f"[DrukCare reminders] check failed, will retry: {err!r}", file=sys.stderr)


def play_alert(window, sound_on):
    if not sound_on:
        return
    try:
        import winsound  # Windows only
        try:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except RuntimeError:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except ImportError:
        window.bell()


def bring_to_front(window):
    """Restore a minimised/hidden window and put it above other programs for a moment.
    On Windows a pop-up belongs to the main window, so while the main window is minimised
    its pop-ups are hidden too - that is why reminders seemed to 'not work'."""
    try:
        if window.state() in ("iconic", "withdrawn"):
            window.deiconify()
        window.lift()
        window.attributes("-topmost", True)
        window.after(400, lambda: window.attributes("-topmost", False))
    except tk.TclError:
        pass


# ================================================================== dialogs
class Dialog(tk.Toplevel):
    def __init__(self, app, title, width=470):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.configure(bg=C.IVORY, padx=22, pady=18)
        self.resizable(False, False)
        self.transient(app)
        self.width = width
        self.body = tk.Frame(self, bg=C.IVORY)
        self.body.pack(fill="both", expand=True)

    def show(self):
        self.update_idletasks()
        x = self.app.winfo_x() + (self.app.winfo_width() - max(self.width, self.winfo_reqwidth())) // 2
        y = self.app.winfo_y() + (self.app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()
        self.focus_set()

    def field(self, text, widget_factory, row):
        tk.Label(self.body, text=text, bg=C.IVORY, fg=C.MUTED, font=(FONT, 9, "bold")).grid(row=row, column=0, sticky="w", pady=(8, 0))
        w = widget_factory(self.body)
        w.grid(row=row, column=1, sticky="ew", pady=(8, 0), padx=(12, 0))
        self.body.columnconfigure(1, weight=1)
        return w


TIME_OPTIONS = time_choices(30, start_hour=5)     # '5:00 AM', '5:30 AM' ... '11:30 PM' 


def med_combo(parent, value="", width=28, dose=None):
    """Read-only dropdown listing every medicine name - nothing to type.

    Press a letter to jump to medicines starting with it. When a medicine is chosen,
    its usual dosage is filled into the `dose` dropdown automatically.
    """
    cb = ttk.Combobox(parent, values=C.MEDICINES, state="readonly", width=width, font=(FONT, 11), height=18)
    if value:
        cb.set(value)
    else:
        cb.set("Choose a medicine")

    def picked(_=None):
        if dose is not None and cb.get() in C.MEDICINE_DOSES:
            dose.set(C.MEDICINE_DOSES[cb.get()])

    def jump(e):
        ch = (e.char or "").lower()
        if not ch.isalnum():
            return
        names = [m for m in C.MEDICINES if m.lower().startswith(ch)]
        if names:
            cur = cb.get()
            nxt = names[(names.index(cur) + 1) % len(names)] if cur in names else names[0]
            cb.set(nxt)
            picked()

    cb.bind("<<ComboboxSelected>>", picked)
    cb.bind("<KeyPress>", jump)
    return cb


def dose_combo(parent, value="", width=28):
    """Dosage dropdown (filled automatically from the medicine; can still be changed)."""
    cb = ttk.Combobox(parent, values=C.DOSAGE_OPTIONS, width=width, font=(FONT, 11), height=12)
    cb.set(value)
    return cb


def time_combo(parent, value="08:00", width=28):
    """Time dropdown with AM/PM in 30-minute steps (any time such as 7:45 AM can still be typed)."""
    cb = ttk.Combobox(parent, values=TIME_OPTIONS, width=width, font=(FONT, 11), height=14)
    cb.set(time_label(value))
    return cb


class _Later:
    """Points at a widget that is created a moment later (used to link medicine -> dosage)."""

    def __init__(self, getter):
        self.getter = getter

    def set(self, value):
        w = self.getter()
        if w is not None:
            w.set(value)


def entry(parent, value="", width=30, show=None):
    e = ttk.Entry(parent, width=width, font=(FONT, 11), show=show)
    e.insert(0, value)
    return e


class MedDialog(Dialog):
    def __init__(self, app, med=None, on_saved=None):
        super().__init__(app, "Edit medication" if med else "Add medication")
        self.med, self.on_saved = med, on_saved
        m = med or {}
        self.dosage = None
        self.name = self.field("Medicine name", lambda p: med_combo(p, m.get("Med_Name", ""), 28,
                                                                    dose=_Later(lambda: self.dosage)), 0)
        self.dosage = self.field("Dosage", lambda p: dose_combo(p, m.get("Dosage", "")), 1)
        self.time = self.field("Time (e.g. 8:30 AM or 8:30 PM)", lambda p: time_combo(p, m.get("Dosage_Time", "08:00")), 2)
        self.freq = self.field("Frequency", lambda p: ttk.Combobox(p, values=S.FREQUENCIES, state="readonly", font=(FONT, 11)), 3)
        self.freq.set(m.get("Frequency", "Once daily"))
        self.prio = self.field("Priority", lambda p: ttk.Combobox(p, values=S.PRIORITIES, state="readonly", font=(FONT, 11)), 4)
        self.prio.set(m.get("Priority_Level", "Medium"))
        self.start = self.field("Start date", lambda p: entry(p, m.get("Start_Date", date.today().isoformat())), 5)
        self.end = self.field("End date (optional)", lambda p: entry(p, m.get("End_Date", "")), 6)
        self.active = tk.BooleanVar(value=storage.to_bool(m.get("Is_Active", "True")))
        if med:
            ttk.Checkbutton(self.body, text="Active (reminders on)", variable=self.active, style="Dlg.TCheckbutton").grid(row=7, column=1, sticky="w", pady=8, padx=12)
        else:
            tk.Label(self.body, text="Twice / three times daily creates extra reminders automatically.", bg=C.IVORY,
                     fg=C.MUTED, font=(FONT, 9)).grid(row=7, column=0, columnspan=2, sticky="w", pady=6)
        row = tk.Frame(self.body, bg=C.IVORY)
        row.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))
        button(row, "Cancel", self.destroy, "ghost").pack(side="left", padx=6)
        button(row, "Save", self.save).pack(side="left")
        self.show()

    def save(self):
        try:
            uid = self.app.uid
            args = (self.name.get(), self.dosage.get(), self.time.get(), self.freq.get(), self.prio.get(),
                    self.start.get(), self.end.get())
            if self.med:
                S.update_medication(self.med["Med_ID"], uid, *args, self.active.get())
                self.app.notify(f"{self.name.get()} updated")
            else:
                rows = S.add_medication(uid, *args)
                self.app.notify(f"{self.name.get()} added ({len(rows)} reminder{'s' if len(rows) > 1 else ''})")
        except (ValidationError, storage.StorageError) as err:
            return messagebox.showerror("Please check the form", str(err), parent=self)
        self.destroy()
        if self.on_saved:
            self.on_saved()


class RxDialog(Dialog):
    def __init__(self, app, on_saved, item=None):
        super().__init__(app, "Edit prescription" if item else "New prescription", 640)
        self.on_saved, self.item = on_saved, item
        self.provider = app.user["Role"] == "Provider"
        r = 0
        if self.provider:
            self.patient = self.field("Patient username", lambda p: entry(p), r)
            r += 1
        self.rx_date = self.field("Date", lambda p: entry(p, (item or {}).get("Rx_Date", date.today().isoformat())), r)
        self.note = self.field("Diagnosis / note", lambda p: entry(p, (item or {}).get("Diagnosis_Note", "")), r + 1)
        self.rows_frame = tk.Frame(self.body, bg=C.IVORY)
        self.rows_frame.grid(row=r + 2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.rows = []
        hdr = tk.Frame(self.rows_frame, bg=C.IVORY)
        hdr.pack(fill="x")
        for text, w in (("Medicine", 22), ("Dosage", 14), ("Frequency", 15), ("Days", 6)):
            tk.Label(hdr, text=text, bg=C.IVORY, fg=C.MUTED, font=(FONT, 9, "bold"), width=w, anchor="w").pack(side="left", padx=2)
        self.add_row(item)
        if not item:
            button(self.body, "+ Add another medicine", self.add_row, "ghost").grid(row=r + 3, column=0, columnspan=2, sticky="w", pady=8)
        bottom = tk.Frame(self.body, bg=C.IVORY)
        bottom.grid(row=r + 4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        button(bottom, "Cancel", self.destroy, "ghost").pack(side="left", padx=6)
        button(bottom, "Save prescription", self.save).pack(side="left")
        self.show()

    def add_row(self, item=None):
        f = tk.Frame(self.rows_frame, bg=C.IVORY)
        f.pack(fill="x", pady=2)
        it = item if isinstance(item, dict) else {}
        dose = dose_combo(f, it.get("Dosage", ""), 14)
        name = med_combo(f, it.get("Med_Name", ""), 22, dose=dose)
        freq = ttk.Combobox(f, values=S.FREQUENCIES, state="readonly", width=14, font=(FONT, 11))
        freq.set(it.get("Frequency", "Once daily"))
        days = entry(f, str(it.get("Duration_Days", "7")), 6)
        for w in (name, dose, freq, days):
            w.pack(side="left", padx=2)
        self.rows.append((name, dose, freq, days))

    def save(self):
        items = [{"Med_Name": n.get(), "Dosage": d.get(), "Frequency": f.get(), "Duration_Days": u.get()}
                 for n, d, f, u in self.rows if n.get() in C.MEDICINE_DOSES]
        me = self.app.user
        try:
            if self.item:
                it = items[0] if items else {}
                S.update_prescription_item(self.item["Item_ID"], me["User_ID"], it.get("Med_Name"), it.get("Dosage"),
                                           it.get("Frequency"), it.get("Duration_Days"), self.rx_date.get(), self.note.get())
            else:
                if self.provider:
                    patient = S.find_user(self.patient.get())
                    if not patient or patient["Role"] != "Patient":
                        raise ValidationError("No patient account was found with that username.")
                    pid = patient["User_ID"]
                else:
                    pid = me["User_ID"]
                S.create_prescription(me["User_ID"], pid, self.rx_date.get(), self.note.get(), items)
                self.app.notify("Prescription saved")
        except (ValidationError, storage.StorageError) as err:
            return messagebox.showerror("Please check the form", str(err), parent=self)
        self.destroy()
        self.on_saved()


class ScheduleDialog(Dialog):
    def __init__(self, app, item, on_saved):
        super().__init__(app, "Add to my schedule", 380)
        self.item, self.on_saved = item, on_saved
        tk.Label(self.body, text=f"Create reminders for {item['Med_Name']}", bg=C.IVORY, fg=C.TEXT,
                 font=(FONT, 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        self.time = self.field("First dose time (e.g. 8:00 AM)", lambda p: time_combo(p, "08:00", 20), 1)
        self.prio = self.field("Priority colour", lambda p: ttk.Combobox(p, values=S.PRIORITIES, state="readonly", font=(FONT, 11)), 2)
        self.prio.set("Medium")
        row = tk.Frame(self.body, bg=C.IVORY)
        row.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        button(row, "Cancel", self.destroy, "ghost").pack(side="left", padx=6)
        button(row, "Add", self.save).pack(side="left")
        self.show()

    def save(self):
        try:
            S.schedule_prescription_item(self.app.uid, self.item["Item_ID"], self.time.get(), self.prio.get())
            self.app.notify(f"{self.item['Med_Name']} added to your schedule")
        except (ValidationError, storage.StorageError) as err:
            return messagebox.showerror("Cannot add", str(err), parent=self)
        self.destroy()
        self.on_saved()


class MessagePopup(tk.Toplevel):
    """A message from the patient's caregiver or doctor (for example a new care plan)."""

    def __init__(self, app, msg, offset=0):
        super().__init__(app)
        self.app, self.msg = app, msg
        self.title("DrukCare message")
        self.configure(bg=C.CARD)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        head = tk.Frame(self, bg=C.TEAL_DARK if hasattr(C, "TEAL_DARK") else "#01333C")
        head.pack(fill="x")
        who = f"{msg['Sender_Name']} ({msg['Sender_Role'].lower()})" if msg["Sender_Role"] else msg["Sender_Name"]
        tk.Label(head, text=f"📨  New message from {who}", bg=head["bg"], fg="white",
                 font=(FONT, 13, "bold"), padx=20, pady=12).pack(anchor="w")
        tk.Label(self, text=msg["Title"], bg=C.CARD, fg=C.TEXT, font=(FONT, 16, "bold"), padx=24,
                 wraplength=520, justify="left").pack(anchor="w", pady=(16, 4))
        tk.Label(self, text=msg["Body"], bg=C.CARD, fg=C.TEXT, font=(FONT, 12), padx=24,
                 wraplength=520, justify="left").pack(anchor="w", pady=(0, 6))
        tk.Label(self, text=f"Sent {msg['Sent_At'][:16]}", bg=C.CARD, fg=C.MUTED, font=(FONT, 10), padx=24).pack(anchor="w")
        row = tk.Frame(self, bg=C.CARD, padx=24, pady=4)
        row.pack(fill="x", pady=(12, 18))
        tk.Button(row, text="✓  OK, got it", command=self.read, bg=C.EMERALD, fg="white", relief="flat",
                  font=(FONT, 13, "bold"), padx=18, pady=10, cursor="hand2").pack(side="left")
        tk.Button(row, text="Later", command=self.destroy, bg=C.SURFACE, fg=C.TEXT, relief="flat",
                  font=(FONT, 12), padx=14, pady=10, cursor="hand2").pack(side="left", padx=10)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        grabber = self.grab_current()
        if grabber is not None:
            grabber.grab_release()
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{max(0, (sw - w) // 2 + offset)}+{max(0, (sh - h) // 3 + offset)}")
        self.deiconify()
        self.lift()
        self.after(50, self.focus_force)

    def read(self):
        S.mark_messages_read(self.msg["Patient_ID"], [self.msg["Msg_ID"]])
        self.destroy()
        self.app.refresh_page()


class ReminderPopup(tk.Toplevel):
    """The big, easy-to-read reminder pop-up (made for elderly users)."""

    def __init__(self, app, dose, offset=0):
        super().__init__(app)
        self.app, self.dose = app, dose
        color = C.PRIORITY_COLORS[dose["Priority_Level"]]
        self.title("DrukCare reminder")
        self.configure(bg=C.CARD)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        head = tk.Frame(self, bg=color)
        head.pack(fill="x")
        tk.Label(head, text=f"⏰  Time for your medicine  ·  {dose['Priority_Level']} priority", bg=color, fg="white",
                 font=(FONT, 13, "bold"), padx=20, pady=12).pack(anchor="w")
        tk.Label(self, text=dose["Med_Name"], bg=C.CARD, fg=C.TEXT, font=(FONT, 24, "bold"), padx=24).pack(anchor="w", pady=(18, 0))
        tk.Label(self, text=f"{dose['Dosage']}  ·  scheduled {fmt12(dose['Dosage_Time'])}", bg=C.CARD, fg=C.MUTED,
                 font=(FONT, 14), padx=24).pack(anchor="w", pady=(2, 16))
        snooze = int(S.get_profile(app.uid)["Snooze_Min"] or 10)
        row = tk.Frame(self, bg=C.CARD, padx=24, pady=4)
        row.pack(fill="x", pady=(0, 18))
        tk.Button(row, text="✓  Mark as taken", command=lambda: self.act("Taken", snooze), bg=C.EMERALD, fg="white", relief="flat",
                  font=(FONT, 13, "bold"), padx=18, pady=10, cursor="hand2").pack(side="left")
        tk.Button(row, text=f"Snooze {snooze} min", command=lambda: self.act("Snoozed", snooze), bg=C.SURFACE, fg=C.TEXT, relief="flat",
                  font=(FONT, 12), padx=14, pady=10, cursor="hand2").pack(side="left", padx=10)
        tk.Button(row, text="Dismiss", command=self.destroy, bg=C.CARD, fg=C.MUTED, relief="flat",
                  font=(FONT, 11), padx=8, pady=10, cursor="hand2").pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        # an open dialog (e.g. "Add medicine") grabs all clicks - release it so these buttons work
        grabber = self.grab_current()
        if grabber is not None:
            grabber.grab_release()
        self.update_idletasks()
        # place it on the visible screen (a minimised window reports x/y of about -32000 on Windows)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x, y = app.winfo_rootx() + 120 + offset, app.winfo_rooty() + 100 + offset
        if not (0 <= x <= sw - w and 0 <= y <= sh - h):
            x, y = (sw - w) // 2 + offset, (sh - h) // 3 + offset
        self.geometry(f"+{max(0, min(x, sw - w))}+{max(0, min(y, sh - h))}")
        self.deiconify()
        self.lift()
        self.after(50, self.focus_force)

    def act(self, status, snooze):
        try:
            S.set_dose_status(self.app.uid, self.dose["Med_ID"], status, self.dose["Date"], snooze)
        except (ValidationError, storage.StorageError) as err:
            messagebox.showerror("DrukCare", str(err), parent=self)
        self.destroy()
        self.app.refresh_page()


class NotificationPanel(tk.Toplevel):
    """Opens when the 🔔 is clicked: overdue doses (with Taken / Snooze), later doses, today's activity."""

    def __init__(self, app, x, y):
        super().__init__(app)
        self.app = app
        self.title("Notifications")
        self.configure(bg=C.CARD, padx=18, pady=14)
        self.resizable(False, False)
        self.transient(app)
        self.bind("<Escape>", lambda e: self.destroy())
        self.build()
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{max(0, min(x - w, sw - w))}+{max(0, min(y, sh - h - 40))}")
        self.lift()
        self.focus_force()

    def section(self, text, color=C.TEXT):
        label(self, text, 11, True, color).pack(anchor="w", pady=(10, 4))

    def line(self, text, color=C.MUTED):
        label(self, text, 10, color=color, wraplength=420, justify="left").pack(anchor="w", pady=1)

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        label(self, "🔔  Notifications", 14, True, family=SERIF).pack(anchor="w")
        uid = self.app.uid
        if not uid:                                   # caregiver / provider accounts have no doses of their own
            self.line("Medicine reminders are shown for patient accounts.")
            self.footer()
            return
        n = S.notifications(uid)
        if n.get("messages"):
            self.section("New messages", C.EMERALD_DARK)
            for m in n["messages"]:
                self.line(f"📨  {m['Title']}", C.TEXT)
                for ln in m["Body"].splitlines():
                    self.line(f"      {ln}")
            button(self, "Mark messages as read", self.read_all, "ghost").pack(anchor="w", pady=(4, 0))
        if n["attention"]:
            self.section("Needs attention", "#C23A3A")
            for d in n["attention"]:
                row = tk.Frame(self, bg=C.CARD)
                row.pack(fill="x", pady=3)
                label(row, f"⏰  {d['Med_Name']}", 11, True).pack(side="left")
                label(row, f"  {d['Dosage']} · {fmt12(d['Dosage_Time'])} · {d['When']}", 10, color=C.MUTED).pack(side="left")
                button(row, "Snooze", lambda d=d: self.act(d, "Snoozed"), "ghost").pack(side="right", padx=(6, 0))
                button(row, "✓ Taken", lambda d=d: self.act(d, "Taken")).pack(side="right")
        if n["upcoming"]:
            self.section("Later today")
            for d in n["upcoming"][:5]:
                extra = f" · snoozed until {fmt12(d['Snooze_Until'])}" if d["Status"] == "Snoozed" and d["Snooze_Until"] else ""
                self.line(f"💊  {d['Med_Name']} at {fmt12(d['Dosage_Time'])}{extra}", C.TEXT)
        if n["activity"]:
            self.section("Today")
            for a in n["activity"]:
                self.line(f"{a['icon']}  {a['text']}  {a['detail']}", C.TEXT)
        if self.app.recent:
            self.section("Recent")
            for when, text in reversed(self.app.recent[-6:]):
                self.line(f"•  {text}  ({when})")
        if not (n.get("messages") or n["attention"] or n["upcoming"] or n["activity"] or self.app.recent):
            self.line("Nothing new. You're all caught up 🎉")
        self.footer()

    def footer(self):
        button(self, "Close", self.destroy, "ghost").pack(anchor="e", pady=(12, 0))

    def read_all(self):
        S.mark_messages_read(self.app.uid)
        self.app.refresh_page()
        if self.winfo_exists():
            self.build()

    def act(self, dose, status):
        self.app.mark(dose["Med_ID"], dose["Date"], status)
        if self.winfo_exists():
            self.build()


# =================================================================== the app
class DrukCareApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DrukCare - Medication Reminder and Daily Exercise Planner")
        # open as a 16:9 window (same shape as the login design) that fits the screen
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1440, sw - 40)
        h = round(w * 9 / 16)
        if h > sh - 90:
            h = sh - 90
            w = round(h * 16 / 9)
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 20)}")
        self.minsize(1120, 630)
        self.configure(bg=C.IVORY)
        self._icon = logo_photo(64)
        if self._icon:
            self.iconphoto(True, self._icon)
        storage.init_storage()
        seed.remove_demo_data()   # deletes the old fictional demo accounts if they still exist
        self.user = None
        self.page = "Home"
        self.state_memory = {}
        self.launcher = WebLauncher()
        self.reminders = queue.Queue()
        self.worker = ReminderWorker(self.reminders, lambda: self.uid)
        self._popups = 0
        self.recent = []          # (time, text) of things done in this session, shown under the bell
        self._notif = None
        self._setup_styles()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(500, self._poll_reminders)
        self.worker.start()
        self.show_login()

    # ------------------------------------------------------------ plumbing
    @property
    def uid(self):
        return self.user["User_ID"] if self.user and self.user["Role"] == "Patient" else None

    viewer_id = uid

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", font=(FONT, 11), rowheight=34, background=C.CARD, fieldbackground=C.CARD, foreground=C.TEXT, borderwidth=0)
        s.configure("Treeview.Heading", font=(FONT, 10, "bold"), background=C.NAVY, foreground="white", relief="flat", padding=6)
        s.map("Treeview.Heading", background=[("active", C.NAVY)])
        s.map("Treeview", background=[("selected", C.EMERALD)], foreground=[("selected", "white")])
        s.configure("TNotebook", background=C.IVORY, borderwidth=0)
        s.configure("TNotebook.Tab", font=(FONT, 10, "bold"), padding=(12, 7), background=C.SURFACE, foreground=C.TEXT)
        s.map("TNotebook.Tab", background=[("selected", C.EMERALD)], foreground=[("selected", "white")])
        s.configure("TEntry", padding=5, fieldbackground=C.SURFACE, foreground=C.TEXT, insertcolor=C.TEXT)
        s.configure("TCombobox", fieldbackground=C.SURFACE, background=C.SURFACE, foreground=C.TEXT, arrowcolor=C.TEXT)
        s.map("TCombobox", fieldbackground=[("readonly", C.SURFACE)], foreground=[("readonly", C.TEXT)])
        s.configure("TCheckbutton", background=C.CARD, foreground=C.TEXT)
        s.configure("Dlg.TCheckbutton", background=C.IVORY, foreground=C.TEXT)
        s.configure("TScrollbar", background=C.SURFACE, troughcolor=C.IVORY, arrowcolor=C.MUTED)
        for opt, val in (("background", C.SURFACE), ("foreground", C.TEXT), ("selectBackground", C.EMERALD)):
            self.option_add(f"*TCombobox*Listbox.{opt}", val)
        s.configure("Green.Horizontal.TProgressbar", troughcolor=C.TRACK, background=C.EMERALD, thickness=10, borderwidth=0)

    def safe(self, func, *args, parent=None):
        """Run a service call; show a friendly dialog on an error."""
        try:
            return func(*args)
        except (ValidationError, storage.StorageError) as err:
            messagebox.showerror("DrukCare", str(err), parent=parent or self)
        except Exception as err:  # unexpected
            messagebox.showerror("DrukCare", f"Something went wrong: {err}", parent=parent or self)
        return None

    def _poll_reminders(self):
        try:
            while True:
                dose = self.reminders.get_nowait()
                if not self.uid:
                    continue
                try:
                    prof = S.get_profile(self.uid)
                    bring_to_front(self)
                    popup = MessagePopup if "Msg_ID" in dose else ReminderPopup
                    popup(self, dose, offset=(self._popups % 4) * 26)
                    self._popups += 1
                    play_alert(self, storage.to_bool(prof["Sound_On"]))
                    self.refresh_page()
                except Exception as err:  # one bad reminder must not stop all the others
                    print(f"[DrukCare reminders] could not show pop-up: {err!r}", file=sys.stderr)
        except queue.Empty:
            pass
        finally:
            # ALWAYS check again in half a second, even if something above went wrong
            self.after(500, self._poll_reminders)

    def open_web(self, kind):
        """Start (if needed) and open the Streamlit dashboard or the Gradio portal in the browser."""
        self.launcher.open(kind, lambda m: self.after(0, lambda: messagebox.showerror("DrukCare", m)))

    def notify(self, text):
        """Remember an action (e.g. 'Paracetamol added') for the bell's Recent list."""
        self.recent.append((datetime.now().strftime("%I:%M %p").lstrip("0"), text))
        del self.recent[:-20]

    def notification_count(self):
        return S.notifications(self.uid)["count"] if self.uid else 0

    def show_notifications(self, anchor):
        if self._notif is not None and self._notif.winfo_exists():
            self._notif.destroy()
        x = anchor.winfo_rootx() + anchor.winfo_width() + 120
        y = anchor.winfo_rooty() + anchor.winfo_height() + 12
        self._notif = NotificationPanel(self, x, y)

    def on_close(self):
        self.worker.stop_event.set()
        self.launcher.stop_all()
        self.destroy()

    def clear(self):
        for w in self.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()

    # --------------------------------------------------------------- login
    def show_login(self):
        """Login / create-account screen drawn exactly like the 16:9 design sample.

        * the background picture (assets/login_full.jpg) fills the whole window and is scaled evenly
          (never stretched) - dragon top-left, medical bag bottom-left, dzong in the middle,
          DrukCare logo top-right
        * the frosted login card (about 520 x 500 px) sits on the right, under the logo
        * card, tabs, fields and buttons are painted with Pillow (rounded corners, see-through card);
          only the text boxes are real Tkinter widgets placed on top
        """
        self.user = None
        self.clear()
        cv = tk.Canvas(self, highlightthickness=0, bg=C.IVORY, bd=0)
        cv.pack(fill="both", expand=True)
        src_path = I.find_image(C.LOGIN_FULL)
        try:
            src = Image.open(src_path).convert("RGB") if src_path else None
        except Exception:
            src = None
        SW, SH = (src.size if src else (1672, 941))
        icons = {}
        for key, path in (("knot", "assets/login_knot.png"), ("heart", "assets/login_heart.png")):
            f = I.find_image(path)
            if f:
                try:
                    icons[key] = Image.open(f).convert("RGBA")
                except Exception:
                    pass

        TEAL, TEAL_DARK, INK, GREY_TXT = "#13979D", "#0B4F5C", "#12304A", "#7C8C99"
        CW, CH = 520, 500                       # login card size (pixels at full size)
        fonts = {n: tkfont.Font(family=FONT, size=sz, weight=wt) for n, sz, wt in (
            ("tab", 13, "bold"), ("field", 12, "normal"), ("small", 10, "normal"), ("label", 9, "bold"),
            ("btn", 14, "bold"), ("icon", 13, "normal"), ("foot", 9, "normal"), ("err", 9, "normal"),
            ("val", 8, "normal"))}
        base_sizes = {n: f.cget("size") for n, f in fonts.items()}
        st_ = {"tab": "in", "widgets": [], "fields": [], "bg": None, "bgsize": None, "photo": None,
               "job": None, "hot": [], "msg": "", "geo": None, "checks": [], "P": None}

        # ---------------------------------------------------------- text boxes
        class HintEntry(tk.Entry):
            """Borderless entry with grey hint text (placeholder) and optional hidden text."""

            def __init__(self, parent, hint, secret=False):
                super().__init__(parent, relief="flat", bd=0, bg="white", fg=GREY_TXT, font=fonts["field"],
                                 insertbackground=TEAL_DARK, highlightthickness=0)
                self.hint, self.secret, self.empty, self.shown = hint, secret, True, False
                self.bind("<FocusIn>", self._in)
                self.bind("<FocusOut>", self._out)
                self._out()

            def _in(self, _=None):
                if self.empty:
                    self.delete(0, "end")
                    self.config(fg=INK, show="•" if self.secret and not self.shown else "")
                    self.empty = False

            def _out(self, _=None):
                if not super().get():
                    self.empty = True
                    self.config(fg=GREY_TXT, show="")
                    self.insert(0, self.hint)

            def toggle(self):
                self.shown = not self.shown
                if not self.empty:
                    self.config(show="" if self.shown else "•")
                return self.shown

            def value(self):
                return "" if self.empty else super().get().strip() if not self.secret else super().get()

        s_ = ttk.Style(self)
        s_.configure("Login.TCombobox", fieldbackground="white", background="white", foreground=INK,
                     arrowcolor=TEAL_DARK, borderwidth=0, relief="flat", padding=2)
        s_.map("Login.TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)],
               selectbackground=[("readonly", "white")], selectforeground=[("readonly", INK)])

        def add_field(box, icon, widget, eye=None):
            """box = (x0, y0, x1, y1) inside the card at full size."""
            win = cv.create_window(0, 0, window=widget, anchor="w")
            eye_win = cv.create_window(0, 0, window=eye, anchor="e") if eye else None
            st_["fields"].append({"box": box, "icon": icon, "win": win, "eye": eye_win, "w": widget, "eyew": eye})

        def make_eye(entry_):
            lab = tk.Label(cv, text="👁", bg="white", fg=TEAL_DARK, font=fonts["icon"], cursor="hand2")
            lab.bind("<Button-1>", lambda e: lab.config(text="🙈" if entry_.toggle() else "👁"))
            return lab

        # ---------------------------------------------------------- live (as-you-type) validation
        RED, GREEN = "#B02A2A", "#1E8E5A"

        def add_check(widget, check, box, tick_y=None):
            """Check `widget` while the user types and show a short red message under its box.
            check() returns "" (fine) or a short message. box = the field box (x0, y0, x1, y1).
            tick_y = where to put a green ✓ when the value is fine (None = no tick)."""
            rec = {"w": widget, "check": check, "box": box, "tick_y": tick_y,
                   "touched": False, "err": "", "job": None}
            st_["checks"].append(rec)

            def typed(e):
                if e.keysym in ("Return", "KP_Enter", "Tab", "ISO_Left_Tab", "Shift_L", "Shift_R"):
                    return
                rec["touched"] = True
                if rec["job"]:
                    cv.after_cancel(rec["job"])
                rec["job"] = cv.after(300, check_touched)      # wait for a short pause in typing

            def left(_=None):
                if rec["touched"]:
                    check_touched()

            widget.bind("<KeyRelease>", typed, add="+")
            widget.bind("<FocusOut>", left, add="+")
            return rec

        def check_touched():
            """Re-check every field the user has typed in (so 'confirm password' updates too)."""
            if not cv.winfo_exists():
                return
            for rec in st_["checks"]:
                rec["job"] = None
                if rec["touched"] and rec["w"].winfo_exists():
                    rec["err"] = rec["check"]()
            if st_["msg"]:                                      # old message from the button is out of date
                st_["msg"] = ""
                render(rebuild_bg=False)                        # render() also redraws the checks
            else:
                draw_checks()

        def check_all():
            """Used by the button: check every field now. Returns the first field with a problem."""
            first = None
            for rec in st_["checks"]:
                rec["touched"] = True
                rec["err"] = rec["check"]()
                if rec["err"] and first is None:
                    first = rec
            draw_checks()
            return first

        def draw_checks():
            cv.delete("val")
            P = st_["P"]
            if not P:
                return
            k = st_["k"]
            for rec in st_["checks"]:
                if not rec["touched"]:
                    continue
                x0, y0, x1, y1 = rec["box"]
                if rec["err"]:
                    # red line along the bottom of the text box + message under it
                    cv.create_line(*P(x0 + 10, y1 - 1), *P(x1 - 10, y1 - 1), fill=RED, width=2, tags="val")
                    cv.create_text(*P(x0 + 4, y1 + 9), text="⚠ " + rec["err"], anchor="w", font=fonts["val"],
                                   fill=RED, width=int((x1 - x0) * k), tags="val")
                elif rec["tick_y"] is not None and rec["w"].value():
                    cv.create_text(*P(x1 - 4, rec["tick_y"]), text="✓", anchor="e", font=fonts["label"],
                                   fill=GREEN, tags="val")

        # ---------------------------------------------------------- the two forms
        def build_login():
            u = HintEntry(cv, "Username or CID")
            p = HintEntry(cv, "Password", secret=True)
            add_field((32, 108, 488, 166), "👤", u)
            add_field((32, 186, 488, 244), "🔒", p, make_eye(p))
            add_check(u, lambda: live_check("login_username", u.value()), (32, 108, 488, 166))
            add_check(p, lambda: "" if p.value() else "Password is required", (32, 186, 488, 244))

            def do_login(_=None):
                bad = check_all()
                if bad:
                    bad["w"].focus_set()
                    return
                try:
                    self.user = S.authenticate(u.value(), p.value())
                except (ValidationError, storage.StorageError) as err:
                    return show_msg(str(err))
                self.page = "Home"
                self.show_shell()

            for w in (u, p):
                w.bind("<Return>", do_login)
            st_["action"] = do_login
            st_["widgets"] = [u, p]
            u.focus_set()

        def build_signup():
            name, uname = HintEntry(cv, "Full name"), HintEntry(cv, "Username")
            email, phone = HintEntry(cv, "Email address"), HintEntry(cv, "Phone number")
            cid = HintEntry(cv, "11-digit CID")
            role = ttk.Combobox(cv, values=S.ROLES, state="readonly", style="Login.TCombobox", font=fonts["field"])
            role.set("Patient")
            pw, pw2 = HintEntry(cv, "Password", secret=True), HintEntry(cv, "Confirm password", secret=True)
            L, R = (26, 252), (268, 494)
            rows = [(("Full name", "🪪", name), ("Username", "👤", uname)),
                    (("Email", "✉", email), ("Phone", "☎", phone)),
                    (("CID (citizenship ID)", "🆔", cid), ("I am a", "", role)),
                    (("Password", "🔒", pw), ("Confirm password", "🔒", pw2))]
            st_["labels"] = []
            for i, pair in enumerate(rows):
                ly = 100 + i * 76
                for (text, icon, widget), (x0, x1) in zip(pair, (L, R)):
                    st_["labels"].append((x0 + 2, ly, text))
                    add_field((x0, ly + 12, x1, ly + 54), icon, widget)

            # live checks: (widget, field rule, row, column)
            taken = lambda n: S.find_user(n) is not None
            rules = [(name, lambda: live_check("name", name.value()), 0, L),
                     (uname, lambda: live_check("username", uname.value(), taken=taken), 0, R),
                     (email, lambda: live_check("email", email.value()), 1, L),
                     (phone, lambda: live_check("phone", phone.value()), 1, R),
                     (cid, lambda: live_check("cid", cid.value(), taken=lambda c: S.find_user_by_cid(c) is not None), 2, L),
                     (pw, lambda: live_check("password", pw.value()), 3, L),
                     (pw2, lambda: live_check("confirm", pw2.value(), password=pw.value()), 3, R)]
            for widget, rule, i, (x0, x1) in rules:
                ly = 100 + i * 76
                add_check(widget, rule, (x0, ly + 12, x1, ly + 54), tick_y=ly)

            def do_register(_=None):
                bad = check_all()
                if bad:
                    bad["w"].focus_set()
                    return
                try:
                    mail = validate_email(email.value())
                    user = S.register_user(name.value(), uname.value(), pw.value(), pw2.value(), role.get(),
                                           "", phone.value(), cid=cid.value())
                    if mail:
                        S.save_profile(user["User_ID"], Email=mail)
                except (ValidationError, storage.StorageError) as err:
                    return show_msg(str(err))
                self.user = user
                self.page = "Home"
                self.show_shell()

            for w in (name, uname, email, phone, cid, pw, pw2):
                w.bind("<Return>", do_register)
            st_["action"] = do_register
            st_["widgets"] = [name, uname, email, phone, dob, role, pw, pw2]
            name.focus_set()

        def forgot():
            messagebox.showinfo("Forgot your password?",
                                "Password reset is not available in this version of DrukCare.\n\n"
                                "Please create a new account, or ask the person who set up DrukCare to help you.")

        def show_msg(text):
            st_["msg"] = text
            render(rebuild_bg=False)

        def show_tab(key):
            st_["tab"], st_["msg"] = key, ""
            for f in st_["fields"]:
                cv.delete(f["win"])
                f["w"].destroy()
                if f["eye"]:
                    cv.delete(f["eye"])
                    f["eyew"].destroy()
            st_["fields"], st_["labels"], st_["checks"] = [], [], []
            cv.delete("val")
            (build_login if key == "in" else build_signup)()
            render()

        # ---------------------------------------------------------- drawing
        def card_overlay(k):
            """The frosted card with tabs, field boxes and button, drawn at 2x then smoothed."""
            SS, M = 2, 26
            ow, oh = int((CW + 2 * M) * k), int((CH + 2 * M) * k)
            z = lambda v: int(v * k * SS)                          # full-size card units -> overlay pixels
            img = Image.new("RGBA", (ow * SS, oh * SS), (0, 0, 0, 0))
            m = z(M)
            # soft shadow
            sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle((m, m + z(8), m + z(CW), m + z(CH) + z(8)), z(24), fill=(0, 60, 70, 60))
            img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(z(14))))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((m, m, m + z(CW), m + z(CH)), z(24), fill=(247, 252, 252, 214),
                                outline=(155, 211, 210, 255), width=max(2, z(2)))
            on, off = (19, 151, 157, 255), (227, 241, 242, 235)
            d.rounded_rectangle((m + z(26), m + z(22), m + z(254), m + z(84)), z(14), fill=on if st_["tab"] == "in" else off)
            d.rounded_rectangle((m + z(266), m + z(22), m + z(494), m + z(84)), z(14), fill=on if st_["tab"] == "up" else off)
            for f in st_["fields"]:
                x0, y0, x1, y1 = f["box"]
                d.rounded_rectangle((m + z(x0), m + z(y0), m + z(x1), m + z(y1)), z(10), fill=(255, 255, 255, 255),
                                    outline=(185, 214, 220, 255), width=max(2, z(1)))
            btn = (32, 266, 488, 324) if st_["tab"] == "in" else (26, 420, 494, 472)
            d.rounded_rectangle((m + z(btn[0]), m + z(btn[1]), m + z(btn[2]), m + z(btn[3])), z(12), fill=on)
            if st_["tab"] == "in":
                for xa, xb in ((40, 230), (290, 480)):
                    d.line((m + z(xa), m + z(398), m + z(xb), m + z(398)), fill=(155, 211, 210, 255), width=max(2, z(1)))
            img = img.resize((ow, oh), Image.LANCZOS)
            if st_["tab"] == "in":
                for key, cx, cy, wd in (("knot", 260, 398, 34), ("heart", 260, 438, 54)):
                    if key in icons:
                        ic = icons[key].copy()
                        ic.thumbnail((int(wd * k), int(wd * k)), Image.LANCZOS)
                        img.alpha_composite(ic, (int((M + cx) * k - ic.width / 2), int((M + cy) * k - ic.height / 2)))
            st_["btn"] = btn
            return img, int(M * k)

        def render(rebuild_bg=True):
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 200 or h < 200:
                return
            s = max(w / SW, h / SH)                                 # "cover": fills the window, never stretched
            iw, ih = int(SW * s + 0.5), int(SH * s + 0.5)
            ox, oy = (w - iw) // 2, (h - ih) // 2
            if st_["bgsize"] != (iw, ih):
                st_["bg"] = (src.resize((iw, ih), Image.LANCZOS) if src else Image.new("RGB", (iw, ih), C.IVORY)).convert("RGBA")
                st_["bgsize"] = (iw, ih)
            # card: right side, below the logo + tagline (same place as in the sample)
            under_logo = oy + 262 * s
            k = max(0.78, min(1.0, (h - 18 - under_logo) / CH, (w * 0.42) / CW))
            cw, ch = CW * k, CH * k
            x0 = min(ox + 1298 * s - cw / 2, w - cw - 28)
            y0 = max(14, min(oy + 276 * s, h - ch - 18))
            ov, mpx = card_overlay(k)
            frame = Image.new("RGBA", (w, h), C.IVORY)
            frame.alpha_composite(st_["bg"], (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy)))
            frame.alpha_composite(ov, (int(x0) - mpx, int(y0) - mpx))
            st_["photo"] = ImageTk.PhotoImage(frame)
            cv.delete("deco")
            cv.create_image(0, 0, anchor="nw", image=st_["photo"], tags="deco")
            cv.tag_lower("deco")
            P = lambda x, y: (x0 + x * k, y0 + y * k)
            st_["P"], st_["k"] = P, k
            for n, f in fonts.items():
                f.configure(size=max(7, round(base_sizes[n] * k)))
            # tab texts
            for key, cx, text in (("in", 140, "👤  Log In"), ("up", 380, "➕  Create Account")):
                cv.create_text(*P(cx, 53), text=text, font=fonts["tab"], tags="deco",
                               fill="white" if st_["tab"] == key else INK)
            # fields
            for f in st_["fields"]:
                fx0, fy0, fx1, fy1 = f["box"]
                left = 44 if f["icon"] else 10
                if f["icon"]:
                    cv.create_text(*P(fx0 + 22, (fy0 + fy1) / 2), text=f["icon"], font=fonts["icon"], fill=TEAL_DARK, tags="deco")
                right = 40 if f["eye"] else 10
                cv.coords(f["win"], *P(fx0 + left, (fy0 + fy1) / 2))
                cv.itemconfigure(f["win"], width=int((fx1 - fx0 - left - right) * k), height=int((fy1 - fy0 - 14) * k))
                if f["eye"]:
                    cv.coords(f["eye"], *P(fx1 - 10, (fy0 + fy1) / 2))
            for lx, ly, text in st_.get("labels", []):
                cv.create_text(*P(lx, ly), text=text, anchor="w", font=fonts["label"], fill=TEAL_DARK, tags="deco")
            b = st_["btn"]
            cv.create_text(*P((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), text="Log In" if st_["tab"] == "in" else "Create Account",
                           font=fonts["btn"], fill="white", tags="deco")
            hot = [((26, 22, 254, 84), lambda: show_tab("in")), ((266, 22, 494, 84), lambda: show_tab("up")),
                   (b, lambda: st_["action"]())]
            if st_["tab"] == "in":
                cv.create_text(*P(260, 350), text="Forgot your password?", font=fonts["small"], fill=TEAL, tags="deco")
                hot.append(((175, 338, 345, 362), forgot))
                cv.create_text(*P(260, 476), text="HEALTH   •   COMPASSION   •   CARE", font=fonts["foot"], fill=TEAL, tags="deco")
                if "heart" not in icons:
                    cv.create_text(*P(260, 438), text="♡", font=fonts["btn"], fill=TEAL, tags="deco")
                msg_y = 376
            else:
                msg_y = 406
            if st_["msg"]:
                cv.create_text(*P(260, msg_y), text=st_["msg"], font=fonts["err"], fill="#B02A2A", width=int(456 * k),
                               justify="center", tags="deco")
            draw_checks()
            st_["hot"] = [((x0 + a * k, y0 + bb * k, x0 + c * k, y0 + d * k), fn) for (a, bb, c, d), fn in hot]

        def hit(e):
            for (a, b, c, d), fn in st_["hot"]:
                if a <= e.x <= c and b <= e.y <= d:
                    return fn
            return None

        cv.bind("<Button-1>", lambda e: (hit(e) or (lambda: None))())
        cv.bind("<Motion>", lambda e: cv.config(cursor="hand2" if hit(e) else ""))

        def on_resize(_=None):
            if st_["job"]:
                cv.after_cancel(st_["job"])
            st_["job"] = cv.after(40, render)

        cv.bind("<Configure>", on_resize)
        show_tab("in")
        cv.after(120, render)

    # --------------------------------------------------------------- shell
    def show_shell(self):
        """Main window: sidebar in the design-sample colours (logo, teal pill menu, dragon) + page area."""
        self.clear()
        BG, FG = C.NAVY, "#E8F5F4"
        side = tk.Frame(self, bg=BG, width=240)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        # logo: cross + DrukCare + tagline (assets/logo_sidebar.png)
        logo_img = I.find_image(C.LOGO_SIDEBAR)
        if logo_img:
            self._side_logo = load_photo(C.LOGO_SIDEBAR, (150, 110), contain=True)
            tk.Label(side, image=self._side_logo, bg=BG).pack(pady=(18, 0))
        else:
            row = tk.Frame(side, bg=BG)
            row.pack(pady=(24, 0))
            tk.Label(row, text="Druk", bg=BG, fg="white", font=(SERIF, 22, "bold")).pack(side="left")
            tk.Label(row, text="Care", bg=BG, fg=C.TEAL_LIGHT, font=(SERIF, 22, "bold")).pack(side="left")
        tk.Label(side, text=C.TAGLINE, bg=BG, fg="white", font=(FONT, 9)).pack(pady=(2, 16))
        self.nav_buttons = {}
        names = NAV if self.user["Role"] == "Patient" else NAV_OTHER

        def paint(item, colour):
            for w in (item, *item.winfo_children()):
                w.config(bg=colour)

        for name, icon in names:
            item = tk.Frame(side, bg=BG, cursor="hand2", padx=14, pady=9)
            item.pack(fill="x", padx=12, pady=2)
            tk.Label(item, text=icon, bg=BG, fg="white", font=(FONT, 15), width=2).pack(side="left")
            tk.Label(item, text=("Dashboard" if name == "Home" else name), bg=BG, fg=FG, font=(FONT, 12),
                     anchor="w").pack(side="left", padx=(10, 0), fill="x", expand=True)
            for w in (item, *item.winfo_children()):
                w.bind("<Button-1>", lambda e, n=name: self.goto(n))
                w.bind("<Enter>", lambda e, it=item, n=name: n != self.page and paint(it, C.NAV_HOVER))
                w.bind("<Leave>", lambda e, it=item, n=name: paint(it, C.NAV_ACTIVE if n == self.page else BG))
            item.paint = paint
            self.nav_buttons[name] = item
        tk.Frame(side, bg="#2C5E66", height=1).pack(fill="x", padx=22, pady=(14, 8))
        for text, kind in (("🌐  Analytics (Streamlit)", "streamlit"), ("📝  Prescriptions (Gradio)", "gradio")):
            tk.Button(side, text=text, anchor="w", bg="#0A4A52", fg="white", activebackground=C.NAV_ACTIVE,
                      activeforeground="white", relief="flat", font=(FONT, 10), padx=12, pady=7, cursor="hand2",
                      command=lambda k=kind: self.launcher.open(
                          k, lambda m: self.after(0, lambda: messagebox.showerror("DrukCare", m)))).pack(fill="x", padx=16, pady=3)
        tk.Button(side, text="⎋   Log out", anchor="w", bg=BG, fg=FG, activebackground=C.NAV_HOVER, activeforeground="white",
                  relief="flat", font=(FONT, 12), padx=14, pady=8, cursor="hand2", command=self.logout).pack(fill="x", padx=12, pady=(6, 0))
        # dragon decoration at the bottom of the sidebar (assets/sidebar_dragon.png)
        if I.find_image(C.SIDEBAR_DRAGON):
            self._side_dragon = load_photo(C.SIDEBAR_DRAGON, (240, 214), contain=True)
            tk.Label(side, image=self._side_dragon, bg=BG, bd=0).pack(side="bottom")
        self.content = ScrollFrame(self)
        self.content.pack(side="left", fill="both", expand=True)
        self.goto(self.page)

    def logout(self):
        self.user = None
        self.show_login()

    def goto(self, page):
        self.page = page
        for name, item in self.nav_buttons.items():
            item.paint(item, C.NAV_ACTIVE if name == page else C.NAVY)
            item.winfo_children()[1].config(font=(FONT, 12, "bold" if name == page else ""))
        self.refresh_page()

    def refresh_page(self):
        if not self.user or not hasattr(self, "content") or not self.content.winfo_exists():
            return
        y = self.content.canvas.yview()[0]
        for w in self.content.inner.winfo_children():
            w.destroy()
        pad = tk.Frame(self.content.inner, bg=C.IVORY, padx=24, pady=16)
        pad.pack(fill="both", expand=True)
        pad.columnconfigure(0, weight=1)
        builder = {"Home": self.page_home, "Medication": self.page_medication, "Exercise": self.page_exercise,
                   "Prescriptions": self.page_prescriptions, "Analytics": self.page_analytics,
                   "My Profile": self.page_profile}[self.page]
        if self.user["Role"] != "Patient" and self.page == "Home":
            builder = self.page_other_role
        try:
            builder(pad)
        except storage.StorageError as err:
            tk.Label(pad, text=str(err), bg=C.IVORY, fg="#B02A2A", font=(FONT, 12)).pack()
        self.update_idletasks()
        self.content.canvas.yview_moveto(y)

    def banner(self, parent, title, subtitle, row=0):
        b = Banner(parent, self, self.page, title, subtitle)
        b.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        return b

    def footer(self, parent, row):
        """Small empty space at the bottom of every page (the disclaimer line was removed)."""
        tk.Frame(parent, bg=C.IVORY, height=12).grid(row=row, column=0)

    def mark(self, med_id, day, status):
        snooze = int(S.get_profile(self.uid)["Snooze_Min"] or 10)
        self.safe(S.set_dose_status, self.uid, med_id, status, day, snooze)
        self.refresh_page()

    # ---------------------------------------------------------------- pages
    def page_other_role(self, p):
        """Caregivers and providers: the desktop app is for patients, so point them to their web tool."""
        role = self.user["Role"]
        self.banner(p, f"Kuzuzangpo, {self.user['Full_Name']}!", "Welcome to DrukCare.")
        c = card(p)
        c.grid(row=1, column=0, sticky="ew")
        if role == "Caregiver":
            title = "Follow a patient's progress in the Streamlit dashboard"
            text = ("Open the dashboard, log in with this same account, go to My Patients and press View patient: "
                    "enter the patient's username and CID. You will then see their taken and missed doses, exercise "
                    "and charts (read-only), and you can send them a care plan (medicines and daily exercise).")
            kind, btn = "streamlit", "🌐  Open the Streamlit dashboard"
        else:
            title = "Write prescriptions in the Gradio portal"
            text = ("First link your patient in the Streamlit dashboard (My Patients → View patient: username + CID). "
                    "Then write prescriptions in the Gradio portal, or send a care plan from My Patients. "
                    "The patient gets a message at once, and a care plan goes straight into their reminders.")
            kind, btn = "gradio", "📝  Open the Gradio prescription portal"
        label(c, title, 13, True, family=SERIF).pack(anchor="w")
        label(c, text, 11, color=C.MUTED, wraplength=760, justify="left").pack(anchor="w", pady=6)
        button(c, btn, lambda: self.open_web(kind)).pack(anchor="w", pady=(4, 0))
        self.footer(p, 2)

    def page_home(self, p):
        uid = self.uid
        self.banner(p, f"Kuzuzangpo, {self.user['Full_Name']}!", "Small steps today for a healthier tomorrow.")
        nxt, ex, wk = S.next_dose(uid), S.exercise_today(uid), S.week_adherence(uid)
        items = [i for i in S.list_prescription_items(patient_id=uid) if i["Status"] == "Active"]
        todays = S.doses_for_date(uid)
        taken_today = sum(1 for d in todays if d["Status"] == "Taken")
        row = tk.Frame(p, bg=C.IVORY)
        row.grid(row=1, column=0, sticky="ew")
        for i in range(4):
            row.columnconfigure(i, weight=1, uniform="c")
        c1 = card(row)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        label(c1, "💊 Next medication", 10, True, C.MUTED).pack(anchor="w")
        if nxt:
            label(c1, nxt["Med_Name"], 16, True).pack(anchor="w", pady=(6, 0))
            label(c1, f"{nxt['Dosage']} · {fmt12(nxt['Dosage_Time'])}", 10, color=C.MUTED).pack(anchor="w")
            priority_chip(c1, nxt["Priority_Level"]).pack(anchor="w", pady=4)
            label(c1, f"{nxt['Status']} · {nxt['When']}", 10, True, C.STATUS_COLORS.get(nxt["Status"], C.MUTED)).pack(anchor="w")
            btns = tk.Frame(c1, bg=C.CARD)
            btns.pack(anchor="w", pady=(8, 0))
            button(btns, "✓ Mark taken", lambda: self.mark(nxt["Med_ID"], nxt["Date"], "Taken")).pack(side="left")
            button(btns, "✗ Mark missed", lambda: self.mark(nxt["Med_ID"], nxt["Date"], "Missed"), "danger").pack(side="left", padx=6)
        else:
            label(c1, "All done 🎉", 16, True).pack(anchor="w", pady=6)
        label(c1, f"Doses taken today: {taken_today}/{len(todays)}", 10, True, C.EMERALD_DARK).pack(anchor="w", pady=(8, 0))
        c2 = card(row)
        c2.grid(row=0, column=1, sticky="nsew", padx=4)
        label(c2, f"🚶 Today's exercise · {ex['steps_pct']}% of goal", 10, True, C.MUTED).pack(anchor="w")
        label(c2, f"{ex['steps']:,} / {ex['steps_goal']:,} steps", 13, True).pack(anchor="w", pady=(6, 4))
        ttk.Progressbar(c2, style="Green.Horizontal.TProgressbar", value=ex["steps_pct"]).pack(fill="x")
        label(c2, f"⏱ {ex['minutes']} min    📍 {ex['distance_km']:g} km", 10, color=C.MUTED).pack(anchor="w", pady=6)
        button(c2, "Log activity →", lambda: self.goto("Exercise"), "ghost").pack(anchor="w")
        c3 = card(row)
        c3.grid(row=0, column=2, sticky="nsew", padx=4)
        label(c3, "📈 Medication adherence", 10, True, C.MUTED).pack(anchor="w")
        draw_ring(c3, wk["pct"], 84, 10).pack(side="left", pady=6)
        label(c3, f"This week\n{wk['taken']}/{wk['total']}\ndoses", 10, True, justify="left").pack(side="left", padx=8)
        c4 = card(row)
        c4.grid(row=0, column=3, sticky="nsew", padx=(8, 0))
        label(c4, "📄 Prescriptions", 10, True, C.MUTED).pack(anchor="w")
        label(c4, str(len(items)), 26, True).pack(anchor="w", pady=(6, 0))
        label(c4, "Active prescriptions", 10, color=C.MUTED).pack(anchor="w")
        button(c4, "View details →", lambda: self.goto("Prescriptions"), "ghost").pack(anchor="w", pady=(8, 0))
        # ---- five picture tiles (like the design sample)
        tiles = tk.Frame(p, bg=C.IVORY)
        tiles.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        spec = [("Medication", "Manage your medications\nand set reminders.", "Go to Medication"),
                ("Exercise", "Follow your exercise plan\nfor better health.", "Go to Exercises"),
                ("Prescriptions", "View and manage your\nprescriptions.", "Go to Prescriptions"),
                ("Analytics", "Track your health progress\nwith insights.", "Go to Analytics"),
                ("My Profile", "Update your profile and\npersonal details.", "Go to Profile")]
        self._tile_photos = []
        for i, (page, desc, btn) in enumerate(spec):
            tiles.columnconfigure(i, weight=1, uniform="t")
            t = tk.Frame(tiles, bg=C.CARD, highlightbackground=C.BORDER, highlightthickness=1)
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            holder = tk.Frame(t, bg=C.TINT_MINT, height=150)
            holder.pack(fill="x")
            holder.pack_propagate(False)
            pic = tk.Label(holder, bg=C.TINT_MINT, bd=0)
            pic.pack(fill="both", expand=True)
            if page == "My Profile":
                ph = load_photo(I.profile_photo_path(self.user["User_ID"]), (124, 124), circle=True,
                                initials="".join(w[0] for w in self.user["Full_Name"].split()[:2]).upper())
                pic.config(image=ph)
                self._tile_photos.append(ph)
                holder.bind("<Configure>", lambda e, hd=holder: hd.config(height=max(150, int(e.width * 330 / 640))))
            else:
                src_t = I.load_image(C.NAV_IMAGES[page], None, label="")

                def fit(e, hd=holder, lab=pic, im=src_t):     # whole picture, full colour, as wide as the tile
                    w = max(60, e.width)
                    if getattr(lab, "_w", None) == w:
                        return
                    h = max(150, int(w * im.height / im.width))
                    lab._w = w
                    lab._ph = ImageTk.PhotoImage(ImageOps.fit(im, (w, h), Image.LANCZOS) if h > w * im.height / im.width
                                                 else im.resize((w, h), Image.LANCZOS))
                    lab.config(image=lab._ph)
                    hd.config(height=h)

                holder.bind("<Configure>", fit)
            label(t, "Exercises" if page == "Exercise" else page, 14, True, family=SERIF).pack(pady=(8, 2))
            label(t, desc, 9, color=C.MUTED, justify="center").pack()
            tk.Button(t, text=btn + "  →", command=lambda n=page: self.goto(n), bg=C.BUTTON_DARK, fg="white",
                      activebackground=C.EMERALD, activeforeground="white", relief="flat", bd=0, cursor="hand2",
                      font=(FONT, 9, "bold"), padx=12, pady=6).pack(pady=(8, 12))
        # ---- today's schedule | quote card
        bottom = tk.Frame(p, bg=C.IVORY)
        bottom.grid(row=3, column=0, sticky="ew", pady=14)
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=2)
        sched = card(bottom)
        sched.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        label(sched, "🔔  Today's schedule", 12, True, family=SERIF).pack(anchor="w", pady=(0, 6))
        doses = S.doses_for_date(uid)
        if not doses:
            label(sched, "No medicines scheduled today.", 11, color=C.MUTED).pack(pady=10)
        for d in doses:
            r = tk.Frame(sched, bg=C.CARD)
            r.pack(fill="x", pady=3)
            label(r, d["Med_Name"], 11, True).pack(side="left")
            label(r, f"  {d['Dosage']}", 10, color=C.MUTED).pack(side="left")
            label(r, d["Status"], 10, True, C.STATUS_COLORS.get(d["Status"], C.MUTED)).pack(side="right")
            label(r, f"{fmt12(d['Dosage_Time'])}   ", 10, color=C.MUTED).pack(side="right")
            priority_chip(r, d["Priority_Level"]).pack(side="right", padx=8)
        quote, who = C.WELLNESS_MESSAGES[date.today().toordinal() % len(C.WELLNESS_MESSAGES)]
        strip = tk.Canvas(bottom, height=200, highlightthickness=0, bg=C.NAVY)
        strip.grid(row=0, column=1, sticky="nsew")

        def draw(e):
            w, h = e.width, max(200, e.height)
            if w < 60:
                return
            img = I.banner_background((w, h), (0.5, 0.25)).convert("RGBA")
            img = Image.alpha_composite(img, Image.new("RGBA", (w, h), (0, 70, 76, 120)))   # teal tint so text reads
            strip.photo = ImageTk.PhotoImage(img)
            strip.delete("all")
            strip.create_image(0, 0, anchor="nw", image=strip.photo)
            strip.create_text(w / 2, h / 2 - 12, text=f"“{quote}”", font=(SERIF, 16, "italic"), fill="white",
                              width=w - 50, justify="center")
            strip.create_text(w / 2, h - 34, text=f"— {who}", font=(FONT, 10), fill="#DDF4F0")

        strip.bind("<Configure>", draw)
        self.footer(p, 4)

    # ----------------------------------------------------------- medication
    def page_medication(self, p):
        uid = self.uid
        self.banner(p, "Medication", "Your daily dose. Your better tomorrow.")
        body = tk.Frame(p, bg=C.IVORY)
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)
        left = tk.Frame(body, bg=C.IVORY)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        top = tk.Frame(left, bg=C.IVORY)
        top.pack(fill="x", pady=(0, 8))
        button(top, "＋ Add medication", lambda: MedDialog(self, on_saved=self.refresh_page)).pack(side="right")
        nb = ttk.Notebook(left)
        nb.pack(fill="both", expand=True)
        tabs = {}
        for name in ("Today", "Upcoming", "History", "All medicines"):
            f = tk.Frame(nb, bg=C.CARD, padx=12, pady=12)
            nb.add(f, text=name)
            tabs[name] = f
        cols = [("med", "Medicine", 200, "w"), ("dose", "Dosage", 110, "w"), ("time", "Time", 85, "center"),
                ("prio", "Priority", 85, "center"), ("status", "Status", 110, "center")]
        # --- today
        fr, tree = make_tree(tabs["Today"], cols, 9)
        fr.pack(fill="both", expand=True)
        for d in S.doses_for_date(uid):
            tree.insert("", "end", iid=f"{d['Med_ID']}|{d['Date'].isoformat()}",
                        values=(d["Med_Name"], d["Dosage"], fmt12(d["Dosage_Time"]), d["Priority_Level"], d["Status"]),
                        tags=("done",) if d["Status"] in ("Taken", "Missed") else (d["Priority_Level"],))

        def selected():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("DrukCare", "Please click a medicine in the list first.")
                return None
            med_id, day = sel[0].split("|")
            return med_id, date.fromisoformat(day)

        def act(status):
            s = selected()
            if s:
                self.mark(s[0], s[1], status)

        def undo():
            s = selected()
            if s:
                S.clear_dose_status(uid, s[0], s[1])
                self.refresh_page()

        def edit():
            s = selected()
            med = next((m for m in S.list_medications(uid) if s and m["Med_ID"] == s[0]), None)
            if med:
                MedDialog(self, med, self.refresh_page)

        def delete():
            s = selected()
            med = next((m for m in S.list_medications(uid) if s and m["Med_ID"] == s[0]), None)
            if med and messagebox.askyesno("Delete medication", f"Delete {med['Med_Name']} ({fmt12(med['Dosage_Time'])}) and its history?"):
                self.safe(S.delete_medication, med["Med_ID"], uid)
                self.refresh_page()

        bar = tk.Frame(tabs["Today"], bg=C.CARD)
        bar.pack(fill="x", pady=(10, 0))
        button(bar, "✓ Mark taken", lambda: act("Taken")).pack(side="left", padx=(0, 6))
        button(bar, "✗ Mark missed", lambda: act("Missed"), "ghost").pack(side="left", padx=6)
        button(bar, "⏰ Snooze", lambda: act("Snoozed"), "ghost").pack(side="left", padx=6)
        button(bar, "↩ Undo", undo, "ghost").pack(side="left", padx=6)
        button(bar, "✏ Edit", edit, "ghost").pack(side="left", padx=6)
        button(bar, "🗑 Delete", delete, "danger").pack(side="left", padx=6)
        # --- upcoming
        fr2, t2 = make_tree(tabs["Upcoming"], [("date", "Date", 110, "w")] + cols, 10)
        fr2.pack(fill="both", expand=True)
        for i, d in enumerate(S.upcoming_doses(uid, 3)):
            t2.insert("", "end", iid=str(i), values=(d["Date"].strftime("%a %d %b"), d["Med_Name"], d["Dosage"], fmt12(d["Dosage_Time"]),
                                                      d["Priority_Level"], d["Status"]), tags=(d["Priority_Level"],))
        # --- history
        now = datetime.now()
        past = [d for d in S.doses_between(uid, now.date() - timedelta(days=29), now.date(), now)
                if d["Scheduled"] <= now or d["Status"] == "Taken"]
        flt = ttk.Combobox(tabs["History"], values=["All", "Taken", "Missed", "Overdue"], state="readonly", width=12)
        flt.set("All")
        flt.pack(anchor="w", pady=(0, 8))
        fr3, t3 = make_tree(tabs["History"], [("date", "Date", 110, "w")] + cols, 10)
        fr3.pack(fill="both", expand=True)

        def fill_history(_=None):
            t3.delete(*t3.get_children())
            for i, d in enumerate(reversed(past)):
                status = "Missed" if d["Status"] == "Overdue" and d["Date"] < now.date() else d["Status"]
                if flt.get() in ("All", status):
                    t3.insert("", "end", iid=str(i), values=(d["Date"].strftime("%d %b %Y"), d["Med_Name"], d["Dosage"],
                                                              fmt12(d["Dosage_Time"]), d["Priority_Level"], status),
                              tags=("done",) if status == "Taken" else (d["Priority_Level"],))

        flt.bind("<<ComboboxSelected>>", fill_history)
        fill_history()
        # --- all medicines
        fr4, t4 = make_tree(tabs["All medicines"], cols + [("freq", "Frequency", 110, "center")], 9)
        fr4.pack(fill="both", expand=True)
        for m in S.list_medications(uid):
            status = "Active" if storage.to_bool(m["Is_Active"]) else "Paused"
            t4.insert("", "end", iid=m["Med_ID"], values=(m["Med_Name"], m["Dosage"], fmt12(m["Dosage_Time"]), m["Priority_Level"], status, m["Frequency"]),
                      tags=(m["Priority_Level"],))

        def sel_med():
            sel = t4.selection()
            if not sel:
                messagebox.showinfo("DrukCare", "Please click a medicine in the list first.")
                return None
            return next((m for m in S.list_medications(uid) if m["Med_ID"] == sel[0]), None)

        def edit4():
            m = sel_med()
            if m:
                MedDialog(self, m, self.refresh_page)

        def del4():
            m = sel_med()
            if m and messagebox.askyesno("Delete medication", f"Delete {m['Med_Name']} and its history?"):
                self.safe(S.delete_medication, m["Med_ID"], uid)
                self.refresh_page()

        bar4 = tk.Frame(tabs["All medicines"], bg=C.CARD)
        bar4.pack(fill="x", pady=(10, 0))
        button(bar4, "✏ Edit", edit4, "ghost").pack(side="left", padx=(0, 6))
        button(bar4, "🗑 Delete", del4, "danger").pack(side="left")
        nb.select(self.state_memory.get("med_tab", 0))
        nb.bind("<<NotebookTabChanged>>", lambda e: self.state_memory.__setitem__("med_tab", nb.index("current")))
        # --- adherence card
        wk = S.week_adherence(uid)
        right = card(body)
        right.grid(row=0, column=1, sticky="n")
        label(right, "You're doing great! 🌿", 13, True).pack(anchor="w")
        label(right, f"You've taken {wk['taken']} out of {wk['total']}\ndoses this week.", 10, color=C.MUTED, justify="left").pack(anchor="w", pady=4)
        draw_ring(right, wk["pct"], 140, 15).pack(pady=10)
        label(right, "Always follow your doctor's advice.", 9, color="#7A5B00", bg="#FFF4D6", justify="left", padx=8, pady=6).pack(fill="x")
        self.footer(p, 2)

    # ------------------------------------------------------------- exercise
    def page_exercise(self, p):
        uid = self.uid
        self.banner(p, "Exercise", "Move more. Feel better. Live longer.")
        ex = S.exercise_today(uid)
        row = tk.Frame(p, bg=C.IVORY)
        row.grid(row=1, column=0, sticky="ew")
        for i in range(3):
            row.columnconfigure(i, weight=1, uniform="s")
        for i, (icon, title, value, goal, pct) in enumerate((
                ("👣", "Steps today", f"{ex['steps']:,} steps", f"Goal: {ex['steps_goal']:,}", ex["steps_pct"]),
                ("⏱", "Active minutes", f"{ex['minutes']} min", f"Goal: {ex['minutes_goal']} min", ex["minutes_pct"]),
                ("📍", "Distance", f"{ex['distance_km']:g} km", f"Goal: {ex['km_goal']:g} km", ex["km_pct"]))):
            c = card(row)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 2 else 6))
            label(c, f"{icon} {title}", 10, True, C.MUTED).pack(anchor="w")
            label(c, value, 20, True).pack(anchor="w", pady=(4, 6))
            ttk.Progressbar(c, style="Green.Horizontal.TProgressbar", value=pct).pack(fill="x")
            label(c, f"{goal} · {pct}%", 10, color=C.MUTED).pack(anchor="w", pady=(4, 0))
        mid = tk.Frame(p, bg=C.IVORY)
        mid.grid(row=2, column=0, sticky="ew", pady=14)
        mid.columnconfigure(0, weight=2)
        mid.columnconfigure(1, weight=1)
        chart = card(mid)
        chart.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        label(chart, "Your weekly progress (steps)", 10, True, C.MUTED).pack(anchor="w")
        series = S.exercise_series(uid, date.today() - timedelta(days=6), date.today())
        fig = Figure(figsize=(6, 2.8), dpi=100, facecolor=C.CARD)
        ax = fig.add_subplot(111)
        ax.bar([s["date"].strftime("%a") for s in series], [s["steps"] for s in series], color=C.EMERALD, width=0.55)
        ax.axhline(ex["steps_goal"], color="#D4A017", linestyle="--", linewidth=1.2)
        ax.set_ylabel("steps")
        style_fig(fig)
        fig.tight_layout()
        FigureCanvasTkAgg(fig, chart).get_tk_widget().pack(fill="both", expand=True)
        goals = card(mid)
        goals.grid(row=0, column=1, sticky="nsew")
        label(goals, "Today's goals", 10, True, C.MUTED).pack(anchor="w", pady=(0, 6))
        for g in S.daily_goal_checklist(uid):
            r = tk.Frame(goals, bg=C.CARD)
            r.pack(fill="x", pady=5)
            label(r, g["label"], 11).pack(side="left")
            label(r, "✓ Done" if g["done"] else f"{g['pct']}%", 10, True, C.EMERALD if g["done"] else C.MUTED).pack(side="right")
        bottom = tk.Frame(p, bg=C.IVORY)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure((0, 1), weight=1, uniform="b")
        form = card(bottom)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        label(form, "Record an activity", 12, True).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        kind = ttk.Combobox(form, values=S.ACTIVITY_TYPES, state="readonly", font=(FONT, 11))
        kind.set("Walking")
        minutes, km, steps = entry(form, "30", 10), entry(form, "0", 10), entry(form, "0", 10)
        for r, (text, w) in enumerate((("Activity type", kind), ("Duration (min)", minutes), ("Distance (km)", km), ("Steps (0 = estimate)", steps)), 1):
            label(form, text, 10, color=C.MUTED).grid(row=r, column=0, sticky="w", pady=4)
            w.grid(row=r, column=1, sticky="ew", padx=(10, 0))
        form.columnconfigure(1, weight=1)

        def save_activity():
            if self.safe(S.log_activity, uid, kind.get(), minutes.get(), km.get(), steps.get() or None) is not None:
                self.notify(f"{kind.get()} logged ({minutes.get()} min)")
                self.refresh_page()

        button(form, "Save activity", save_activity).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        right = tk.Frame(bottom, bg=C.IVORY)
        right.grid(row=0, column=1, sticky="nsew")
        gcard = card(right)
        gcard.pack(fill="x")
        label(gcard, "Daily goals", 12, True).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        g = S.get_goals(uid)
        gs = entry(gcard, g["Steps"]["Exercise_Target"], 10)
        gm = entry(gcard, g["Minutes"]["Exercise_Target"], 10)
        gk = entry(gcard, f"{int(float(g['Distance']['Exercise_Target'])) / 1000:g}", 10)
        for r, (text, w) in enumerate((("Steps", gs), ("Active minutes", gm), ("Distance (km)", gk)), 1):
            label(gcard, text, 10, color=C.MUTED).grid(row=r, column=0, sticky="w", pady=3)
            w.grid(row=r, column=1, sticky="ew", padx=(10, 0))
        gcard.columnconfigure(1, weight=1)

        def save_goals():
            self.safe(S.set_goals, uid, gs.get(), gm.get(), gk.get())
            self.refresh_page()

        button(gcard, "Update goals", save_goals, "ghost").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        acts = card(right)
        acts.pack(fill="x", pady=(10, 0))
        label(acts, "Today's activities", 12, True).pack(anchor="w")
        todays = S.activities_for_date(uid)
        if not todays:
            label(acts, "No activity recorded yet today.", 10, color=C.MUTED).pack(pady=8)
        for a in todays:
            r = tk.Frame(acts, bg=C.CARD)
            r.pack(fill="x", pady=3)
            label(r, f"{a['Type']} · {a['minutes']} min · {a['distance_km']:g} km · {a['steps']:,} steps", 10).pack(side="left")
            tk.Button(r, text="🗑", relief="flat", bg=C.CARD, fg="#B02A2A", cursor="hand2",
                      command=lambda aid=a["Activity_ID"], t=a["Type"]: (
                          messagebox.askyesno("Delete activity", f"Delete this {t} entry?") and
                          (S.delete_activity(uid, aid), self.refresh_page()))).pack(side="right")
        self.footer(p, 4)

    # -------------------------------------------------------- prescriptions
    def page_prescriptions(self, p):
        uid = self.uid
        self.banner(p, "Prescriptions", "Your doctor's plan, in your hands.")
        items = S.list_prescription_items(patient_id=uid)
        top = tk.Frame(p, bg=C.IVORY)
        top.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        button(top, "＋ Add prescription", lambda: RxDialog(self, self.refresh_page)).pack(side="right")
        button(top, "📝 Open the Gradio prescription portal", lambda: self.open_web("gradio"), "ghost").pack(side="right", padx=8)
        nb = ttk.Notebook(p)
        nb.grid(row=2, column=0, sticky="ew")
        cols = [("med", "Medicine", 190, "w"), ("dose", "Dosage", 130, "w"), ("freq", "Frequency", 110, "center"),
                ("days", "Days", 60, "center"), ("date", "Prescribed on", 110, "center"), ("status", "Status", 80, "center"),
                ("by", "Prescribed by", 140, "w")]
        trees = {}
        for name, subset in (("Active", [i for i in items if i["Status"] == "Active"]),
                             ("Past", [i for i in items if i["Status"] == "Past"]), ("All", items)):
            f = tk.Frame(nb, bg=C.CARD, padx=12, pady=12)
            nb.add(f, text=name)
            if not subset:
                label(f, "📄\nNo prescriptions here yet\nWhen your doctor adds a prescription it will appear here.", 11,
                      color=C.MUTED, justify="center", pady=40).pack(fill="x")
                continue
            fr, tree = make_tree(f, cols, 8)
            fr.pack(fill="both", expand=True)
            trees[name] = (tree, {i["Item_ID"]: i for i in subset})
            for i in subset:
                tree.insert("", "end", iid=i["Item_ID"], values=(i["Med_Name"], i["Dosage"], i["Frequency"], i["Duration_Days"],
                                                                 i["Rx_Date"], i["Status"], i["Provider_Name"]))

        def chosen():
            name = nb.tab(nb.select(), "text")
            if name not in trees:
                messagebox.showinfo("DrukCare", "There is nothing to choose in this tab.")
                return None
            tree, lookup = trees[name]
            if not tree.selection():
                messagebox.showinfo("DrukCare", "Please click a prescription in the list first.")
                return None
            return lookup[tree.selection()[0]]

        def view():
            it = chosen()
            if it:
                folder = C.DATA_DIR / "summaries"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"prescription_{it['Rx_ID']}.html"
                path.write_text(self.safe(S.prescription_summary_html, it["Rx_ID"]) or "", encoding="utf-8")
                webbrowser.open(path.as_uri())

        def edit():
            it = chosen()
            if it:
                if it["Provider_ID"] != self.user["User_ID"]:
                    return messagebox.showinfo("DrukCare", "Only the person who created a prescription can edit it.")
                RxDialog(self, self.refresh_page, item=it)

        def delete():
            it = chosen()
            if it and messagebox.askyesno("Delete", f"Delete {it['Med_Name']} from this prescription?"):
                if self.safe(S.delete_prescription_item, it["Item_ID"], self.user["User_ID"]) is None:
                    self.refresh_page()

        def schedule():
            it = chosen()
            if it:
                ScheduleDialog(self, it, self.refresh_page)

        bar = tk.Frame(p, bg=C.IVORY)
        bar.grid(row=3, column=0, sticky="w", pady=10)
        button(bar, "👁 View / print summary", view, "ghost").pack(side="left", padx=(0, 6))
        button(bar, "✏ Edit", edit, "ghost").pack(side="left", padx=6)
        button(bar, "🗑 Delete", delete, "danger").pack(side="left", padx=6)
        button(bar, "📅 Add to my schedule", schedule).pack(side="left", padx=6)
        tk.Label(p, text="Summaries open in your browser — press Ctrl+P there to print.", bg=C.IVORY, fg=C.MUTED, font=(FONT, 9)).grid(row=4, column=0, sticky="w")
        self.footer(p, 5)

    # ------------------------------------------------------------ analytics
    def page_analytics(self, p):
        uid = self.uid
        self.banner(p, "Analytics", "Track your progress. See the bigger picture.")
        days = self.state_memory.get("an_days", 7)
        bar = tk.Frame(p, bg=C.IVORY)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        button(bar, "🌐 Open the Streamlit dashboard", lambda: self.open_web("streamlit"), "ghost").pack(side="right")
        for label_text, n in (("7 days", 7), ("30 days", 30), ("3 months", 90)):
            b = button(bar, label_text, lambda n=n: (self.state_memory.__setitem__("an_days", n), self.refresh_page()),
                       "primary" if n == days else "ghost")
            b.pack(side="left", padx=(0, 6))
        data = S.analytics_data(uid, days)
        a = data["adherence"]
        row = tk.Frame(p, bg=C.IVORY)
        row.grid(row=2, column=0, sticky="ew")
        row.columnconfigure((0, 1, 2, 3), weight=1, uniform="m")
        for i, (title, big, sub) in enumerate((          # the four metric tiles from the proposal presentation
                ("Medication adherence", f"{a['pct']}%", f"{a['taken']}/{a['total']} doses taken"),
                ("Days with every dose", f"{data['full_dose_days']} / {data['dose_days']}", "all doses taken that day"),
                ("Average exercise", f"{data['avg_exercise_pct']}%", f"of the daily goal ({data['steps_goal']:,} steps)"),
                ("Days goal reached", f"{data['goal_days']} / {data['days']}", "steps goal met"))):
            c = card(row)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 0 if i == 3 else 5))
            label(c, title, 10, True, C.MUTED).pack(anchor="w")
            label(c, big, 20, True).pack(anchor="w", pady=(4, 0))
            label(c, sub, 9, color=C.MUTED).pack(anchor="w")
        chart = card(p)
        chart.grid(row=3, column=0, sticky="ew", pady=14)
        fig = Figure(figsize=(10, 6.4), dpi=100, facecolor=C.CARD)
        short = lambda d: d.strftime("%d %b")
        # 1. taken vs missed
        ax1 = fig.add_subplot(221)
        ad = data["adherence_days"]
        if days > 31 and ad:   # weekly buckets for 3 months
            buckets = {}
            for e in ad:
                key = e["date"] - timedelta(days=e["date"].weekday())
                b = buckets.setdefault(key, [0, 0])
                b[0] += e["taken"]
                b[1] += e["missed"]
            xs = [short(k) for k in sorted(buckets)]
            taken = [buckets[k][0] for k in sorted(buckets)]
            missed = [buckets[k][1] for k in sorted(buckets)]
        else:
            xs, taken, missed = [short(e["date"]) for e in ad], [e["taken"] for e in ad], [e["missed"] for e in ad]
        ax1.bar(xs, taken, color=C.EMERALD, label="Taken")
        ax1.bar(xs, missed, bottom=taken, color="#E58A8A", label="Missed")
        ax1.set_title("Doses taken vs missed", fontsize=10, loc="left")
        ax1.legend(fontsize=8, frameon=False)
        # 2. steps
        ex = data["exercise"]
        ax2 = fig.add_subplot(222)
        ax2.bar([short(e["date"]) for e in ex], [e["steps"] for e in ex], color=C.EMERALD)
        ax2.axhline(data["steps_goal"], color="#D4A017", linestyle="--", linewidth=1)
        ax2.set_title("Steps per day (dashed = goal)", fontsize=10, loc="left")
        # 3. minutes
        ax3 = fig.add_subplot(223)
        ax3.plot([short(e["date"]) for e in ex], [e["minutes"] for e in ex], color=C.EMERALD, marker="o", markersize=3)
        ax3.fill_between([short(e["date"]) for e in ex], [e["minutes"] for e in ex], color=C.EMERALD, alpha=0.15)
        ax3.set_title("Active minutes", fontsize=10, loc="left")
        # 4. weight
        ax4 = fig.add_subplot(224)
        if data["weight"]:
            ax4.plot([short(w["date"]) for w in data["weight"]], [w["weight"] for w in data["weight"]], color="#3D7EA6", marker="o")
        else:
            ax4.text(0.5, 0.5, "No weight entries in this range", ha="center", transform=ax4.transAxes, color=C.MUTED)
        ax4.set_title("Weight (kg)", fontsize=10, loc="left")
        for ax in (ax1, ax2, ax3, ax4):
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            n = len(ax.get_xticks())
            ax.tick_params(labelsize=7)
            if n > 8:
                step = max(1, n // 7)
                for i, lbl in enumerate(ax.get_xticklabels()):
                    lbl.set_visible(i % step == 0)
            for lbl in ax.get_xticklabels():
                lbl.set_rotation(35)
                lbl.set_ha("right")
        style_fig(fig)
        fig.tight_layout()
        FigureCanvasTkAgg(fig, chart).get_tk_widget().pack(fill="both", expand=True)
        self.footer(p, 4)

    # -------------------------------------------------------------- profile
    def page_profile(self, p):
        me = S.get_user(self.user["User_ID"])
        prof = S.get_profile(me["User_ID"])
        self.banner(p, "My Profile", "Your information. Your health journey.")
        body = tk.Frame(p, bg=C.IVORY)
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)
        left = card(body)
        left.grid(row=0, column=0, sticky="n", padx=(0, 14))
        self._avatar = load_photo(I.profile_photo_path(me["User_ID"]), (130, 130), circle=True,
                                  initials="".join(w[0] for w in me["Full_Name"].replace("Dr.", "").split()[:2]).upper())
        tk.Label(left, image=self._avatar, bg=C.CARD).pack(pady=(0, 8))
        label(left, me["Full_Name"], 14, True).pack()
        label(left, prof["Email"] or f"@{me['Username']}", 10, color=C.MUTED).pack(pady=(0, 8))

        def change_photo():
            path = filedialog.askopenfilename(title="Choose a profile photo", filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("All files", "*.*")])
            if path:
                try:
                    I.save_profile_photo(me["User_ID"], path)
                except ValueError as err:
                    return messagebox.showerror("DrukCare", str(err))
                self.refresh_page()

        button(left, "📷 Change photo", change_photo, "ghost").pack(fill="x", pady=3)
        button(left, "Remove photo", lambda: (I.remove_profile_photo(me["User_ID"]), self.refresh_page()), "ghost").pack(fill="x", pady=3)
        right = card(body)
        right.grid(row=0, column=1, sticky="nsew")
        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        def tab(name):
            f = tk.Frame(nb, bg=C.CARD, padx=16, pady=14)
            f.columnconfigure(1, weight=1)
            nb.add(f, text=name)
            return f

        def rows(f, spec):
            widgets = []
            for r, (text, w) in enumerate(spec):
                label(f, text, 10, True, C.MUTED).grid(row=r, column=0, sticky="w", pady=6)
                w.grid(row=r, column=1, sticky="ew", padx=(14, 0))
                widgets.append(w)
            return widgets

        def combo(parent, values, value):
            c = ttk.Combobox(parent, values=values, state="readonly", font=(FONT, 11))
            c.set(value)
            return c

        def saver(f, row, func, ok="Saved."):
            def go():
                try:
                    func()
                except (ValidationError, storage.StorageError) as err:
                    return messagebox.showerror("Please check the form", str(err))
                messagebox.showinfo("DrukCare", ok)
                self.user = S.public_user(S.get_user(me["User_ID"]))
                self.refresh_page()
            button(f, "Save changes", go).grid(row=row, column=0, columnspan=2, sticky="w", pady=(14, 0))

        f1 = tab("Personal Details")
        name, cid, dob, phone, email, gender = rows(f1, [
            ("Full name", entry(f1, me["Full_Name"])), ("CID (11 digits)", entry(f1, me["CID"])),
            ("Date of birth (YYYY-MM-DD)", entry(f1, me["Date_of_Birth"])),
            ("Phone", entry(f1, me["Phone"])), ("Email", entry(f1, prof["Email"])),
            ("Gender", combo(f1, S.GENDERS, prof["Gender"]))])
        saver(f1, 6, lambda: ((S.update_cid(me["User_ID"], cid.get()) if cid.get().strip() != me["CID"] else None),
                              S.update_user(me["User_ID"], name.get(), dob.get(), phone.get()),
                              S.save_profile(me["User_ID"], Email=email.get(), Gender=gender.get())))
        f2 = tab("Health Information")
        height, weight, blood, allergies, cond = rows(f2, [
            ("Height (cm)", entry(f2, prof["Height_Cm"])), ("Weight (kg)", entry(f2, prof["Weight_Kg"])),
            ("Blood type", combo(f2, S.BLOOD_TYPES, prof["Blood_Type"])), ("Allergies", entry(f2, prof["Allergies"])),
            ("Health conditions", entry(f2, prof["Conditions"]))])
        saver(f2, 5, lambda: S.save_profile(me["User_ID"], Height_Cm=height.get(), Weight_Kg=weight.get(), Blood_Type=blood.get(),
                                            Allergies=allergies.get(), Conditions=cond.get()))
        f3 = tab("Emergency Contact")
        en, er, ep = rows(f3, [("Name", entry(f3, prof["Emergency_Name"])), ("Relationship", entry(f3, prof["Emergency_Relation"])),
                               ("Phone", entry(f3, prof["Emergency_Phone"]))])
        saver(f3, 3, lambda: S.save_profile(me["User_ID"], Emergency_Name=en.get(), Emergency_Relation=er.get(), Emergency_Phone=ep.get()))
        f4 = tab("Notifications")
        v_rem, v_week = tk.BooleanVar(value=storage.to_bool(prof["Notify_Reminders"])), tk.BooleanVar(value=storage.to_bool(prof["Notify_Weekly"]))
        ttk.Checkbutton(f4, text="Show medication reminder pop-ups (with sound)", variable=v_rem).grid(row=0, column=0, sticky="w", pady=6)
        ttk.Checkbutton(f4, text="Weekly progress summary", variable=v_week).grid(row=1, column=0, sticky="w", pady=6)
        saver(f4, 2, lambda: S.save_profile(me["User_ID"], Notify_Reminders=v_rem.get(), Notify_Weekly=v_week.get()))
        f5 = tab("Settings")
        snooze = rows(f5, [("Snooze length (minutes)", entry(f5, prof["Snooze_Min"]))])[0]
        v_sound = tk.BooleanVar(value=storage.to_bool(prof["Sound_On"]))
        ttk.Checkbutton(f5, text="Play a sound with reminders", variable=v_sound).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        saver(f5, 2, lambda: S.save_profile(me["User_ID"], Snooze_Min=snooze.get(), Sound_On=v_sound.get()))
        label(f5, f"Your data is stored only on this computer:\n{C.DATA_DIR}", 9, color=C.MUTED, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(16, 0))
        self.footer(p, 2)


def main():
    DrukCareApp().mainloop()


if __name__ == "__main__":
    main()
