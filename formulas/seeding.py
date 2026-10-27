r"""Loads formulas, topics and code examples from the plain-text files in formulas/data/.

  formulas/data/formulas/*.txt   one line per formula (every .txt file in the folder is read)
  formulas/data/topics*.txt      topic name and the formulas inside it
  formulas/data/*snippets*.txt   Python / Java examples for a subject's topics

To add content, add lines (or a new .txt file) and run:  python manage.py seed_content
Nothing here is edited by hand in code. Rows that already exist are left alone, so anything
you changed in the panel is never overwritten.

Formula line:  subject|grade code|Title|LaTeX|Short explanation|variables|access|difficulty|other subjects
  subject       code from subjects.txt (M, P, C...)
  grade code    code from grades.txt (S9 = Class 9, U = Undergraduate, P, R...)
  variables     symbol~name~unit;symbol~name~unit   (optional)
  access        basic or premium (optional; default comes from the grade)
  difficulty    beginner, intermediate or advanced (optional; default comes from the grade)
  other subjects  comma separated subject codes for a formula that belongs to more than one subject (optional)
Do not use the | character inside LaTeX (write \mid, \lvert or \rvert instead).
"""
import re
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from taxonomy.models import AcademicLevel, Subject, Topic
from taxonomy.seeding import data_dir, grade_codes, read_rows, subject_codes
from .models import CodeSnippet, Example, Formula, FormulaVariable, Status


def formula_files(folder=None):
    return sorted((data_dir(folder) / "formulas").glob("*.txt"))


def parse_formulas(folder=None):
    """[(file, line, dict)] for every formula line. No database needed."""
    out = []
    for f in formula_files(folder):
        for n, p in read_rows(f, 5):
            vars_ = p[5] if len(p) > 5 else ""
            out.append((f.name, n, {
                "subject": p[0], "grade": p[1], "title": p[2], "latex": p[3], "short": p[4], "vars": vars_,
                "tier": p[6] if len(p) > 6 else "", "difficulty": p[7] if len(p) > 7 else "",
                "others": [x for x in (p[8].split(",") if len(p) > 8 else []) if x.strip()]}))
    return out


def parse_topics(folder=None):
    out = []
    for f in sorted(data_dir(folder).glob("topics*.txt")):
        for n, p in read_rows(f, 3):
            out.append((f.name, n, {"subject": p[0], "name": p[1], "titles": [t for t in p[2].split(";") if t]}))
    return out


def parse_snippets(folder=None):
    """[(file, subject code, [block dicts])]"""
    out = []
    for f in sorted(data_dir(folder).glob("*snippets*.txt")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r"^@subject\s+(\S+)", text, flags=re.M)
        code = m.group(1) if m else "CS"
        blocks = []
        for block in re.split(r"^@@ ", text, flags=re.M)[1:]:
            head, _, rest = block.partition("\n")
            tname, title, lang, tier, expl = [x.strip() for x in head.split("|")]
            code_text, _, out_text = rest.partition("\n##\n")
            blocks.append({"topic": tname, "title": title, "lang": lang, "tier": tier, "expl": expl,
                           "code": code_text.strip("\n"), "out": out_text.strip()})
        out.append((f.name, code, blocks))
    return out


def check(folder=None):
    """Problems in the data files, as readable lines. Empty list = all good. Needs no database."""
    problems = []
    subjects, grades = subject_codes(folder), grade_codes(folder)
    titles, slugs = {}, {}
    for fname, n, f in parse_formulas(folder):
        where = f"{fname} line {n}"
        if f["subject"] not in subjects:
            problems.append(f"{where}: unknown subject code '{f['subject']}'")
        for o in f["others"]:
            if o.strip() not in subjects:
                problems.append(f"{where}: unknown extra subject code '{o}'")
        if f["grade"] not in grades:
            problems.append(f"{where}: unknown grade code '{f['grade']}'")
        if f["tier"] not in ("", "basic", "premium"):
            problems.append(f"{where}: access must be basic or premium, not '{f['tier']}'")
        if f["difficulty"] not in ("", "beginner", "intermediate", "advanced"):
            problems.append(f"{where}: difficulty must be beginner, intermediate or advanced, not '{f['difficulty']}'")
        if f["title"] in titles:
            problems.append(f"{where}: title '{f['title']}' is already used at {titles[f['title']]}")
        titles.setdefault(f["title"], where)
        s = slugify(f["title"])
        if s in slugs and slugs[s] != f["title"]:
            problems.append(f"{where}: '{f['title']}' makes the same web address as '{slugs[s]}'")
        slugs.setdefault(s, f["title"])
        if not f["latex"] or not f["short"]:
            problems.append(f"{where}: LaTeX and short explanation are required")
        for v in [x for x in f["vars"].split(";") if x]:
            if not v.split("~")[0]:
                problems.append(f"{where}: a variable has no symbol")
    for fname, n, t in parse_topics(folder):
        where = f"{fname} line {n}"
        if t["subject"] not in subjects:
            problems.append(f"{where}: unknown subject code '{t['subject']}'")
        for title in t["titles"]:
            if title not in titles:
                problems.append(f"{where}: topic '{t['name']}' lists '{title}', which is not a formula title")
    for fname, code, blocks in parse_snippets(folder):
        if code not in subjects:
            problems.append(f"{fname}: unknown subject code '{code}'")
    topic_keys = {(t["subject"], t["name"]) for _, _, t in parse_topics(folder)}
    for fname, code, blocks in parse_snippets(folder):
        topic_keys |= {(code, b["topic"]) for b in blocks}
    problems += check_explanations(folder, set(titles), topic_keys)
    return problems


def _subject(code, subjects):
    s = subjects[code]
    return Subject.objects.get(slug=slugify(s["name"]))


def load_formulas(folder=None, draft=False):
    """Create the formulas that are missing. Returns the number added."""
    subjects, grades = subject_codes(folder), grade_codes(folder)
    user = get_user_model().objects.filter(is_superuser=True).first()
    levels = {l.slug: l for l in AcademicLevel.objects.all()}
    added = 0
    for _, _, f in parse_formulas(folder):
        g = grades[f["grade"]]
        sub = _subject(f["subject"], subjects)
        slug = slugify(f["title"])
        obj, new = Formula.objects.get_or_create(slug=slug, defaults=dict(
            title=f["title"], latex=f["latex"], short_explanation=f["short"],
            keywords=f"{f['title'].lower()}, {subjects[f['subject']]['name'].lower()}",
            is_demo=True, created_by=user, min_class=g["number"],
            access_tier=f["tier"] or g["tier"], difficulty=f["difficulty"] or g["difficulty"],
            status=Status.DRAFT if draft else Status.PUBLISHED, published_at=None if draft else timezone.now()))
        if not new:
            continue
        added += 1
        obj.subjects.add(sub, *[_subject(o.strip(), subjects) for o in f["others"]])
        obj.levels.add(levels[g["level"]])
        for i, v in enumerate(x for x in f["vars"].split(";") if x):
            bits = v.split("~")
            FormulaVariable.objects.create(
                formula=obj, symbol=bits[0], name=bits[1] if len(bits) > 1 else bits[0],
                unit=bits[2] if len(bits) > 2 and "constraint" not in bits[1].lower() else "", sort_order=i)
    return added


def _topic(subject, name, order):
    return Topic.objects.get_or_create(subject=subject, slug=slugify(name), defaults={"name": name, "sort_order": order})[0]


def load_topics(folder=None):
    """Create topics and link formulas to them. Returns (links made, titles not found)."""
    subjects = subject_codes(folder)
    linked, missing = 0, []
    for i, (_, _, t) in enumerate(parse_topics(folder)):
        topic = _topic(_subject(t["subject"], subjects), t["name"], i)
        for title in t["titles"]:
            f = Formula.objects.filter(title=title).first()
            if f is None:
                missing.append(title)
            elif not f.topics.filter(pk=topic.pk).exists():
                f.topics.add(topic)
                linked += 1
    return linked, missing


def load_snippets(folder=None):
    subjects, count, n = subject_codes(folder), 0, 0
    for _, code, blocks in parse_snippets(folder):
        subject = _subject(code, subjects)
        for b in blocks:
            body = b["code"]
            if b["lang"] == "java" and "class " not in body:
                inner = "\n".join("        " + l for l in body.splitlines())
                body = ("public class Main {\n    public static void main(String[] args) throws Exception {\n"
                        + inner + "\n    }\n}")
            CodeSnippet.objects.update_or_create(
                topic=_topic(subject, b["topic"], n), title=b["title"], language=b["lang"],
                defaults=dict(code=body, expected_output=b["out"], explanation=b["expl"],
                              is_premium=(b["tier"] == "p"), sort_order=n))
            count += 1
            n += 1
    return count


def parse_explanations(folder=None):
    """[(file, line, dict)] from explanations*.txt. Each block is  @@ formula|Title  or  @@ topic|CODE|Name,
    then paragraphs, then optional  ## example|Title|Problem|Solution (steps split by //)|Result|Units  lines."""
    out = []
    for f in sorted(data_dir(folder).glob("explanations*.txt")):
        kind, head, body, examples, start = None, None, [], [], 0
        def flush():
            if kind:
                text = "\n".join(body).strip()
                out.append((f.name, start, {"kind": kind, "head": head, "text": text, "examples": list(examples)}))
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("@@ "):
                flush()
                parts = [x.strip() for x in line[3:].split("|")]
                kind, head, body, examples, start = parts[0], parts[1:], [], [], n
            elif kind and line.startswith("## example|"):
                p = [x.strip() for x in line[len("## example|"):].split("|")]
                examples.append({"title": p[0], "problem": p[1] if len(p) > 1 else "",
                                 "solution": "\n".join(x.strip() for x in p[2].split("//")) if len(p) > 2 else "",
                                 "result": p[3] if len(p) > 3 else "", "units": p[4] if len(p) > 4 else ""})
            elif kind and not line.startswith("#"):
                body.append(line)
        flush()
    return out


def check_explanations(folder, titles, topic_keys):
    problems = []
    subjects = subject_codes(folder)
    for fname, n, e in parse_explanations(folder):
        where = f"{fname} line {n}"
        if e["kind"] == "formula":
            if e["head"][0] not in titles:
                problems.append(f"{where}: explanation for '{e['head'][0]}', which is not a formula title")
        elif e["kind"] == "topic":
            if len(e["head"]) < 2 or e["head"][0] not in subjects:
                problems.append(f"{where}: topic explanation needs a known subject code and a name")
            elif (e["head"][0], e["head"][1]) not in topic_keys:
                problems.append(f"{where}: topic '{e['head'][1]}' does not exist for subject {e['head'][0]}")
        else:
            problems.append(f"{where}: block must start with 'formula' or 'topic'")
        if not e["text"]:
            problems.append(f"{where}: no explanation text")
    return problems


def load_explanations(folder=None):
    """Fill empty explanations only. Returns (formulas, topics, examples) counts."""
    subjects, nf, nt, ne = subject_codes(folder), 0, 0, 0
    for _, _, e in parse_explanations(folder):
        if e["kind"] == "formula":
            f = Formula.objects.filter(title=e["head"][0]).first()
            if f is None:
                continue
            if not f.detailed_explanation:
                f.detailed_explanation = e["text"]
                f.save(update_fields=["detailed_explanation"])
                nf += 1
            for x in e["examples"]:
                if not f.examples.filter(title=x["title"]).exists():
                    Example.objects.create(formula=f, title=x["title"], problem=x["problem"], solution=x["solution"],
                                           result=x["result"], units=x["units"],
                                           difficulty=f.difficulty if f.difficulty in ("beginner", "intermediate", "advanced") else "beginner")
                    ne += 1
        elif e["kind"] == "topic":
            sub = Subject.objects.filter(slug=slugify(subjects[e["head"][0]]["name"])).first()
            t = Topic.objects.filter(subject=sub, slug=slugify(e["head"][1])).first() if sub else None
            if t and not t.explanation:
                t.explanation = e["text"]
                t.save(update_fields=["explanation"])
                nt += 1
    return nf, nt, ne
