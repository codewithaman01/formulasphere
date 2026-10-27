# FormulaSphere — Phase 1

## Run
Database: MongoDB (Atlas). In Atlas: create a cluster, add your IP under Network Access, create a database user, then Connect -> Drivers and copy the connection string into `.env` as `MONGODB_URI`.

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env            # fill in MONGODB_URI and the other values
    python manage.py migrate        # creates the collections and indexes
    python manage.py createsuperuser
    python manage.py seed_content         # levels, grades, subjects, ~690 formulas, topics, code examples (from the text files)
    python manage.py seed_account_types   # Student, Teacher, Professor, Research Scholar
    python manage.py seed_roles           # optional example roles
    python manage.py seed_learning        # starter courses and tuition offers, created as unpublished drafts
    python manage.py seed_plans           # example Premium plans (hidden until you set your own amounts)
    python manage.py runserver

Tests need a MongoDB replica set (transactions): `python manage.py test`. Atlas works; for a local one start `mongod --replSet rs0` and run `rs.initiate()` once.

Backups: Atlas free clusters have no automatic backups. Run `python manage.py backup_db` nightly; restore with `python manage.py restore_db backups/<file>`.

Search is a plain word match (every word must appear in title, keywords or explanation; title and keyword matches rank first). It is not typo-tolerant.

Many-to-many fields are batch-loaded with `config.prefetch.prefetch()` because MongoDB's Django backend does not support `prefetch_related` for them.

## Architecture
- `taxonomy`: Subject (nested), AcademicLevel, Curriculum, Course, Topic.
- `formulas`: Formula and its variables, derivation steps, assumptions, examples, references, revisions, reviews.
- `formulas/workflow.py`: the only place status changes happen (draft → submitted → in review → approved → published; needs correction; archived). Reviewing needs `review_formula`, publishing needs `publish_formula`, and publishing requires a reviewer on record. Each change writes a `FormulaRevision`.
- `formulas/search.py`: weighted word matching (see above). Only `published` rows are queried.
- `web`: homepage, explore (filters, sort, pagination), detail page, suggestion endpoint. No `forms.py`; filters are GET parameters.
- Source verification is a separate field from publication status and review date.

## Not yet built (later phases)
DRF API, accounts and bookmarks, subject/topic pages, LaTeX sanitising beyond KaTeX `trust:false`, tests, sitemap.

## Staff panel (replaces Django admin for staff)
Staff work at `/panel/`. Django admin (`/admin/`) is only for the superuser.

- **Roles** (`/panel/roles/`): create a role and tick what it can open (write / review / publish formulas, subjects and topics, snippets, references, students, roles, staff, activity log). Stored on the role, so no code change is needed to add or change roles. A role can also have *usual subjects* (used when you give it to someone without choosing subjects) and, for superusers, *require two-factor*.
- **Staff** (`/panel/staff/`): give a role to a user (an existing username, or create the account right there). Roles that work on formulas are limited to the subjects you choose. **Pause** switches an assignment off without deleting it.
- **After sign-in** the user goes straight to their page if the role opens only one, otherwise to `/panel/` with a menu that shows only what the role allows. Every page also checks access on the server.
- **Activity log** (`/panel/audit/`): who changed roles, staff access, premium and two-factor, and when. Rows are only added, never edited.
- **Two-factor** (`/panel/security/`): authenticator-app codes (Google Authenticator, Microsoft Authenticator, Authy). Required for roles that have it switched on; anyone in the panel can also turn it on for themselves. A superuser can reset someone's two-factor from the Staff page.
- **Sign-in protection**: 5 wrong passwords (per username and address) lock that sign-in for 15 minutes; the same for wrong two-factor codes. The count lives in Django's cache. The default cache is per process, so with several workers use a shared cache (see the note in `config/settings.py`).

To add a new page later: add a line to `ACCESS` and `PAGES` in `accounts/permissions.py`, and guard the view with `@need("your.code")`. The test `test_every_panel_page_is_guarded_by_its_own_code` then checks it automatically.

### Upgrading from the old three-checkbox roles
After `makemigrations` and `migrate`, run `python manage.py upgrade_roles` once. It turns old create / review / publish roles into the new access list. The three old columns can then be deleted from `StaffRole` in a later migration.

### Settings
Secrets come from environment variables or a `.env` file (copy `.env.example`). `DJANGO_SECRET_KEY` is required unless `DJANGO_DEBUG=1`.

### Tests
`python manage.py test panel` (needs the MongoDB settings in .env).

## Account types (who signs up)
At sign-up a person first picks **who they are** (Student, Teacher, Professor, Research Scholar...). These are created and edited by an admin at `/panel/c/account_types/` (menu: **Account types**, access code `admin.account_types`).

- **Ask for grade** ticked (Student): the Grade list appears after choosing it, and the person must pick one.
- **Ask for grade** not ticked (Teacher, Professor...): no grade list. The admin picks a **formula level** instead, which decides which formulas that type can open.
- **Show on sign-up** unticked hides a type from new sign-ups; existing users keep it. A type that still has users cannot be deleted.
- After `makemigrations` and `migrate`, run `python manage.py seed_account_types` once. It adds the four starter types and marks existing users as Student.
- API: `GET /api/v1/account-types/`; `POST /api/v1/auth/register/` takes `account_type` (slug) and `grade` (only for types that ask). Omitting `account_type` means `student`, so the current mobile app keeps working.

## Role permissions (per action)
`/panel/roles/new/` shows one section per area (Formulas, Subjects, Topics, Code snippets, References, Account types, Roles, Staff access, Students, Activity log). Most areas have four separate ticks: **Can add / Can change / Can delete / Can view**, and every panel page and button checks its own tick (a role can add subjects without being able to delete them). Formulas keep write / review / publish, limited to the subjects chosen under Staff access.

- Old roles keep working: the old broad codes (for example `content.taxonomy`, `admin.staff`) are read as "all four ticks" for that area. Saving the role converts it to the new ticks.
- Someone who is not a superuser can only tick what they hold themselves.
- To add a new area: add one line to `AREAS` (or `CUSTOM`) and one to `PAGES` in `accounts/permissions.py`, and register it in `CRUD` in `panel/views.py`.

### Grade access per account type
Each account type (Account types page) has two grade settings besides its main level:
- **Open every grade**: the type opens formulas of every grade and level (Class 1 to Research). The starter *Professor* type has this on.
- **Also open these grades**: tick extra grades, for example a Teacher who also opens Class 9 to 12 and Undergraduate.

A Student still sees only their own grade unless the Student type is given extras. Premium and trial rules are unchanged: this setting decides *which grades*, not whether a formula is free.
After updating, run `python manage.py makemigrations accounts` and `python manage.py migrate`. For an existing Professor type, open it in the panel and tick *Open every grade* (the seed command only sets it for newly created types).


## Soft-coded: nothing below is typed into the code
Everything that used to be a Python list is now a table you edit in the panel, or a plain text line you add to a data file.

| What | Where you change it |
|---|---|
| **Grades** (Class 1 to 12, Undergraduate, Postgraduate, Research...) | Panel > **Grades** (`/panel/c/grades/`), or `formulas/data/grades.txt`. Add, rename, reorder, hide from sign-up. The code (slug) of a grade cannot change once created, and a grade still in use cannot be deleted. |
| **Academic levels** (School, Undergraduate...) | Panel > **Academic levels**, or `formulas/data/levels.txt` |
| **Subjects** | Panel > **Subjects**, or `formulas/data/subjects.txt` |
| **Topics** | Panel > **Topics**, or `formulas/data/topics*.txt` |
| **Formulas** | Panel > **Formulas**, or any `.txt` file in `formulas/data/formulas/` |
| **Account types** | Panel > **Account types**, or `accounts/data/account_types.txt` |
| **Starter roles** | Panel > **Roles**, or `accounts/data/roles.txt` |
| **Trial days, premium grant days, lock-out limits, page sizes** | `.env` (`FS_TRIAL_DAYS`, `FS_PREMIUM_GRANT_DAYS`, `FS_LOCKOUT_LIMIT`, `FS_LOCKOUT_MINUTES`, `FS_EXPLORE_PAGE_SIZE`, `FS_PANEL_PAGE_SIZE`...) |
| **Grade list in the mobile app** | Loaded from `GET /api/v1/grades/` |

### Grade access for roles
On the role form (`/panel/roles/new/`) the section **Grades this role can see** has **can see every grade** and one tick per grade. People with that role can open the formulas of those grades on the site, with no trial or premium needed (so reviewers can read what they review). It adds to anything their own account gives them. Pausing a staff assignment pauses its grade access too. Someone who is not a superuser can only hand out grades they hold themselves. Changes appear in the Activity log. (Which formulas a role may *edit, review or publish* is still decided by the subjects chosen under Staff access.)

### Adding content without touching code
Add lines to a data file, or add a new `.txt` file, then run `python manage.py seed_content`. It only adds what is missing and never changes a row you edited in the panel.

    formulas/data/formulas/*.txt   subject | grade code | title | LaTeX | short explanation | variables | access | difficulty | other subjects
    formulas/data/topics*.txt      subject | topic | formula titles separated by ;
    formulas/data/grades.txt       code | grade slug | name | level | class number | usual access | usual difficulty | order

* The grade code (S9, U, P, R...) comes from `grades.txt`; a new grade there is immediately usable in formula files. Access (basic or premium) and difficulty default from the grade and can be overridden per formula.
* Variables are `symbol~name~unit;symbol~name~unit`. Do not put the `|` character inside LaTeX (use `\mid`, `\lvert`, `\rvert`).
* `python manage.py seed_content --check` finds mistakes (unknown codes, repeated titles, topics naming formulas that do not exist) without touching the database. Use `--dir /path/to/your/data` to load your own folder, `--draft` to load new formulas as drafts, `--only formulas topics` to run some steps.
* Loaded formulas are flagged `is_demo` because they were written from general knowledge and have **not** been checked by a subject expert. Review them in the panel before relying on them.

### What the starter data covers (689 formulas, every one in a topic)
Mathematics 194, Physics 151, Chemistry 60, Statistics 48, Engineering 47, Economics 43, Data Science 40, Computer Science 39, Biology 37, Astronomy 33 (a formula can belong to two subjects). Levels run from Class 3 to Research. Classes 1 to 5 only have a few basic mathematics formulas, because science at those classes has none.


## Explanations
* Every **topic** now has an *explanation* (shown as "About this topic" on the topic page). Edit it in the panel under Topics.
* Formulas have a *detailed explanation* and *worked examples* (already shown on the formula page). 105 topic explanations, 62 formula explanations and 61 worked examples ship in `formulas/data/explanations_topics.txt` and `explanations_formulas.txt`; the other formulas show their short explanation and variable table until you add more.
* To add more, append blocks to any `formulas/data/explanations*.txt` file and run `seed_content`:

      @@ formula|Exact formula title
      Explanation paragraphs. A blank line starts a new paragraph.
      ## example|Example title|Problem|Step one // Step two // Step three|Result|Units

      @@ topic|M|Topic name

  Loading only fills explanations that are still empty, so text you wrote in the panel is never replaced. `seed_content --check` reports titles or topics that do not exist.
* Like the formulas, these were written from general knowledge and have not been checked by a subject expert.

## Courses, live classes and tuition (new `learning` app)
Pages: `/courses/`, `/live/`, `/tuition/` and `/my-learning/` (all linked from the menu). Manage everything in the staff panel: **Courses, Live classes, Enrollments, Tuition offers, Tuition enquiries**. Each has its own permission (`courses.*`, `live_classes.*`, `enrollments.*`, `tuition_offers.*`, `enquiries.*`), so you can give a helper only what they need through Roles.

* **Courses** are linked to a subject, the grades they are for (from the Grades table) and the topics they cover (which link to formulas). A price of 0 is free and enrols at once; a paid course saves the student's place as *Waiting for payment* until staff set the enrollment to *Active* under Enrollments (there is no payment gateway; confirm payment yourself, for example UPI, and note the reference).
* **Live classes** have a time, length, optional capacity, a meeting link (Google Meet, Zoom...) and, later, a recording link. The meeting link is shown only to registered students (or active course students), from `FS_LIVE_JOIN_EARLY_MINUTES` before the start until the end. Registration respects the capacity. The panel shows seats taken.
* **Tuition**: publish offers (subject, grades, online or in person, area, fee or a fee note, batch size). Visitors send a request on the Tuition page; it appears under Tuition enquiries, where you set a status (New, Contacted, Trial class booked, Enrolled, Closed) and add private notes. The form has a hidden spam trap and a per-connection limit (`FS_ENQUIRY_LIMIT` per hour).
* `seed_learning` creates 10 starter courses and 4 tuition offers from `learning/data/courses.txt` and `tuition.txt` as **unpublished drafts**. Check the details and fees, then tick *Published*. Not included: online payment, video hosting (use a link) and notification emails.


## Premium plans (amount and what students get)
The Premium page (`/premium/`) is built from plans you manage in the panel under **Premium plans** (`/panel/c/plans/`). Each plan has a **name, amount, optional old amount** (shown crossed out with the saving worked out), **how long it lasts** (30 = a month, 365 = a year), a **tagline**, **"what they get"** (one benefit per line, each shown with a tick), an optional description and a **"most popular"** highlight. Untick *Show on the Premium page* to hide a plan.

How a student buys (no payment gateway needed):
1. They sign in and press **Choose** on a plan. A request is saved as *Waiting for payment*, and the page shows how to pay (set the text with `FS_PAYMENT_INSTRUCTIONS` in `.env`, for example your UPI id).
2. They pay you and type their payment reference on the same page.
3. You open **Plan payments** (`/panel/c/plan_requests/`), check the money and set the status to **Paid**. The plan's days are added to their Premium automatically, **once** (saving again does not add twice), and added on top of any Premium they already have.

Notes: `seed_plans` creates three **example** plans (Monthly 199, 3 months 499, Yearly 1499) as hidden; change the amounts, then show them. The currency symbol is `FS_CURRENCY_SYMBOL` (default ₹) and is also used for course and tuition amounts. A plan that already has requests cannot be deleted (hide it instead). Changing a request back from Paid does not take days away; use the student's Premium date in Students if you need to correct it. Give someone only the *Plan payments* permission (for example a helper who confirms payments) without letting them change prices.

## Owner / CEO profile and theme
- **Owner and team** (`/panel/c/leaders/`): add a person with name, title, profile photo, a short line (shown at the bottom of every page) and a full message (shown on `/about/`). **Qualifications and achievements** (`/panel/c/leader_items/`): add as many lines as you like under a person (qualification, achievement, experience, other), with optional year and detail. Both are access codes on the role (`leaders.*`, `leader_items.*`); a superuser has them automatically.
- Photos are saved in `media/` and served by Django while `DEBUG` is on (needs `pip install Pillow`). In production serve `MEDIA_ROOT` with your web server.
- **Theme**: every visitor can pick Light, Dark or Match my device, and an accent colour, from the header. The choice is kept in that browser.
- Setup: `pip install -r requirements.txt`, then `python manage.py makemigrations web` (only if Django asks) and `python manage.py migrate`.

## Content protection and LaTeX editor
* **Protection** (`FS_PROTECT_CONTENT` in `config/settings.py`, `web/static/web/protect.js`): on `/formulas/`, `/subjects/` and `/explore/` pages, people who are not staff cannot select, copy, right-click, drag or print the content; the page blurs when the window loses focus or PrintScreen is pressed; a faint watermark with the viewer's username is drawn. **This is a deterrent only.** A browser cannot stop a phone camera, a screen recorder or someone reading the page source, so the watermark is the part that helps you trace a leak. Staff accounts are exempt so they can edit.
* **LaTeX editor** (staff panel > Formulas > New): symbol toolbar, live KaTeX preview under every LaTeX box (main formula, derivation steps, variable symbols and units), red error message while the LaTeX is broken. The server also rejects unbalanced `{ }` and unsafe commands (`\href`, `\url`, `\input`, `\def`, HTML tags...).

## What was added in the second update
* **Safer settings**: `config/settings.py` now reads `.env` (see `.env.example`). With `DJANGO_DEBUG=0` the site refuses to start without `DJANGO_SECRET_KEY` and `MONGODB_URI`.
* **Site pages**: Privacy, Terms, Contact, Editorial policy, Source attribution and Corrections are created by `migrate` and edited in the panel under *Site pages*. They are a starting draft, not legal advice: have them reviewed before taking payments.
* **Students add formulas**: *Add a formula* (signed-in menu) with the LaTeX editor. Goes to review as *Submitted*; reviewers send it back with notes and the student fixes it under *My submissions*. Limit per day: `FS_SUBMISSIONS_PER_DAY`.
* **Saved formulas, Recently viewed, Practice** (self-marked: open the solution, then "I got it" or "Not yet").
* **Calculator**: set *calculator expression* on a formula (for example `0.5*m*v^2`); every name becomes an input box.
* **Sitemap and robots**: `/sitemap.xml`, `/robots.txt`. Formula pages need a sign-in, so search engines index only the public pages (home, subjects, pricing, about, site pages).
* **Dashboard** (owner, or anyone with "view students"): sign-ups, Premium, trials ending, conversion, most opened formulas, searches that found nothing, accounts that opened many different formulas in 24 hours, published formulas still marked demo.
* **Protection**: per-account page limit per hour (`FS_VIEW_LIMIT_PER_HOUR`), view log, and a limit of devices signed in at once (`FS_MAX_SESSIONS`). Staff are exempt.
* **Email**: welcome, payment received, trial ending, Premium ending. Run `python manage.py send_reminders` once a day.
* **Online payment (Razorpay)**: fill `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`; in the Razorpay dashboard add a webhook to `https://YOUR-SITE/hooks/razorpay/` for `payment.captured`. Without keys the manual UPI flow works as before.
* **Backups**: `python manage.py backup_db` (uses `mongodump` if installed, else a built-in export). Run it nightly and copy the folder off the server.
* **Tests**: `python manage.py test` (120 tests).

### Daily jobs (cron or Windows Task Scheduler)
    python manage.py send_reminders
    python manage.py backup_db

## Pictures are stored in the database
Owner/team photos, the site logo and the tab icon are saved inside MongoDB (collection `web_storedimage`), not in a `media/` folder. One database backup (`python manage.py backup_db`) now holds everything, and nothing needs to be copied between servers.
* Uploads are checked (JPG, PNG or WebP, up to 3 MB), turned upright, stripped of hidden camera/GPS data and shrunk (photo 600 px, logo 512 px, icon 128 px).
* Pictures are served from `/img/<id>/` and cached by browsers for a year; replacing a picture gives it a new address and deletes the old row.
* `migrate` copies any pictures uploaded before this update from `media/` into the database once. It never deletes the old files; after you check the site you can delete the `media/` folder.
* `MEDIA_ROOT` is now read only by that one migration; nothing is served from it.
