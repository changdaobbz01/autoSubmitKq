# Releases

This folder stores distributable packages that are safe to share with other computers.

- `AttendanceRebuild-portable.zip` is a clean portable package
- `AttendanceTokenCollector-portable.zip` is a clean desktop Token collection client
- It must not contain `.attendance_auth/`
- It must not contain imported xlsx account data, cached token files, local polling state, cloud API keys, or notification settings
- After extraction on another machine, import that machine's own xlsx before using real submit or polling
