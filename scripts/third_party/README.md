# Upstream renderer attribution

These widgets retain the original Merko appearance while the local Python collector supplies their data. No upstream server is called when rendering or viewing them.

- `templates/streak.svg` is adapted from [`src/card.php`](https://github.com/DenverCoder1/github-readme-streak-stats/blob/9202e37665889fdb42d9a7df8501c1800acf761d/src/card.php) and the Merko values in `src/themes.php`, at commit `9202e37665889fdb42d9a7df8501c1800acf761d`. Its dimensions, column offsets, ring mask, fire path, colors, typography, date format, and entrance animations follow the original README parameters. See `streak-stats-LICENSE.txt`.
- The line graph in `merko.py` adapts the default layout and Merko CSS from [`src/GraphCards.ts`](https://github.com/Ashutosh00710/github-readme-activity-graph/blob/0962e9461de815933d462e8b98c7ce566cada8fb/src/GraphCards.ts), `src/svgs.ts`, and `src/styles/` at commit `0962e9461de815933d462e8b98c7ce566cada8fb`. See `activity-graph-LICENSE.txt`.
- Its monotone cubic interpolation and integer scale calculation are adapted from [Chartist 0.11.4](https://github.com/chartist-js/chartist/tree/v0.11.4), the engine used by the original graph's `node-chartist` dependency. See `chartist-LICENSE.txt`.

The static Python port emits SVG text instead of a `foreignObject` for the graph heading. Its default animation styles remain visible in renderers that do not support animation, and it honors reduced-motion preferences. Refresh timestamps are in SVG descriptions and the JSON report so they do not change the original visible layout. Font rasterization can vary between platforms.

The corresponding MIT notices are included in the generated SVGs as comments.
