# DarijaDoc interface

Patient-facing health literacy, designed for Moroccan French and Darija readers. Four destinations: understand a document, organize a confirmed prescription, ask questions, inspect prototype evaluation.

## Direction

Trust comes from legible instructions, visible uncertainty, predictable controls, and honest state. Keep clinical urgency visually separate. No invented patient testimonials, certifications, statistics, or accuracy scores.

The user-supplied white/green/blue system is defined in `src/tokens.css` and used by both routes. Core colors: green `#2E9E5B`, blue `#2E6FA8`, navy `#0A2540`, white `#FFFFFF`, off-white `#F7FAFC`. Inter and Noto Naskh Arabic are self-hosted. The full semantic, spacing, radius, type, transition and z-index tokens are preserved. Primary buttons use the supplied green-700 shade for readable white text; green-500 remains the brand token.

The logo is adapted from the user's `logo.html`: the original green-to-blue organic shape and white cross replace the previous icon in shared branding and the favicon. The landing's closing logo morphs and breathes; app navigation uses its static version. All animation respects reduced motion, and the landing also offers a pause control.

Desktop: compact persistent navigation, document workspace plus contextual guidance. Mobile: four-item bottom navigation, single-column content. RTL uses logical CSS properties. The Arabic welcome typography is the expressive focal point; the forms remain conventional.

```text
Navigation | Page title and steps
           | Document / upload       | Darija audio introduction
           | Preview                 | Explanation after analysis
           |                         | Confirmed next steps
```

Design review: the app retains its document-first flow and reviewed schedule. The public landing at `/` explains the product; the workspace is at `/app`. No invented trust badges, testimonials, usage figures, or clinical scores. Taste guides the public landing; frontend-design guides the application.

## Landing page

Design read: a Moroccan patient-facing service with an approachable, trustworthy white/green/blue identity. Taste dials: variance 4, motion 3, density 4. These intentionally override its higher-motion marketing default.

```text
Logo / navigation / language / open app
Value proposition + actions  | Illustrative family photograph
Document / audio / calendar capability strip
Interactive workflow steps | Live synthetic demo component
Darija audio feature       | Follow-up and schedule feature
Clinical limits and link to evaluation
Frequently asked questions
Animated supplied logo / final app action
```

The hero is editorial photography, not a fake app screenshot. The walkthrough is an actual interactive component using shared demo data, speech playback, and calendar export. Motion is limited to initial entrance, section reveals, workflow transitions, and the supplied animated logo. The family photograph is explicitly identified as generated illustrative imagery in the footer. See `ASSETS.md` for its prompt and provenance.

The landing and app are lazy-loaded without adding a routing library. Production hosting must rewrite `/app` and other non-file paths to `index.html`. Query parameters `lang=ary`, `demo=1`, and `tab=accuracy` support the landing entry points.

## State and boundaries

React state only. Uploaded file and chat stay available across tabs. Refresh clears the session. No localStorage of health data. A synthetic prescription is available via “Essayer”; its result and chat are visibly labeled as demonstrations. Real uploads always call the backend and surface failures.

Treatment data must be reviewed. Missing dose, time, and duration are never inferred by the frontend. Calendar export uses floating local times and explicit count-limited daily recurrence. Calendar notifications are controlled by the calendar app, and exports do not synchronize.
