"""DrukCare settings: folders, colours and IMAGE PATHS.

=====================================================================
  WANT TO USE YOUR OWN PHOTOS?  EDIT THE "IMAGE PATHS" BLOCK BELOW
  (or simply save your photo into the assets/ folder with the same
  file name as listed here - no code change needed).
=====================================================================
"""
from pathlib import Path

# ---------------------------------------------------------------- folders
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"
PHOTO_DIR = DATA_DIR / "profile_photos"   # photos uploaded from inside the apps

# ------------------------------------------------------------ IMAGE PATHS
# Paths are relative to the DrukCare folder.  Change them to point at any
# image you like.  Supported formats: .jpg .jpeg .png .webp .bmp .gif
LOGO = "assets/logo.png"                              # square, transparent PNG, 256x256
LOGIN_FULL = "assets/login_full.jpg"                  # full-window login background (no form baked in)
LOGIN_BANNER = "assets/login_banner.jpg"              # 1600x900   (login / create-account screen)
HOME_BANNER = "assets/home_banner.jpg"                # 1600x320
MEDICATION_BANNER = "assets/medication_banner.jpg"    # 1600x320
EXERCISE_BANNER = "assets/exercise_banner.jpg"        # 1600x320
PRESCRIPTIONS_BANNER = "assets/prescriptions_banner.jpg"  # 1600x320
ANALYTICS_BANNER = "assets/analytics_banner.jpg"      # 1600x320
PROFILE_BANNER = "assets/profile_banner.jpg"          # 1600x320
PROVERB_BANNER = "assets/proverb_banner.jpg"          # 1600x200  (strip at the bottom of Home)
PROFILE_IMAGE = "assets/profile.jpg"                  # square, 400x400 (default profile photo)
LOGO_SIDEBAR = "assets/logo_sidebar.png"              # cross + name on dark teal (sidebar)
LOGO_FULL = "assets/logo_full.png"                    # horizontal logo with tagline
WAVES = "assets/waves.jpg"                            # wave strip at the bottom of every page
GRADIO_BANNER = "assets/gradio_banner.jpg"            # header of the prescription portal
NAV_IMAGES = {"Medication": "assets/nav_medication.jpg", "Exercise": "assets/nav_exercise.jpg",
              "Prescriptions": "assets/nav_prescriptions.jpg", "Analytics": "assets/nav_analytics.jpg"}
MASCOT_IMAGE = "assets/mascot.png"                    # friendly dragon doctor (Home page)
SIDEBAR_DRAGON = "assets/sidebar_dragon.png"          # decoration at the bottom of the sidebar
BANNER_BACKGROUND = "assets/banner_background.jpg"    # teal dzong landscape behind every banner photo + quote card

PAGE_BANNERS = {
    "Home": HOME_BANNER,
    "Medication": MEDICATION_BANNER,
    "Exercise": EXERCISE_BANNER,
    "Prescriptions": PRESCRIPTIONS_BANNER,
    "Analytics": ANALYTICS_BANNER,
    "My Profile": PROFILE_BANNER,
}

SUPPORTED_IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")

# ---------------------------------------------------------------- colours
# Teal theme taken from the DrukCare design samples (same colours on every page / app)
NAVY = "#01333C"          # sidebar (same dark teal as the design sample)
NAVY_DARK = "#004447"     # sidebar (bottom)
NAV_ACTIVE = "#14A595"    # active menu item (bright teal pill)
NAV_HOVER = "#0B4F57"     # menu item under the mouse
BUTTON_DARK = "#003440"   # dark "Go to ..." buttons on the Home tiles
EMERALD = "#018A94"       # main teal: buttons, rings, highlights
EMERALD_DARK = "#006F78"
TEAL_LIGHT = "#1FB5A5"    # bright teal accents on the dark sidebar
GREEN_SOFT = "#DDF4F0"
IVORY = "#EAF5F9"         # page background
IVORY_DARK = "#DCEEF3"
CARD = "#FBFEFE"
SURFACE = "#F1F8FA"       # inputs, ghost buttons
TRACK = "#CDE7E6"         # empty part of bars and rings
GRID = "#DCEBEE"          # chart grid lines
TEXT = "#0E2A47"
MUTED = "#5C7185"
BORDER = "#CFE5E8"
TINT_BLUE = "#E5F1FD"     # pastel stat-card backgrounds
TINT_MINT = "#E6F8F8"
TINT_PEACH = "#FDECDC"
PRIORITY_COLORS = {"High": "#D64545", "Medium": "#E0821B", "Low": "#2E9E5B"}
PRIORITY_BG = {"High": "#FDE3E3", "Medium": "#FFEBD2", "Low": "#DDF5E6"}
STATUS_COLORS = {
    "Taken": "#14935F", "Missed": "#D64545", "Snoozed": "#7B5FC7",
    "Overdue": "#D64545", "Upcoming": "#2B7FBF",
}

# ----------------------------------------------------------- app settings
APP_NAME = "DrukCare"
TAGLINE = "Better Care. Healthier Bhutan."
STREAMLIT_PORT = 8501
GRADIO_PORT = 7860

WELLNESS_MESSAGES = [
    ("Health is wealth.", "Bhutanese Proverb"),
    ("Small steps today, a healthier tomorrow.", "DrukCare"),
    ("A glass of water and a short walk can change your whole day.", "DrukCare"),
    ("Taking medicine on time is a kindness to your future self.", "DrukCare"),
    ("Rest well, move gently, eat with gratitude.", "DrukCare"),
    ("Good health is the foundation of a happy life.", "DrukCare"),
]


# ---------------------------------------------------------------- MEDICINE LIST
# Medicine names are chosen from this list (dropdown only), so nobody has to type them
# and spellings can never go wrong. Each medicine has a ready-made usual dosage that is
# filled in automatically (it can still be changed from the Dosage dropdown).
# To add a medicine, add one line:  "Name strength": "usual dosage",
# This is a student-project reference list of common medicines, NOT medical advice.
MEDICINE_DOSES = {
    # pain, fever, inflammation
    "Paracetamol 500 mg": "1 tablet", "Paracetamol 650 mg": "1 tablet",
    "Paracetamol Syrup 125 mg/5 ml": "5 ml", "Ibuprofen 200 mg": "1 tablet", "Ibuprofen 400 mg": "1 tablet",
    "Diclofenac 50 mg": "1 tablet", "Aspirin 75 mg": "1 tablet", "Aspirin 325 mg": "1 tablet",
    "Tramadol 50 mg": "1 capsule",
    # antibiotics and anti-infectives
    "Amoxicillin 250 mg": "1 capsule", "Amoxicillin 500 mg": "1 capsule",
    "Amoxicillin + Clavulanate 625 mg": "1 tablet", "Azithromycin 250 mg": "1 tablet",
    "Azithromycin 500 mg": "1 tablet", "Cefixime 200 mg": "1 tablet", "Cephalexin 500 mg": "1 capsule",
    "Ciprofloxacin 500 mg": "1 tablet", "Cloxacillin 500 mg": "1 capsule", "Cotrimoxazole 480 mg": "2 tablets",
    "Doxycycline 100 mg": "1 capsule", "Erythromycin 250 mg": "1 tablet", "Metronidazole 400 mg": "1 tablet",
    "Nitrofurantoin 100 mg": "1 capsule", "Norfloxacin 400 mg": "1 tablet",
    "Acyclovir 200 mg": "1 tablet", "Acyclovir 400 mg": "1 tablet", "Fluconazole 150 mg": "1 capsule",
    "Albendazole 400 mg": "1 tablet", "Mebendazole 100 mg": "1 tablet",
    # allergy, cough, breathing
    "Cetirizine 5 mg": "1 tablet", "Cetirizine 10 mg": "1 tablet", "Loratadine 10 mg": "1 tablet",
    "Levocetirizine 5 mg": "1 tablet", "Chlorpheniramine 4 mg": "1 tablet", "Montelukast 10 mg": "1 tablet",
    "Salbutamol 4 mg": "1 tablet", "Salbutamol Inhaler": "2 puffs", "Budesonide Inhaler": "2 puffs",
    "Cough Syrup (Dextromethorphan)": "10 ml", "Prednisolone 5 mg": "1 tablet",
    # stomach and digestion
    "Omeprazole 20 mg": "1 capsule", "Pantoprazole 40 mg": "1 tablet", "Ranitidine 150 mg": "1 tablet",
    "Domperidone 10 mg": "1 tablet", "Ondansetron 4 mg": "1 tablet", "Antacid Gel": "10 ml",
    "Loperamide 2 mg": "1 capsule", "Bisacodyl 5 mg": "1 tablet", "Lactulose Syrup": "15 ml",
    "ORS Sachet": "1 sachet in 1 litre water", "Hyoscine Butylbromide 10 mg": "1 tablet",
    # heart and blood pressure
    "Amlodipine 5 mg": "1 tablet", "Amlodipine 10 mg": "1 tablet", "Atenolol 50 mg": "1 tablet",
    "Enalapril 5 mg": "1 tablet", "Losartan 50 mg": "1 tablet", "Telmisartan 40 mg": "1 tablet",
    "Hydrochlorothiazide 25 mg": "1 tablet", "Furosemide 40 mg": "1 tablet",
    "Atorvastatin 10 mg": "1 tablet", "Atorvastatin 20 mg": "1 tablet", "Clopidogrel 75 mg": "1 tablet",
    # diabetes and thyroid
    "Metformin 500 mg": "1 tablet", "Metformin 1000 mg": "1 tablet", "Gliclazide 80 mg": "1 tablet",
    "Glimepiride 1 mg": "1 tablet", "Insulin (Regular)": "As prescribed (units)",
    "Levothyroxine 50 mcg": "1 tablet", "Levothyroxine 100 mcg": "1 tablet",
    # vitamins and supplements
    "Calcium 500 mg": "1 tablet", "Calcium + Vitamin D3": "1 tablet", "Folic Acid 5 mg": "1 tablet",
    "Iron + Folic Acid": "1 tablet", "Ferrous Sulphate 200 mg": "1 tablet", "Multivitamin": "1 tablet",
    "Vitamin B Complex": "1 tablet", "Vitamin B12 500 mcg": "1 tablet", "Vitamin C 500 mg": "1 tablet",
    "Vitamin D3 1000 IU": "1 capsule", "Vitamin D3 60000 IU": "1 capsule", "Zinc 20 mg": "1 tablet",
    # mind, sleep, nerves
    "Amitriptyline 10 mg": "1 tablet", "Diazepam 5 mg": "1 tablet", "Sertraline 50 mg": "1 tablet",
    "Fluoxetine 20 mg": "1 capsule", "Phenytoin 100 mg": "1 capsule", "Carbamazepine 200 mg": "1 tablet",
    "Sodium Valproate 200 mg": "1 tablet",
    # eye, ear, skin
    "Chloramphenicol Eye Drops": "1 drop", "Ciprofloxacin Eye Drops": "1 drop",
    "Artificial Tears Eye Drops": "1 drop", "Ear Wax Drops": "3 drops",
    "Clotrimazole Cream": "Apply thin layer", "Hydrocortisone Cream 1%": "Apply thin layer",
    "Mupirocin Ointment": "Apply thin layer", "Calamine Lotion": "Apply thin layer",
}
MEDICINES = sorted(MEDICINE_DOSES, key=str.lower)

# Dosage choices for the Dosage dropdown (no typing needed).
DOSAGE_OPTIONS = [
    "1/2 tablet", "1 tablet", "2 tablets", "1 capsule", "2 capsules", "1 sachet in 1 litre water",
    "2.5 ml", "5 ml", "10 ml", "15 ml", "1 puff", "2 puffs", "1 drop", "2 drops", "3 drops",
    "Apply thin layer", "As prescribed (units)",
]
