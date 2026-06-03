// Inline SVG icon set — Lucide-style 1.5-stroke. Keeps the bundle small and
// guarantees consistent stroke width, line caps, and visual rhythm.

import React from 'react';

const I = ({ children, size = 16, className, strokeWidth = 1.6, ...rest }) => (
  <svg
    width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={strokeWidth}
    strokeLinecap="round" strokeLinejoin="round"
    className={className} aria-hidden="true" {...rest}
  >
    {children}
  </svg>
);

export const IconHome      = (p) => <I {...p}><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></I>;
export const IconCompass   = (p) => <I {...p}><circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2.5 5-5 2.5 2.5-5z"/></I>;
export const IconBeaker    = (p) => <I {...p}><path d="M9 3h6"/><path d="M10 3v6.5L4.5 19a2 2 0 001.7 3h11.6a2 2 0 001.7-3L14 9.5V3"/></I>;
export const IconBriefcase = (p) => <I {...p}><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2"/></I>;
export const IconChart     = (p) => <I {...p}><path d="M3 21h18"/><path d="M6 17v-5"/><path d="M11 17V8"/><path d="M16 17v-3"/><path d="M21 17v-9"/></I>;
export const IconLayers    = (p) => <I {...p}><path d="M12 2l9 5-9 5-9-5z"/><path d="M3 12l9 5 9-5"/><path d="M3 17l9 5 9-5"/></I>;
export const IconSparkles  = (p) => <I {...p}><path d="M12 3v4"/><path d="M12 17v4"/><path d="M5 12H1"/><path d="M23 12h-4"/><path d="M6 6l-3-3"/><path d="M21 21l-3-3"/><path d="M6 18l-3 3"/><path d="M21 3l-3 3"/></I>;
export const IconSettings  = (p) => <I {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.9 2.9l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 01-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.9-2.9l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 010-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.9-2.9l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 014 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.9 2.9l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z"/></I>;
export const IconSearch    = (p) => <I {...p}><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></I>;
export const IconCommand   = (p) => <I {...p}><path d="M18 6a3 3 0 100-6 3 3 0 000 6zm0 18a3 3 0 110-6 3 3 0 010 6zM6 0a3 3 0 100 6 3 3 0 000-6zm0 18a3 3 0 100 6 3 3 0 000-6z"/><path d="M6 6h12v12H6z"/></I>;
export const IconBell      = (p) => <I {...p}><path d="M6 8a6 6 0 0112 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21a2 2 0 004 0"/></I>;
export const IconArrowUp   = (p) => <I {...p}><path d="M12 19V5"/><path d="M5 12l7-7 7 7"/></I>;
export const IconArrowDown = (p) => <I {...p}><path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/></I>;
export const IconArrowRight= (p) => <I {...p}><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></I>;
export const IconArrowLeft = (p) => <I {...p}><path d="M19 12H5"/><path d="M12 5l-7 7 7 7"/></I>;
export const IconCheck     = (p) => <I {...p}><path d="M4 12l5 5L20 6"/></I>;
export const IconX         = (p) => <I {...p}><path d="M6 6l12 12M18 6L6 18"/></I>;
export const IconStar      = (p) => <I {...p}><polygon points="12 2 15 9 22 10 17 14 18 21 12 18 6 21 7 14 2 10 9 9"/></I>;
export const IconStarFill  = (p) => <I {...p} strokeWidth={0} fill="currentColor"><polygon points="12 2 15 9 22 10 17 14 18 21 12 18 6 21 7 14 2 10 9 9"/></I>;
export const IconPlus      = (p) => <I {...p}><path d="M12 5v14M5 12h14"/></I>;
export const IconMinus     = (p) => <I {...p}><path d="M5 12h14"/></I>;
export const IconDownload  = (p) => <I {...p}><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></I>;
export const IconUpload    = (p) => <I {...p}><path d="M12 21V9"/><path d="M7 14l5-5 5 5"/><path d="M5 3h14"/></I>;
export const IconRefresh   = (p) => <I {...p}><path d="M3 12a9 9 0 0115-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 01-15 6.7L3 16"/><path d="M3 21v-5h5"/></I>;
export const IconActivity  = (p) => <I {...p}><path d="M3 12h4l3-9 4 18 3-9h4"/></I>;
export const IconFilter    = (p) => <I {...p}><path d="M3 4h18l-7 9v6l-4 2v-8z"/></I>;
export const IconSliders   = (p) => <I {...p}><path d="M4 6h12"/><path d="M20 6h0"/><path d="M4 12h0"/><path d="M8 12h12"/><path d="M4 18h12"/><path d="M20 18h0"/><circle cx="18" cy="6" r="2"/><circle cx="6" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></I>;
export const IconBolt      = (p) => <I {...p}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10"/></I>;
export const IconShield    = (p) => <I {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></I>;
export const IconGlobe     = (p) => <I {...p}><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 010 20"/><path d="M12 2a15 15 0 000 20"/></I>;
export const IconClock     = (p) => <I {...p}><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></I>;
export const IconInfo      = (p) => <I {...p}><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></I>;
export const IconExternal  = (p) => <I {...p}><path d="M14 4h6v6"/><path d="M10 14L20 4"/><path d="M20 14v5a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2h5"/></I>;
export const IconExpand    = (p) => <I {...p}><path d="M4 14v6h6"/><path d="M20 10V4h-6"/><path d="M14 10l6-6"/><path d="M10 14l-6 6"/></I>;
export const IconCollapse  = (p) => <I {...p}><path d="M14 4h6v6"/><path d="M10 20H4v-6"/><path d="M20 4l-6 6"/><path d="M4 20l6-6"/></I>;
export const IconQuestion  = (p) => <I {...p}><circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 015.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></I>;
export const IconBookOpen  = (p) => <I {...p}><path d="M2 4h7a3 3 0 013 3v13"/><path d="M22 4h-7a3 3 0 00-3 3v13"/><path d="M2 4v15h7"/><path d="M22 4v15h-7"/></I>;
export const IconScale     = (p) => <I {...p}><path d="M12 3v18"/><path d="M5 21h14"/><path d="M5 6l-3 7a4 4 0 008 0z"/><path d="M19 6l-3 7a4 4 0 008 0z"/></I>;
export const IconTarget    = (p) => <I {...p}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor" strokeWidth="0"/></I>;
export const IconBrain     = (p) => <I {...p}><path d="M9 3a3 3 0 00-3 3v.5A3 3 0 005 12a3 3 0 002 5.5V19a3 3 0 003 3"/><path d="M15 3a3 3 0 013 3v.5A3 3 0 0119 12a3 3 0 01-2 5.5V19a3 3 0 01-3 3"/><path d="M9 12h6"/></I>;
export const IconWaveform  = (p) => <I {...p}><path d="M2 12h2"/><path d="M6 8v8"/><path d="M10 4v16"/><path d="M14 8v8"/><path d="M18 6v12"/><path d="M22 12h-2"/></I>;
export const IconMail      = (p) => <I {...p}><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M3 6l9 7 9-7"/></I>;
export const IconLock      = (p) => <I {...p}><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4"/></I>;
export const IconEye       = (p) => <I {...p}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></I>;
export const IconEyeOff    = (p) => <I {...p}><path d="M9.9 5.1A9.6 9.6 0 0112 5c6.5 0 10 7 10 7a17 17 0 01-3.2 4M6.2 6.2A17 17 0 002 12s3.5 7 10 7a9.6 9.6 0 003.9-.8"/><path d="M3 3l18 18"/><path d="M9.9 9.9a3 3 0 004.2 4.2"/></I>;
export const IconUser      = (p) => <I {...p}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/></I>;
export const IconLogout    = (p) => <I {...p}><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></I>;
export const IconChevronDown = (p) => <I {...p}><path d="M6 9l6 6 6-6"/></I>;
