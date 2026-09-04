# site/

Marketing assets for OurNook that don't belong in the app bundle.

- `landing.html` — the OurNook marketing landing page. Self-contained,
  single file, no build step. Originally from `/Users/amre/Projects/ournook/`
  (the user's working copy). Deploy to GitHub Pages or a static host when
  ready to launch the public site.

The desktop app itself does NOT load this file — it has its own React-based
UI built from `src-ui/` and bundled into `dist/index.html` by Vite. The two
share the same brand but are otherwise independent surfaces.
