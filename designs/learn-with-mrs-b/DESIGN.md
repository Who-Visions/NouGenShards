---
name: "learn-with-mrs-b"
version: "0.1.0"
description: "One look for learnwithmrsb.com and the Board + Zoom desktop app: calm, warm, trustworthy one-to-one tutoring for families in Palm Beach County, and a quiet working tool for the tutor. A light site with one brand blue and a navy back office; the app's bar follows the Windows light or dark setting."
colors: {"--accent": "#0C7FAC", "--accent-on-navy": "#38BDF8", "--accent-soft": "#E6F3F8", "--accent-strong": "#0A6B92", "--bad": "#DC2626", "--bg": "#F8FAFC", "--border": "#E2E8F0", "--border-strong": "#64748B", "--celebrate": "#FFC72C", "--control-ink": "#FFFFFF", "--disabled": "#64748B", "--focus": "#0C7FAC", "--good": "#15803D", "--muted": "#475569", "--navy": "#0F172A", "--navy-raised": "#1E293B", "--on-celebrate": "#0F172A", "--on-navy": "#E2E8F0", "--raised": "#F1F5F9", "--surface": "#FFFFFF", "--text": "#0F172A", "--warn": "#B45309"}
---

# learn-with-mrs-b

## referenceWorld

A clean, well-kept classroom and a teacher's planner, not a startup dashboard. Serif headings carry the personal, teacherly voice (Playfair Display); a plain sans carries everything people click or read at length (Roboto). The tutor's working area is marked by a navy navigation frame so she always knows she is in the back office.

## antiPatterns

Reject gradients or blur behind text, glow, giant pill radii on controls, brand blue as a page background, more than one primary button in a view, colour-only status, a third typeface, and any back-office page that breaks at the 600 to 820px width of the app's left pane. Gold is for celebration only and is never a button.

## materiality

Flat and opaque. Cards sit on a near-white canvas with a 1px hairline and at most a soft 1px shadow; only dialogs and menus float. Navigation is solid navy with a raised navy for the active item. Corners: 8px for navigation items and chips, 12px for buttons and inputs on the site and in the app bar alike, 16px for cards and dialogs.

## density

Comfortable for families, compact enough for the tutor's pane: spacing steps 4, 8, 16, 24, 32px; cards pad 24px (16px under 640px); touch targets at least 44px tall; forms cap at 440px and the content column at 1120px.

## motionGrammar

Short colour and background transitions on hover and selection only (140ms fast, 220ms base, ease-out). No looping animation, no motion on data. Everything is switched off under prefers-reduced-motion.

## interactionPhysics

Every interactive part has hover (brand strong, or canvas for quiet and secondary buttons), pressed (same as hover), disabled (canvas fill, disabled text, no pointer) and a 3px brand focus ring at 2px offset shown only for keyboard focus. The app's views (Board, Both, Zoom) are one segmented control; Zoom can dock to a 48px navy rail on the right and the board fills the room. Start meeting and Start my next class always open Zoom as host.

## informationHierarchy

Back office: navy navigation, a 56px top bar with one eyebrow line and the signed-in account, then the page: a serif greeting, a muted date line, one primary action, compact stat cards, and cards for today's sessions, new families and what students found tricky. Desktop app: one bar of controls (paste link, views, board width, save board, answer keys, reloads, Zoom dock, status), the site on the left and Zoom on the right.

## responsiveBehavior

Under 640px: phone layout with a top bar and a slide-in menu. 640 to 1279px (tablets and the app's left pane): a 72px navy icon rail with tooltips and an unread dot. 1280px and up: a 256px navy sidebar with section labels. The public header switches to the compact menu under 1024px. Below 1500px the app bar's secondary buttons go icon only and keep their names as tooltips and accessible labels.

## Accessibility

Body and muted text meet 4.5:1 on their surfaces, status words meet 4.5:1 on the light and dark bars, focus rings and icons meet 3:1. The active icon in the navy navigation uses a lighter blue because brand blue is too dark on navy; text on brand soft uses brand strong. Every colour-coded status is paired with a word. Inputs are 16px so phones do not zoom. Respect reduced motion and forced colours.

## brandVoice

Plain, warm and direct, written for parents and a busy teacher. The same words mean the same thing on the site and in the app: Start meeting, Start my next class, Paste Zoom link, Board, Both, Zoom, Save board, Answer keys, Sign in. Empty states say what to do next in one sentence and offer one button that does it.

## iconography

Lucide line icons (ISC licence) at one stroke weight, 16 to 20px, in currentColor. Icons with a meaning people might not guess are paired with text; icon-only buttons always have a tooltip and an accessible name.

## dataViz

Few charts: monthly sessions and practice counts in the family portal. Bars use brand, navy-raised and gold on the canvas, with labelled axes and values shown as text; no colour carries meaning on its own.

## stateGrammar

Per component: default, hover, focus, pressed, disabled, loading (quiet skeleton cards), empty (one sentence plus one button), error (plain sentence in danger with a way back), live (green dot plus In class), waiting (taskbar progress in the app). Status words read In class, Check the link, Cancel session.

## provenance

Observed from the learnwithmrsb repo on 2026-11-12: brand #0C7FAC and its hover #0A6B92 (the most used colours in src), navy #0F172A sidebar, Playfair Display and Roboto from src/app/layout.tsx, 12px and 16px radii as the most used Tailwind radii, and the app bar in desktop/zoom-board-shell/bar.html. Written first as DESIGN.md (google-labs-code/design.md, lint 0 errors) at the repo root and loaded into Google Stitch as project 6019807897591723314, design system asset 9c267e5c5e724c3490af3a80e21b21d8. Lighter navy accent, disabled grey and the dark-bar status colours were chosen to pass contrast checks.
