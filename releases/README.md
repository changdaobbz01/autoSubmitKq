# Releases

This folder stores distributable packages that are safe to share with other computers.

- `AttendanceRebuild-portable.zip` is a clean portable package
- It must not contain `.attendance_auth/`
- It must not contain imported xlsx account data, cached token files, or local polling state
- After extraction on another machine, import that machine's own xlsx before using real submit or polling
