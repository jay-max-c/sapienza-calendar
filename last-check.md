# Sapienza calendar source check

- Lessons-plan courses found: 4/4
- Timetable courses with parseable times: 0/4
- Safe to regenerate ICS automatically: **NO**

## Fetch warnings
- https://www.architettura.uniroma1.it/en/orario: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)>

## Safety stop
The official timetable source did not expose a complete machine-readable timetable.
The existing ICS was left untouched. This prevents a website redesign or partial page from deleting/corrupting classes.

Detected schedule data:
```json
{}
```
