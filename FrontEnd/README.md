# DarijaDoc

A French/Darija medical-document explanation interface built for the GOMYCODE hackathon.

## Run locally

From the repository root:

```sh
cd FrontEnd
npm install
npm run dev
```

Open the local Vite URL. `npm run build` checks TypeScript and builds production assets. `npm test` runs data validation and calendar-export tests.

## Included

- Responsive four-tab interface with French/Darija UI and RTL layout.
- Drag/drop image and PDF upload, preview, file validation, real FastAPI requests, error handling, and a clearly marked synthetic example.
- Structured explanations, uncertainty and emergency displays, browser speech playback when an appropriate voice is available.
- Reviewed treatment schedules, daily taken-status tracking, date navigation, private-title calendar export.
- Document-context chat, clearly labeled canned demo responses, and actual API integration.
- Accuracy report reader with no fabricated scores.

The UI is a prototype, not a clinical product. Medical explanations and emergency detection require the team's backend. Browser speech depends on installed voices; Arabic voices may not pronounce Darija naturally. Voice input is not included.

Data stays in React memory until refresh; real document analysis sends the file to the configured backend only when requested. Calendar export is an importable `.ics` snapshot, not account synchronization or guaranteed notifications. Use synthetic documents for demonstrations.

Copy `.env.example` to `.env` to configure the backend URL. See [BACKEND_CONTRACT.md](BACKEND_CONTRACT.md) for the proposed API/report shapes and [DESIGN.md](DESIGN.md) for UI decisions.
