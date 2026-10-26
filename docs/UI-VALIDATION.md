# Premium studio UI validation

Branch: `codex/premium-studio-ui`.

The working tree contained existing application changes before this work. Those changes were retained. This UI pass changes App wiring, Layout, CreatePage, ReferenceMediaSection, ResultPanel, VideoCard, main.tsx, index.html, and adds studio.css and VideoComparison. No backend, API contract, inference, model management, GPU, or Tauri source was changed by this UI pass.

## Implemented

- Graphite, ivory and iris design system with offline Windows typography.
- Three-column desktop creation studio; two-column intermediate layout and stacked narrow layout.
- Large in-place original video preview, recent creation selection, and result access.
- Prompt character limit, Ctrl+Enter generation, accessible switches and selected controls.
- Sticky generation action with current output settings; live job progress and terminal actions.
- Reference drag feedback, local upload, role/order controls, and selection after partially successful uploads.
- Consistent navigation, galleries, model/settings surfaces and Spaces typography.
- Original/Upscaled comparison with a keyboard-operable divider and synchronized playback, using completed local variants.
- Keyboard-accessible gallery cards; result dialog Escape, focus trapping/restoration and clipboard feedback.
- New creation clears the draft; page navigation resets the workspace scroll.
- Reduced-motion support and visible focus states.

## Evidence

| Check | Result |
| --- | --- |
| TypeScript and production build | `npm.cmd run build` passed |
| Backend regression suite | 61 passed; one existing Starlette/httpx deprecation warning |
| Real local Mock Mode API | `/api/health` returned `mock_mode: true` |
| Generation flow | Prompt validation, settings payload, simulated progress, completion, MP4 loading passed |
| Persistence | Generated video found in History after browser refresh |
| Screens | Home, Create, Spaces, Projects, History, Models, Settings rendered without Vite overlays |
| Responsive Create | 1600, 1280, 768, 390 and 320px widths; no document overflow |
| Reference workflow | Actual PNG dropped through DataTransfer, uploaded locally, assigned an opening-frame role and removed |
| Comparison | Existing original and SeedVR2 videos loaded; playback drift under 0.03 seconds in sampled check; divider and seek tested |
| Keyboard | Modal Escape and focus cycling, draft reset, gallery native buttons |
| Console | Zero errors in final end-to-end and interaction runs |

The first browser run exposed favicon 404s. Adding the existing local SVG favicon resolved them. No models were downloaded, no GPU inference was triggered, and comparison used existing videos. Two short test generations and one reusable test reference were added to local app data during validation.

The native Tauri window and Windows packaging were not launched or rebuilt. Desktop-shell verification remains outside the browser evidence above. Spaces keeps a horizontally scrollable canvas workspace on narrow screens.

## Screenshots and repeatable checks

Screenshots and browser scripts are in [the review folder](../.artifacts/ui-review/). Browser scripts use `playwright-core` installed only in the ignored review-tool directory; application dependencies were not changed.

- [Create desktop](../.artifacts/ui-review/after-create-final.png)
- [Original/Upscaled comparison](../.artifacts/ui-review/after-comparison.png)
- [Create mobile](../.artifacts/ui-review/after-create-final-390.png)
- [History](../.artifacts/ui-review/after-history.png)
- [End-to-end results](../.artifacts/ui-review/results.json)
- [Interaction results](../.artifacts/ui-review/interaction-results.json)

A before screenshot was inspected in the session. The browser connector could not save screenshots to the configured workspace, so after screenshots were saved through a local headless Chrome session.

No changes were committed, merged, or deployed. Mock Mode development services are available at http://127.0.0.1:1420.
