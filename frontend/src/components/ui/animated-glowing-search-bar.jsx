import React from 'react';
import { cn } from '@/lib/utils';

/**
 * Animated glowing search bar — controlled & reusable.
 *
 * Reworked from the shadcn/TS source for this codebase:
 *  • Plain JSX (project is JavaScript), corrected Tailwind classes that no-op in
 *    3.4 (duration-2000 → duration-[2000ms], rotate-60/70 → rotate-[..deg],
 *    brightness-130/35/40 → brightness-[1.x], animate-spin-slow defined in config).
 *  • Lighter / faster: the original stacked 6 large blurred conic-gradient layers
 *    (3 were identical duplicates) which jank on every focus/keystroke. Trimmed to
 *    4 layers with smaller blur — same glow, far less repaint.
 *  • Smaller default size and retuned to the app's iris/violet accent on a dark
 *    surface (not pure black) so it sits well on the dark theme.
 *
 * Props: value, onChange (controlled) · onSubmit(value) · onFilterClick()
 *        placeholder, name, autoFocus, className, inputRef, aria-label
 */
const AnimatedGlowingSearchBar = ({
  value,
  onChange,
  onSubmit,
  onFilterClick,
  placeholder = 'Search...',
  name = 'search',
  autoFocus = false,
  className,
  inputRef,
  'aria-label': ariaLabel = 'Search',
}) => {
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit?.(value);
  };

  return (
    <div className={cn('relative flex items-center justify-center', className)}>
      <div id="poda" className="relative flex items-center justify-center group">
        {/* Outer glow */}
        <div className="absolute z-[-1] overflow-hidden h-full w-full max-h-[52px] max-w-[262px] rounded-xl blur-[2px]
                        before:absolute before:content-[''] before:z-[-2] before:w-[700px] before:h-[700px] before:bg-no-repeat before:top-1/2 before:left-1/2 before:-translate-x-1/2 before:-translate-y-1/2 before:rotate-[60deg] before:[will-change:transform]
                        before:bg-[conic-gradient(#0a0d14,#6366F1_5%,#0a0d14_38%,#0a0d14_50%,#8B5CF6_60%,#0a0d14_87%)] before:transition-all before:duration-[2000ms]
                        group-hover:before:rotate-[-120deg] group-focus-within:before:rotate-[420deg] group-focus-within:before:duration-[4000ms]">
        </div>
        {/* Mid wash */}
        <div className="absolute z-[-1] overflow-hidden h-full w-full max-h-[49px] max-w-[260px] rounded-xl blur-[2px]
                        before:absolute before:content-[''] before:z-[-2] before:w-[500px] before:h-[500px] before:bg-no-repeat before:top-1/2 before:left-1/2 before:-translate-x-1/2 before:-translate-y-1/2 before:rotate-[82deg] before:[will-change:transform]
                        before:bg-[conic-gradient(rgba(0,0,0,0),#312e81,rgba(0,0,0,0)_10%,rgba(0,0,0,0)_50%,#6d28d9,rgba(0,0,0,0)_60%)] before:transition-all before:duration-[2000ms]
                        group-hover:before:rotate-[-98deg] group-focus-within:before:rotate-[442deg] group-focus-within:before:duration-[4000ms]">
        </div>
        {/* Bright highlight */}
        <div className="absolute z-[-1] overflow-hidden h-full w-full max-h-[47px] max-w-[256px] rounded-lg blur-[1.5px]
                        before:absolute before:content-[''] before:z-[-2] before:w-[500px] before:h-[500px] before:bg-no-repeat before:top-1/2 before:left-1/2 before:-translate-x-1/2 before:-translate-y-1/2 before:rotate-[83deg] before:[will-change:transform]
                        before:bg-[conic-gradient(rgba(0,0,0,0)_0%,#a5b4fc,rgba(0,0,0,0)_8%,rgba(0,0,0,0)_50%,#c4b5fd,rgba(0,0,0,0)_58%)] before:brightness-[1.3]
                        before:transition-all before:duration-[2000ms] group-hover:before:rotate-[-97deg] group-focus-within:before:rotate-[443deg] group-focus-within:before:duration-[4000ms]">
        </div>
        {/* Crisp rim */}
        <div className="absolute z-[-1] overflow-hidden h-full w-full max-h-[44px] max-w-[252px] rounded-xl blur-[0.5px]
                        before:absolute before:content-[''] before:z-[-2] before:w-[500px] before:h-[500px] before:bg-no-repeat before:top-1/2 before:left-1/2 before:-translate-x-1/2 before:-translate-y-1/2 before:rotate-[70deg] before:[will-change:transform]
                        before:bg-[conic-gradient(#0a0d14,#6366F1_5%,#0a0d14_14%,#0a0d14_50%,#8B5CF6_60%,#0a0d14_64%)] before:brightness-[1.25]
                        before:transition-all before:duration-[2000ms] group-hover:before:rotate-[-110deg] group-focus-within:before:rotate-[430deg] group-focus-within:before:duration-[4000ms]">
        </div>

        <form id="main" className="relative" onSubmit={handleSubmit} role="search">
          <input
            ref={inputRef}
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            type="text"
            name={name}
            autoFocus={autoFocus}
            aria-label={ariaLabel}
            className="bg-[#0a0d14] border border-line-faint w-[250px] max-w-full h-[42px] rounded-lg text-ink-1 pl-[42px] pr-[46px] text-sm focus:outline-none placeholder:text-ink-4"
          />
          <div id="input-mask" className="pointer-events-none w-[80px] h-[18px] absolute bg-gradient-to-r from-transparent to-[#0a0d14] top-[12px] left-[46px] group-focus-within:hidden"></div>
          <div id="iris-mask" className="pointer-events-none w-[24px] h-[16px] absolute bg-iris top-[8px] left-[6px] blur-2xl opacity-70 transition-all duration-[2000ms] group-hover:opacity-0"></div>
          <div className="absolute h-[30px] w-[30px] overflow-hidden top-[6px] right-[6px] rounded-lg
                          before:absolute before:content-[''] before:w-[400px] before:h-[400px] before:bg-no-repeat before:top-1/2 before:left-1/2 before:-translate-x-1/2 before:-translate-y-1/2 before:rotate-90 before:[will-change:transform]
                          before:bg-[conic-gradient(rgba(0,0,0,0),#3d3a4f,rgba(0,0,0,0)_50%,rgba(0,0,0,0)_50%,#3d3a4f,rgba(0,0,0,0)_100%)]
                          before:brightness-[1.3] before:animate-spin-slow">
          </div>
          <button
            id="filter-icon"
            type="button"
            onClick={onFilterClick}
            tabIndex={onFilterClick ? 0 : -1}
            aria-label="Toggle filters"
            disabled={!onFilterClick}
            className="absolute top-[6px] right-[6px] flex items-center justify-center z-[2] h-[30px] w-[30px] [isolation:isolate] overflow-hidden rounded-lg bg-gradient-to-b from-[#1e1b4b] via-[#0a0d14] to-[#312e81] border border-transparent disabled:cursor-default"
          >
            <svg preserveAspectRatio="none" height="22" width="22" viewBox="4.8 4.56 14.832 15.408" fill="none">
              <path d="M8.16 6.65002H15.83C16.47 6.65002 16.99 7.17002 16.99 7.81002V9.09002C16.99 9.56002 16.7 10.14 16.41 10.43L13.91 12.64C13.56 12.93 13.33 13.51 13.33 13.98V16.48C13.33 16.83 13.1 17.29 12.81 17.47L12 17.98C11.24 18.45 10.2 17.92 10.2 16.99V13.91C10.2 13.5 9.97 12.98 9.73 12.69L7.52 10.36C7.23 10.08 7 9.55002 7 9.20002V7.87002C7 7.17002 7.52 6.65002 8.16 6.65002Z" stroke="#d6d6e6" strokeWidth="1" strokeMiterlimit="10" strokeLinecap="round" strokeLinejoin="round"></path>
            </svg>
          </button>
          <div id="search-icon" className="absolute left-3.5 top-[11px] pointer-events-none">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" viewBox="0 0 24 24" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" height="20" fill="none" className="feather feather-search">
              <circle stroke="url(#search)" r="8" cy="11" cx="11"></circle>
              <line stroke="url(#searchl)" y2="16.65" y1="22" x2="16.65" x1="22"></line>
              <defs>
                <linearGradient gradientTransform="rotate(50)" id="search">
                  <stop stopColor="#f8e7f8" offset="0%"></stop>
                  <stop stopColor="#b6a9b7" offset="50%"></stop>
                </linearGradient>
                <linearGradient id="searchl">
                  <stop stopColor="#b6a9b7" offset="0%"></stop>
                  <stop stopColor="#837484" offset="50%"></stop>
                </linearGradient>
              </defs>
            </svg>
          </div>
        </form>
      </div>
    </div>
  );
};

export { AnimatedGlowingSearchBar };
export default AnimatedGlowingSearchBar;
