import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useApi } from '../hooks/useApi.js';
import { api } from '../api/client.js';
import { Card, CardHeader, CardBody } from '../components/ui/Card.jsx';
import { Select, Input } from '../components/ui/Input.jsx';
import { SegmentedControl } from '../components/ui/Tabs.jsx';
import { Badge } from '../components/ui/Badge.jsx';
import { Button } from '../components/ui/Button.jsx';
import { Skeleton } from '../components/ui/Skeleton.jsx';
import { EmptyState } from '../components/ui/Empty.jsx';
import { IconArrowRight, IconRefresh, IconSearch } from '../components/shell/Icons.jsx';

const RANGES = [
  { value: '1d',  label: 'Today' },
  { value: '7d',  label: 'Week' },
  { value: '30d', label: 'Month' },
  { value: 'all', label: 'All' },
];

const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] },
};

const SECTORS_FALLBACK = [
  'Financial Services', 'Information Technology', 'Energy', 'FMCG', 'Healthcare',
  'Materials', 'Consumer Discretionary', 'Communication', 'Capital Goods',
  'Utilities', 'Industrials',
];

const timeAgo = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const s = Math.max(1, Math.floor((Date.now() - d.getTime()) / 1000));
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const News = () => {
  const { data: sectorsData } = useApi(() => api.newsSectors(), []);
  const sectors = sectorsData?.sectors?.length ? sectorsData.sectors : SECTORS_FALLBACK;

  const [sector, setSector] = useState('Financial Services');
  const [range, setRange] = useState('7d');
  const [query, setQuery] = useState('');

  const { data, loading, refetch } = useApi(() => api.news(sector, 30, range), [sector, range]);
  const articles = data?.articles || [];

  const q = query.trim().toLowerCase();
  const filtered = q
    ? articles.filter((a) =>
        (a.headline || '').toLowerCase().includes(q) ||
        (a.source || '').toLowerCase().includes(q))
    : articles;

  return (
    <div className="space-y-5 pb-12">
      <motion.div {...fadeUp} className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display font-bold text-2xl text-ink-1">Market News</h1>
          <p className="text-sm text-ink-4 mt-0.5">Latest India news by sector. Every headline links to its source.</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="eyebrow">Sector</span>
          <Select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="min-w-[220px] font-medium"
            aria-label="Select sector"
          >
            {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Button size="sm" variant="ghost" leadingIcon={IconRefresh} onClick={refetch}>Refresh</Button>
        </div>
      </motion.div>

      {/* Filters: date range + search */}
      <motion.div {...fadeUp} className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <span className="eyebrow">Date range</span>
          <SegmentedControl value={range} onChange={setRange} options={RANGES} size="sm" />
        </div>
        <div className="relative">
          <IconSearch className="w-4 h-4 text-ink-4 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter headlines…"
            className="pl-9 min-w-[220px]"
            aria-label="Filter headlines"
          />
        </div>
      </motion.div>

      <motion.div {...fadeUp}>
        <Card>
          <CardHeader
            eyebrow={`${sector} · ${RANGES.find((r) => r.value === range)?.label || ''}`}
            title="Headlines"
            subtitle={data ? `${filtered.length} of ${data.count} articles${q ? ' (filtered)' : ''}` : 'Fetching latest news…'}
          />
          <CardBody>
            {loading && !articles.length ? (
              <div className="space-y-3">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
              </div>
            ) : filtered.length ? (
              <div className="divide-y divide-line-faint">
                {filtered.map((a, i) => (
                  <a
                    key={i}
                    href={a.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block py-3 group first:pt-0"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-ink-1 group-hover:text-alpha transition-colors leading-snug">
                          {a.headline}
                        </div>
                        {a.summary && <div className="text-xs text-ink-4 mt-1">{a.summary}</div>}
                        <div className="flex items-center gap-2 mt-1.5">
                          <Badge tone="iris" size="sm">{a.source}</Badge>
                          {a.published && <span className="text-2xs text-ink-5">{timeAgo(a.published)}</span>}
                        </div>
                      </div>
                      <IconArrowRight className="w-4 h-4 text-ink-5 group-hover:text-alpha shrink-0 mt-1 transition-colors" />
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <EmptyState
                title={q ? 'No matching headlines' : 'No news right now'}
                description={q
                  ? 'Nothing matches your filter. Clear the search or widen the date range.'
                  : 'Couldn\'t load articles for this sector. Try another sector, widen the date range, or hit refresh.'}
              />
            )}
          </CardBody>
        </Card>
      </motion.div>

      <p className="text-2xs text-ink-5 text-center">
        News via Google News · headlines and links belong to their respective publishers.
      </p>
    </div>
  );
};

export default News;
