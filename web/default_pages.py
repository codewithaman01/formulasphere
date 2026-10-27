"""First version of the footer pages. They are copied into the database once (migration web.0002) and from then on
edited by staff in the panel under Site pages. They are a sensible starting point, NOT legal advice: have a
lawyer read the Privacy and Terms pages before you take real payments."""
PAGES = [
    dict(slug="privacy", title="Privacy", sort_order=10, body="""This page explains what FormulaSphere stores about you and why.

## What we collect
When you sign up we store your username, email address, the grade you chose and your password (stored only as a one-way hash, never in plain text). While you use the site we store which formulas you open, what you search for, the formulas you save and your practice marks. If you pay, we store the plan you chose and the payment reference or payment id. We do not store card or UPI details; online payments are handled by the payment provider.

## Why we collect it
To run your account and trial, to show your saved formulas and progress, to confirm payments, to send account emails (welcome, trial or Premium ending, payment received), to improve the content (for example by seeing which searches find nothing) and to protect the site from copying and misuse.

## Cookies and local storage
We use a sign-in (session) cookie and a security (CSRF) cookie, which the site needs to work. Your browser may also keep a small setting for the light or dark theme. We do not use advertising cookies.

## Who sees it
Only the people who run FormulaSphere. We do not sell your data. We share it only with service providers needed to run the site (hosting, email and, if you pay online, the payment provider), or when the law requires it.

## Your choices
You can ask us to correct or delete your account and the data linked to it. Use the Contact page.

## Changes
We may update this page. The latest version is always here."""),
    dict(slug="terms", title="Terms", sort_order=20, body="""By creating an account or using FormulaSphere you agree to these terms.

## Your account
Keep your password private. One account is for one person. Signing in on many devices at once may sign your older devices out.

## Use of the content
The formulas, explanations and worked examples are for your own study and teaching. You may not copy, scrape, redistribute, resell or publish them in bulk, or share your paid account with others. Access may be limited or closed if the site detects this.

## Trial, Premium and payments
New accounts get a free trial of basic formulas for the number of days shown at sign-up. Premium opens the formulas for your grade for the length of the plan you pay for. Premium days are added once the payment is confirmed. If you think you were charged wrongly, contact us with your payment reference.

## Accuracy
We work to keep every formula correct and reviewed, and we mark content that has not been reviewed. Formulas are study aids: check important results (exams, engineering, medicine, finance) against your textbook or the cited source before relying on them.

## Content you submit
If you submit a formula, you confirm it is your own work or properly credited, and you allow us to edit, review and publish it on FormulaSphere. We may decline or remove any submission.

## Changes and contact
We may change these terms or the site. Questions: see the Contact page."""),
    dict(slug="contact", title="Contact", sort_order=30, body="""We are glad to hear from you.

## Questions, corrections and payments
Write to the email address shown with the owner's profile on the About page. For a payment question, include your username and the payment reference.

## Found a mistake in a formula?
Please tell us which formula (its title or web address) and what you think is wrong. See the Corrections page for what happens next.

## Private tuition and courses
Use the Tuition page to send a request."""),
    dict(slug="editorial-policy", title="Editorial and verification policy", sort_order=40, body="""Every formula goes through the same steps before students see it.

## Steps
A writer prepares the formula, its variables, units and explanation. A different person reviews it and either approves it or sends it back with notes. Only an approved formula can be published, and nobody can review or publish their own work.

## Verification
Formulas show a verification status. Content that has not been checked against a reliable source is marked as unverified, and demonstration content is marked as a demo until it is reviewed.

## Changes
When a published formula is changed it goes through review again, and the earlier version is kept in its history."""),
    dict(slug="sources", title="Source attribution", sort_order=50, body="""Facts and formulas are not owned by anyone, but explanations, examples and figures are written or adapted with care.

## How we credit
Where a formula or example comes from a book, paper or website, it is listed under References on the formula page. Explanations and worked examples are written for FormulaSphere unless a reference says otherwise.

## Reuse
If you believe something here is not credited properly, tell us on the Contact page and we will fix it."""),
    dict(slug="corrections", title="Corrections", sort_order=60, body="""We want every formula to be right.

## Report a mistake
Use the Contact page and give the formula title, what is wrong and, if you can, a source.

## What we do
A reviewer checks the report. If it is correct, the formula is fixed and goes through review again. Important corrections are noted in the formula's history."""),
]
