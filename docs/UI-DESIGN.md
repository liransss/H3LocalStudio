# H3 Local Studio interface

## Direction

A local editing suite: the preview is a screening room, the composer is a working instrument, and local hardware status stays visible without competing with creative work. Original H3 branding; no Magnific assets or remote services.

## Tokens

- Ink `#101113`: workspace background.
- Graphite `#18191d`: working surfaces.
- Slate `#24252b`: elevated controls.
- Chalk `#eeece6`: primary text and generation action.
- Iris `#b9acf3`: selected controls and progress.
- Mist `#a3a4ae`: secondary text.
- Typography: Bahnschrift for display and navigation, Segoe UI Variable for readable Windows controls. System fallbacks; no network font dependency.
- Spacing: 4 / 8 / 12 / 16 / 24 / 32 px. Distinct surface, control, and media radii.

## Layout

Left-aligned navigation and controls, with the preview occupying the largest uninterrupted surface.

```text
Navigation | Page title / local status
           | Composer          | Preview / playback
           | Reference media   | Output summary
           | Settings          | Recent creations
           | Generate          |
```

On narrow screens, the composer, settings, and preview stack with usable touch targets. The sidebar becomes a labeled horizontal navigation on phones.

## Review against brief

The initial acid-accent dashboard direction was too close to the existing UI. Replaced it with neutral graphite, chalk actions, and quiet iris selection states. Spend visual emphasis on the video surface and prompt, not decorative gradients. Keep real model, project, reference, job, and variant data; never present sample imagery as generated output.

## Functional boundaries

Home, Create, Spaces, Projects, History, Models, and Settings remain reachable. App owns navigation, projects, active jobs, variant operations, and result dialogs. Create retains the GenerationRequest payload, automatic input routing, reference roles/order, quality and advanced settings. ReferenceMediaSection uses existing upload/library endpoints. Job updates retain WebSocket/polling. ResultPanel retains variant availability, output actions, metadata and workflow links. Spaces retains its React Flow graph and execution controls. No inference, backend, API contract, model management, or Tauri permission changes are part of this redesign.
