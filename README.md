# Sapienza calendar automation

Checks official Sapienza sources every 6 hours.

- `lessons-plan` determines the course list.
- Faculty/course timetable pages are checked for machine-readable timetable changes.
- `overrides.json` is the manual layer for professor emails, Meet links and special start dates.
- The script has a safety stop: it does **not** overwrite `Y1S12026.ics` unless all four courses have a complete parseable timetable.

## Manual Email updates

Edit `overrides.json` and commit. Professor information takes priority over scraped website data.

## iPhone subscription

Subscribe to the raw `Y1S12026.ics` URL in Apple Calendar. The URL remains unchanged when GitHub Actions updates the file.
