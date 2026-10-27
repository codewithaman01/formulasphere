"""
The list of things a role can be given access to.

A role is NOT hard-coded: an admin creates a role in the panel and ticks any of the
items below. The tick-list is stored on the role (StaffRole.access).

Most areas have four ticks, like the Django admin and the school timetable app:
    Can add X, Can change X, Can delete X, Can view X
and the panel checks each one on its own (a role may add subjects but not delete them).

To add a new area later: add one line to AREAS (or CUSTOM) and one to PAGES.

scoped=True means "only for the subjects assigned to the user" (for example a
reviewer for Physics cannot review Chemistry).
"""

# key, section title shown in the role form, singular noun used in the labels
AREAS = [
    ("subjects",      "Subjects",       "subject"),
    ("topics",        "Topics",         "topic"),
    ("levels",        "Academic levels", "academic level"),
    ("grades",        "Grades",         "grade"),
    ("plans",         "Premium plans",  "premium plan"),
    ("plan_requests", "Plan requests and payments", "plan request"),
    ("courses",       "Courses",        "course"),
    ("live_classes",  "Live classes",   "live class"),
    ("enrollments",   "Course enrollments", "enrollment"),
    ("tuition_offers", "Tuition offers", "tuition offer"),
    ("enquiries",     "Tuition enquiries", "tuition enquiry"),
    ("snippets",      "Code snippets",  "code snippet"),
    ("references",    "References",     "reference"),
    ("account_types", "Account types",  "account type"),
    ("leaders",       "Owner and team profiles", "owner or team profile"),
    ("leader_items",  "Qualifications and achievements", "qualification or achievement"),
    ("static_pages",  "Site pages",     "site page"),
    ("site_settings", "Site logo and icon", "site logo and icon"),
    ("roles",         "Roles",          "role"),
    ("staff",         "Staff access",   "staff access"),
]

CUSTOM = [
    # code,               group,           label,                          help,                                                         scoped
    ("formulas.create",   "Formulas",      "Can write formulas",           "Create and edit draft formulas and send them for review.",   True),
    ("formulas.review",   "Formulas",      "Can review formulas",          "Open submitted formulas, approve them or send them back.",   True),
    ("formulas.publish",  "Formulas",      "Can publish formulas",         "Publish approved formulas, or take published ones down.",    True),
    ("students.view",     "Students",      "Can view students",            "See users, their account type, grade and plan.",             False),
    ("students.grant",    "Students",      "Can grant premium",            "Give a user extra days of premium (the number of days is a setting).",                       False),
    ("audit.view",        "Activity log",  "Can view activity log",        "See who changed roles, access and premium, and when.",       False),
]

_ACTIONS = [("add", "add"), ("change", "change"), ("delete", "delete"), ("view", "view")]


def _build():
    out = list(CUSTOM[:3])                        # formulas first
    for key, group, noun in AREAS:
        for act, word in _ACTIONS:
            extra = " (also pause, resume and reset two-factor)" if key == "staff" and act == "change" else ""
            out.append((f"{key}.{act}", group, f"Can {word} {noun}{extra}", f"Can {word} {noun}.", False))
    out += CUSTOM[3:]
    return out


ACCESS = _build()
ALL_CODES = {a[0] for a in ACCESS}
SCOPED_CODES = {a[0] for a in ACCESS if a[4]}

# Old broad codes (from before each action had its own tick). They still work: a role that
# holds one is treated as holding everything it used to cover. Saving the role converts it.
LEGACY = {
    "content.taxonomy":   [f"{k}.{a}" for k in ("subjects", "topics") for a, _ in _ACTIONS],
    "content.snippets":   [f"snippets.{a}" for a, _ in _ACTIONS],
    "content.references": [f"references.{a}" for a, _ in _ACTIONS],
    "users.students":     ["students.view", "students.grant"],
    "admin.roles":        [f"roles.{a}" for a, _ in _ACTIONS],
    "admin.account_types": [f"account_types.{a}" for a, _ in _ACTIONS],
    "admin.staff":        [f"staff.{a}" for a, _ in _ACTIONS],
    "admin.audit":        ["audit.view"],
}


def expand(codes):
    """Turn a stored list of codes (new or old) into the set of current codes it means."""
    out = set()
    for c in codes or []:
        if c in LEGACY:
            out.update(LEGACY[c])
        else:
            out.add(c)
    return out & ALL_CODES


def grouped():
    """[(group name, [{code,label,help,scoped}, ...]), ...] in display order."""
    out = {}
    for code, group, label, help_, scoped in ACCESS:
        out.setdefault(group, []).append({"code": code, "label": label, "help": help_, "scoped": scoped})
    return list(out.items())


def summary(codes):
    """Short text for the roles list: 'Formulas (2), Subjects (4)'."""
    held = expand(codes)
    parts = []
    for group, items in grouped():
        n = sum(1 for c in items if c["code"] in held)
        if n:
            parts.append(f"{group} ({n})" if len(items) > 1 else group)
    return ", ".join(parts) or "Nothing yet"


# Panel pages. A page shows in the menu when the user holds ANY of its codes.
# url is (url name, kwargs).
PAGES = [
    {"key": "formulas",   "label": "Formulas",         "url": ("panel:formulas", {}),
     "any": ["formulas.create", "formulas.review", "formulas.publish"],
     "text": "Write, review and publish formulas."},
    {"key": "subjects",   "label": "Subjects",         "url": ("panel:crud_list", {"key": "subjects"}),
     "any": ["subjects.view"], "text": "Subjects shown on the site."},
    {"key": "topics",     "label": "Topics",           "url": ("panel:crud_list", {"key": "topics"}),
     "any": ["topics.view"], "text": "Topics inside each subject."},
    {"key": "levels",     "label": "Academic levels",  "url": ("panel:crud_list", {"key": "levels"}),
     "any": ["levels.view"], "text": "School, Undergraduate, Postgraduate, Research..."},
    {"key": "grades",     "label": "Grades",           "url": ("panel:crud_list", {"key": "grades"}),
     "any": ["grades.view"], "text": "Class 1 to 12, Undergraduate... what people sign up with."},
    {"key": "plans",      "label": "Premium plans",    "url": ("panel:crud_list", {"key": "plans"}),
     "any": ["plans.view"], "text": "Amounts, length and what each plan includes."},
    {"key": "plan_requests", "label": "Plan payments",  "url": ("panel:crud_list", {"key": "plan_requests"}),
     "any": ["plan_requests.view"], "text": "Confirm payments; Premium is added automatically."},
    {"key": "courses",    "label": "Courses",          "url": ("panel:crud_list", {"key": "courses"}),
     "any": ["courses.view"], "text": "Courses students can enrol in."},
    {"key": "live_classes", "label": "Live classes",   "url": ("panel:crud_list", {"key": "live_classes"}),
     "any": ["live_classes.view"], "text": "Scheduled online classes and their meeting links."},
    {"key": "enrollments", "label": "Enrollments",     "url": ("panel:crud_list", {"key": "enrollments"}),
     "any": ["enrollments.view"], "text": "Who is in which course; confirm payments here."},
    {"key": "tuition_offers", "label": "Tuition offers", "url": ("panel:crud_list", {"key": "tuition_offers"}),
     "any": ["tuition_offers.view"], "text": "Private tuition you offer."},
    {"key": "enquiries",  "label": "Tuition enquiries", "url": ("panel:crud_list", {"key": "enquiries"}),
     "any": ["enquiries.view"], "text": "Requests from the Tuition page."},
    {"key": "snippets",   "label": "Code snippets",    "url": ("panel:crud_list", {"key": "snippets"}),
     "any": ["snippets.view"], "text": "Python and Java examples."},
    {"key": "references", "label": "References",       "url": ("panel:crud_list", {"key": "references"}),
     "any": ["references.view"], "text": "Books, papers and websites."},
    {"key": "leaders",    "label": "Owner and team",   "url": ("panel:crud_list", {"key": "leaders"}),
     "any": ["leaders.view"], "text": "Owner / CEO profile, photo and message shown at the bottom of the site."},
    {"key": "leader_items", "label": "Qualifications and achievements", "url": ("panel:crud_list", {"key": "leader_items"}),
     "any": ["leader_items.view"], "text": "Qualifications, achievements and experience listed under each person."},
    {"key": "static_pages", "label": "Site pages", "url": ("panel:crud_list", {"key": "static_pages"}),
     "any": ["static_pages.view"], "text": "Privacy, Terms, Contact and the other pages linked at the bottom of the site."},
    {"key": "site_settings", "label": "Site logo", "url": ("panel:branding", {}),
     "any": ["site_settings.view", "site_settings.change"], "text": "Upload the logo shown in the header and the icon shown in the browser tab."},
    {"key": "students",   "label": "Students",         "url": ("panel:students", {}),
     "any": ["students.view"], "text": "Users, trials and premium."},
    {"key": "roles",      "label": "Roles",            "url": ("panel:roles", {}),
     "any": ["roles.view"], "text": "Create roles and choose their access."},
    {"key": "account_types", "label": "Account types", "url": ("panel:crud_list", {"key": "account_types"}),
     "any": ["account_types.view"], "text": "Student, Teacher, Professor... shown on sign-up."},
    {"key": "staff",      "label": "Staff",            "url": ("panel:staff", {}),
     "any": ["staff.view"], "text": "Give roles to users."},
    {"key": "audit",      "label": "Activity log",     "url": ("panel:audit", {}),
     "any": ["audit.view"], "text": "Who changed what, and when."},
]
