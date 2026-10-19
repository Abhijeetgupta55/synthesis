# HUMAN_TODO

Tasks Claude Code cannot do itself (account actions, pushing, publishing, hardware, course-policy decisions).
Each item has exact steps. Remove an item once it is done.

## Open

1. **Keep the machine awake during long jobs.** The Phase 1 feature-store build and Phase 3 tuning run for hours.
   On Windows: Settings → System → Power → "When plugged in, put my device to sleep after" → **Never**, while jobs run.
   (Jobs are resumable per project, so an interruption costs only the unfinished project.)
2. **Free RAM if possible.** Only about 2 GB of 16 GB is free. Closing browsers and IDE windows during the feature
   build and model training makes them faster. Nothing breaks if you don't.
