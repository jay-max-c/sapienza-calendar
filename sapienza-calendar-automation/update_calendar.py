#!/usr/bin/env python3
"""
Sapienza Architecture (Conservation) 33430 calendar updater.

Design:
- Lessons Plan is the authority for which modules belong to Year 1 / Semester 1.
- Faculty timetable sources are checked for schedule changes.
- overrides.json is the manual layer for professor emails / Meet links / special start dates.
- Existing ICS is NEVER overwritten unless a complete, validated timetable can be extracted.
"""

from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OVERRIDES = json.loads((ROOT / "overrides.json").read_text(encoding="utf-8"))
STATE = ROOT / "source-state.json"
REPORT = ROOT / "last-check.md"
ICS = ROOT / CONFIG["output_file"]

UA = "Mozilla/5.0 (Sapienza calendar updater; GitHub Actions)"

def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def clean_html(html: str) -> str:
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = html.replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", html).strip()

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def expected_courses_from_lessons_plan(text: str):
    wanted = {}
    # Course codes are stable and are safer than fuzzy title-only matching.
    for code, title in CONFIG["courses"].items():
        if code in text and title.upper() in text.upper():
            wanted[code] = title
    return wanted

def find_schedule_candidates(text: str):
    """
    Generic conservative extractor. It only returns records when a course title/code
    occurs near an explicit weekday + HH:MM-HH:MM pattern. If the faculty site changes
    markup and extraction is incomplete, updater refuses to overwrite the ICS.
    """
    weekdays = {
        "MONDAY":"MO","MON":"MO","LUNEDÌ":"MO","LUNEDI":"MO",
        "TUESDAY":"TU","TUE":"TU","MARTEDÌ":"TU","MARTEDI":"TU",
        "WEDNESDAY":"WE","WED":"WE","MERCOLEDÌ":"WE","MERCOLEDI":"WE",
        "THURSDAY":"TH","THU":"TH","GIOVEDÌ":"TH","GIOVEDI":"TH",
        "FRIDAY":"FR","FRI":"FR","VENERDÌ":"FR","VENERDI":"FR",
    }
    out = {}
    upper = text.upper()
    for code, title in CONFIG["courses"].items():
        anchors = [m.start() for m in re.finditer(re.escape(code), upper)]
        anchors += [m.start() for m in re.finditer(re.escape(title.upper()), upper)]
        records = []
        for pos in anchors:
            window = upper[max(0,pos-350):pos+900]
            for wd, byday in weekdays.items():
                for m in re.finditer(rf"\b{re.escape(wd)}\b.{0,180}?(\d{{1,2}}[:.]\d{{2}})\s*(?:-|–|—|TO)\s*(\d{{1,2}}[:.]\d{{2}})", window):
                    start = m.group(1).replace(".",":").zfill(5)
                    end = m.group(2).replace(".",":").zfill(5)
                    rec = {"byday":byday,"start":start,"end":end}
                    if rec not in records:
                        records.append(rec)
        if records:
            out[code] = records
    return out

def ics_escape(s):
    return str(s).replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace("\n","\\n")

def render_ics(schedule):
    from datetime import datetime, timedelta
    cal = [
        "BEGIN:VCALENDAR","VERSION:2.0",
        "PRODID:-//jay-max-c//Sapienza 33430 Calendar//EN",
        "CALSCALE:GREGORIAN","METHOD:PUBLISH",
        "X-WR-CALNAME:Sapienza 33430 - Y1 S1",
        "X-WR-TIMEZONE:Europe/Rome",
    ]
    weekday_idx={"MO":0,"TU":1,"WE":2,"TH":3,"FR":4}
    semester_start=datetime.strptime(CONFIG["semester_start"],"%Y-%m-%d")
    semester_end=CONFIG["semester_end"].replace("-","")+"T225959Z"

    for code, records in schedule.items():
        meta=OVERRIDES.get(code,{})
        title=CONFIG["courses"][code]
        if meta.get("disabled"): continue
        course_start=datetime.strptime(meta.get("start_date",CONFIG["semester_start"]),"%Y-%m-%d")
        for i,r in enumerate(records):
            delta=(weekday_idx[r["byday"]]-course_start.weekday())%7
            first=course_start+timedelta(days=delta)
            st=first.strftime("%Y%m%d")+"T"+r["start"].replace(":","")+"00"
            en=first.strftime("%Y%m%d")+"T"+r["end"].replace(":","")+"00"
            location=meta.get("location_by_day",{}).get(r["byday"], meta.get("location",""))
            desc=[]
            if meta.get("professor"): desc.append(meta["professor"])
            if meta.get("meet"): desc.append("Google Meet: "+meta["meet"])
            if meta.get("note"): desc.append(meta["note"])
            cal += [
                "BEGIN:VEVENT",
                f"UID:{code}-{r['byday']}-{i}@sapienza-calendar",
                f"SUMMARY:{ics_escape(title)}",
                f"DTSTART;TZID=Europe/Rome:{st}",
                f"DTEND;TZID=Europe/Rome:{en}",
                f"RRULE:FREQ=WEEKLY;BYDAY={r['byday']};UNTIL={semester_end}",
            ]
            if location: cal.append("LOCATION:"+ics_escape(location))
            if desc: cal.append("DESCRIPTION:"+ics_escape("\n".join(desc)))
            for minutes in CONFIG["alerts_minutes"]:
                cal += ["BEGIN:VALARM",f"TRIGGER:-PT{minutes}M","ACTION:DISPLAY",
                        f"DESCRIPTION:Class starts in {minutes} minutes","END:VALARM"]
            cal.append("END:VEVENT")
    cal.append("END:VCALENDAR")
    return "\r\n".join(cal)+"\r\n"

def main():
    lessons_html=fetch(CONFIG["lessons_plan_url"])
    lessons=clean_html(lessons_html)
    expected=expected_courses_from_lessons_plan(lessons)

    faculty_pages=[]
    errors=[]
    for url in CONFIG["timetable_urls"]:
        try:
            raw=fetch(url); faculty_pages.append((url,clean_html(raw),sha(raw)))
        except Exception as e:
            errors.append(f"{url}: {e}")

    combined=" ".join(x[1] for x in faculty_pages)
    schedule=find_schedule_candidates(combined)

    complete=set(schedule)==set(CONFIG["courses"])
    report=[
        "# Sapienza calendar source check","",
        f"- Lessons-plan courses found: {len(expected)}/{len(CONFIG['courses'])}",
        f"- Timetable courses with parseable times: {len(schedule)}/{len(CONFIG['courses'])}",
        f"- Safe to regenerate ICS automatically: **{'YES' if complete else 'NO'}**","",
    ]
    if errors:
        report += ["## Fetch warnings"]+[f"- {x}" for x in errors]+[""]
    if not complete:
        report += [
            "## Safety stop",
            "The official timetable source did not expose a complete machine-readable timetable.",
            "The existing ICS was left untouched. This prevents a website redesign or partial page from deleting/corrupting classes.",
            "",
            "Detected schedule data:",
            "```json",json.dumps(schedule,indent=2,ensure_ascii=False),"```"
        ]
    else:
        new=render_ics(schedule)
        if not ICS.exists() or ICS.read_text(encoding="utf-8") != new:
            ICS.write_text(new,encoding="utf-8",newline="")
            report += ["## Result","Validated timetable change detected; ICS regenerated."]
        else:
            report += ["## Result","No timetable change detected."]

    state={
        "lessons_plan_sha256":sha(lessons_html),
        "faculty_sources":[{"url":u,"sha256":h} for u,_,h in faculty_pages],
        "courses_found":expected,
        "schedule_found":schedule,
    }
    STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    REPORT.write_text("\n".join(report)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
