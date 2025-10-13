## InnerBhakti Video Generation Automation

This project aims to automate the production pipeline that takes a written script and delivers ready-to-use assets generated with HeyGen:

- A primary video (or audio track) with the correct HeyGen avatar voice.
- Supporting b-roll clips tailored to the script theme.
- Organized exports to a designated Google Drive folder for sharing.

### What Exists Today
- Early scaffolding for API routing and configuration under `src/`.
- Prompt templates and configuration placeholders to shape the final workflow.

### What We Are Building Next
- Accept a script as input via an API or CLI entry point.
- Call HeyGen programmatically to produce the main visual asset with the voice coming from eleven labs.
- Generate or source b-roll clips aligned with key beats in the script.
- Upload each output (voice asset and b-roll set) as separate files to Google Drive.

### Status & Notes
- The automation is in active development and details will evolve.
- Documentation will be updated as components solidify.
- Feedback and ideas are welcome—expect changes as requirements firm up.
