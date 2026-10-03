/** Hand-drawn 24x24 outline icons (1.5 stroke, round caps). Data only, so it can be previewed outside React. */
export const ICON_PATHS = {
  /** Document with a pen: the redline / tracked-change mark. */
  docPen: [
    "M12.5 3.75H7.25A1.5 1.5 0 0 0 5.75 5.25v13.5a1.5 1.5 0 0 0 1.5 1.5h3.5",
    "M12.5 3.75 18.25 9.5v1.25",
    "M12.5 3.75V8a1.5 1.5 0 0 0 1.5 1.5h4.25",
    "M12.9 20.3l.55-2.35 5.7-5.7a1.15 1.15 0 0 1 1.62 0l.18.18a1.15 1.15 0 0 1 0 1.62l-5.7 5.7-2.35.55Z",
  ],
  eye: [
    "M2.75 12S6 5.75 12 5.75 21.25 12 21.25 12 18 18.25 12 18.25 2.75 12 2.75 12Z",
    "M12 9.25a2.75 2.75 0 1 0 0 5.5 2.75 2.75 0 1 0 0-5.5Z",
  ],
  docLines: [
    "M12.5 3.75H7.25a1.5 1.5 0 0 0-1.5 1.5v13.5a1.5 1.5 0 0 0 1.5 1.5h9.5a1.5 1.5 0 0 0 1.5-1.5V9.5Z",
    "M12.5 3.75V8a1.5 1.5 0 0 0 1.5 1.5h4.25",
    "M9 13.25h6",
    "M9 16.5h3.75",
  ],
  download: ["M12 4.25v10.5", "M7.5 10.5 12 15l4.5-4.5", "M4.75 19.25h14.5"],
  clock: ["M12 3.75a8.25 8.25 0 1 0 0 16.5 8.25 8.25 0 1 0 0-16.5Z", "M12 7.75V12l2.9 1.75"],
  shieldTick: [
    "M12 3.5 19 6.1v5.2c0 4.3-2.8 7.4-7 9.2-4.2-1.8-7-4.9-7-9.2V6.1L12 3.5Z",
    "m8.8 12 2.3 2.3 4.1-4.3",
  ],
  check: ["m5.5 12.5 4.25 4.25L18.5 7.75"],
  /** Three connected nodes: marks model-written text without the sparkle cliche. */
  nodes: [
    "M6 5a2 2 0 1 0 0 4 2 2 0 1 0 0-4Z",
    "M18 5a2 2 0 1 0 0 4 2 2 0 1 0 0-4Z",
    "M12 15.5a2 2 0 1 0 0 4 2 2 0 1 0 0-4Z",
    "M8 7h8",
    "M7.2 8.7l3.7 7.1",
    "M16.8 8.7l-3.7 7.1",
  ],
  layers: ["M12 4 3.75 8.5 12 13l8.25-4.5L12 4Z", "m3.75 12.25 8.25 4.5 8.25-4.5", "m3.75 16 8.25 4.5L20.25 16"],
} as const;

export type IconName = keyof typeof ICON_PATHS;
