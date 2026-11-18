/* Small stroke icons for the feature grid. 24x24, inherit colour from the parent. */
const base = { width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const Icon = {
  gauge: () => (<svg {...base}><path d="M4 16a8 8 0 1 1 16 0" /><path d="M12 16l4-5" /><circle cx="12" cy="16" r="1.2" /></svg>),
  pulse: () => (<svg {...base}><path d="M3 12h4l2.5-6 4 12 2.5-6H21" /></svg>),
  flask: () => (<svg {...base}><path d="M9 3h6" /><path d="M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3" /><path d="M7.5 15h9" /></svg>),
  text: () => (<svg {...base}><path d="M5 6h14" /><path d="M5 12h14" /><path d="M5 18h8" /></svg>),
  shield: () => (<svg {...base}><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /><path d="M9 12l2 2 4-4" /></svg>),
  list: () => (<svg {...base}><path d="M9 6h11" /><path d="M9 12h11" /><path d="M9 18h11" /><path d="M4 6l1 1 2-2" /><path d="M4 12l1 1 2-2" /><path d="M4 18l1 1 2-2" /></svg>),
  upload: () => (<svg {...base}><path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></svg>),
  user: () => (<svg {...base}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>),
  download: () => (<svg {...base}><path d="M12 4v12" /><path d="M7 11l5 5 5-5" /><path d="M4 20h16" /></svg>),
  clock: () => (<svg {...base}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>),
  arrow: () => (<svg {...base} width={16} height={16}><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></svg>),
};
