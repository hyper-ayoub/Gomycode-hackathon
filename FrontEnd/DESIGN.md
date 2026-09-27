# DarijaDoc interface

Patient-facing health literacy, designed for Moroccan French and Darija readers. Four destinations: understand a document, organize a confirmed prescription, ask questions, inspect prototype evaluation.

## Direction

Trust comes from legible instructions, visible uncertainty, predictable controls, and honest state. Keep clinical urgency visually separate. No invented patient testimonials, certifications, statistics, or accuracy scores.

Palette: action teal `#167361`, deep text `#223A35`, canvas `#F7F9F8`, white surfaces `#FFFFFF`, soft sage `#EAF1E5`, muted text `#64736E`. DM Sans for French and Noto Sans Arabic for Darija, self-hosted. Radius scale: 6px fields, 10px nested surfaces, 16px panels. Limited state-driven motion; reduced motion supported.

Desktop: compact persistent navigation, document workspace plus contextual guidance. Mobile: four-item bottom navigation, single-column content. RTL uses logical CSS properties. The Arabic welcome typography is the expressive focal point; the forms remain conventional.

```text
Navigation | Page title and steps
           | Document / upload       | Darija audio introduction
           | Preview                 | Explanation after analysis
           |                         | Confirmed next steps
```

Design review: avoided a marketing hero, decorative gradients, equal feature-card grids, fake trust badges, and invented scores. The upload surface is the primary action, and the schedule requires explicit review. Taste's landing-page constraints are not applied to the product dashboard; frontend-design guides the application.

## State and boundaries

React state only. Uploaded file and chat stay available across tabs. Refresh clears the session. No localStorage of health data. A synthetic prescription is available via “Essayer”; its result and chat are visibly labeled as demonstrations. Real uploads always call the backend and surface failures.

Treatment data must be reviewed. Missing dose, time, and duration are never inferred by the frontend. Calendar export uses floating local times and explicit count-limited daily recurrence. Calendar notifications are controlled by the calendar app, and exports do not synchronize.
