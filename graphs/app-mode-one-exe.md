# App mode one exe

Date: 2026-11-12, 23:28 EST
Status: decided, not built yet

## Problem
The dashboard at 127.0.0.1:8000 is a dev prototype in a browser. A consumer will not run a proxy, then an API, then a browser.

## Intention
One exe, double click, proxy plus API start inside Iris, dashboard embedded in the Iris window, not in a browser, not a separate proxy launch.

## Options
Browser dashboard. Separate proxy launch plus browser. One exe with an embedded dashboard.

## Choice
One exe. Iris.exe, launcher iris-launcher.exe, as Muse Code names it. Icon iris.ico. Splash Iris.

## Rejected
Browser dashboard for consumers. That is a dev prototype, not a product.
A .bat for normal use. No .bat for normal use. Consumer launch is a desktop shortcut to Iris.exe.
Dev tools in the consumer app. Test button, diagnostics, dev tools are not in the final consumer app. They are removed before push, or kept in a separate dev only file or panel, never in the consumer dashboard.

## Links
Dashboard at 127.0.0.1:8000 is the prototype for the embedded pane. It has priced cost, Runs, trace IDs, blocked and rate limited. It has no red button, no pause one Run, no redirect. Kill switch is proven, but it is a terminal command, not a GUI button. Demo recording is parked until Steer buttons are built.
