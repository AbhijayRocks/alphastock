import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useApp } from '../context/AppContext.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { useApi } from '../hooks/useApi.js';
import { api, probeBackend } from '../api/client.js';
import { useToast } from '../components/ui/Toast.jsx';
import { Card, CardHeader, CardBody } from '../components/ui/Card.jsx';
import { Button } from '../components/ui/Button.jsx';
import { Input, Select } from '../components/ui/Input.jsx';
import { Badge } from '../components/ui/Badge.jsx';
import { SegmentedControl } from '../components/ui/Tabs.jsx';
import { HORIZONS } from '../data/universe.js';
import { fmtDate } from '../lib/utils.js';
import { IconRefresh, IconCheck, IconGlobe, IconBrain, IconStar, IconUser, IconLogout } from '../components/shell/Icons.jsx';

const initials = (name = '', email = '') => {
  const src = (name || email || '?').trim();
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 2).toUpperCase();
};

const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] },
};

const Section = ({ icon: Icon, title, description, children }) => (
  <Card>
    <CardHeader
      eyebrow={null}
      title={
        <span className="inline-flex items-center gap-2.5">
          {Icon && <span className="w-7 h-7 grid place-items-center rounded-md bg-bg-2 border border-line-muted text-ink-3"><Icon className="w-3.5 h-3.5" /></span>}
          {title}
        </span>
      }
      subtitle={description}
    />
    <CardBody>{children}</CardBody>
  </Card>
);

const Row = ({ label, hint, children }) => (
  <div className="grid grid-cols-1 md:grid-cols-[1fr_minmax(220px,360px)] gap-3 items-center py-3 border-t border-line-faint first:border-t-0">
    <div>
      <div className="text-sm font-medium text-ink-1">{label}</div>
      {hint && <div className="text-xs text-ink-4 mt-0.5">{hint}</div>}
    </div>
    <div className="flex justify-end">{children}</div>
  </div>
);

const Settings = () => {
  const { prefs, updatePrefs, api: apiCfg, setApiBase, setMockMode, backend, watchlist, setWatchlist } = useApp();
  const { user, updateProfile, logout } = useAuth();
  const toast = useToast();
  const [baseURL, setBaseURL] = useState(apiCfg.baseURL);
  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [savingName, setSavingName] = useState(false);

  const handleSaveName = async () => {
    const next = displayName.trim();
    if (!next || next === user?.display_name) return;
    setSavingName(true);
    try {
      await updateProfile({ display_name: next });
      toast.success({ title: 'Profile updated', description: `You'll appear as ${next}.` });
    } catch (e) {
      toast.error({ title: 'Could not update profile', description: e.message });
    } finally {
      setSavingName(false);
    }
  };

  const handleSaveURL = () => {
    setApiBase(baseURL);
    toast.success({ title: 'API base updated', description: baseURL });
  };
  const handleProbe = async () => {
    await probeBackend();
    toast.info({ title: 'Checked service', description: backend.backendOk ? 'Live service reachable' : 'Offline — serving cached analytics' });
  };

  return (
    <div className="space-y-5 pb-12 max-w-3xl">
      <motion.div {...fadeUp}>
        <Section icon={IconUser} title="Account" description="Your profile and session. Watchlist and preferences are saved to this account.">
          <div className="flex items-center gap-4 pb-4 border-b border-line-faint">
            <span className="w-12 h-12 rounded-xl bg-gradient-to-br from-alpha-soft to-alpha-deep grid place-items-center text-sm font-bold text-bg-0 shrink-0">
              {initials(user?.display_name, user?.email)}
            </span>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-ink-1 truncate">{user?.display_name}</div>
              <div className="text-xs text-ink-4 truncate">{user?.email}</div>
              {user?.created_at && (
                <div className="text-2xs text-ink-5 mt-0.5">Member since {fmtDate(user.created_at)}</div>
              )}
            </div>
            <div className="ml-auto">
              <Button size="sm" variant="bear" leadingIcon={IconLogout} onClick={logout}>Sign out</Button>
            </div>
          </div>
          <Row label="Display name" hint="How your name appears across the terminal">
            <div className="flex items-center gap-2 w-full">
              <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Your name" />
              <Button
                size="sm" variant="primary" onClick={handleSaveName} loading={savingName}
                disabled={!displayName.trim() || displayName.trim() === user?.display_name}
                leadingIcon={savingName ? undefined : IconCheck}
              >
                Save
              </Button>
            </div>
          </Row>
        </Section>
      </motion.div>

      <motion.div {...fadeUp}>
        <Section
          icon={IconGlobe}
          title="Connection"
          description="Where to send requests. If the live service is unreachable, AlphaStock automatically serves the last known analytics so your workspace stays responsive."
        >
          <Row label="API base URL" hint="The FastAPI server prefixed with /api">
            <div className="flex items-center gap-2 w-full">
              <Input value={baseURL} onChange={(e) => setBaseURL(e.target.value)} />
              <Button size="sm" variant="primary" onClick={handleSaveURL} leadingIcon={IconCheck}>Save</Button>
            </div>
          </Row>
          <Row label="Mode" hint="How AlphaStock sources analytics">
            <SegmentedControl
              value={apiCfg.mockMode}
              onChange={setMockMode}
              size="sm"
              options={[
                { value: 'auto', label: 'Automatic' },
                { value: 'off',  label: 'Live only' },
                { value: 'on',   label: 'Offline cache' },
              ]}
            />
          </Row>
          <Row label="Service status">
            <div className="flex items-center gap-2">
              <Badge tone={backend.backendOk ? 'bull' : 'warn'} dot size="sm">
                {backend.backendOk === null ? 'Checking…' : backend.backendOk ? 'Live' : 'Offline'}
              </Badge>
              <Button size="xs" variant="ghost" leadingIcon={IconRefresh} onClick={handleProbe}>Re-check</Button>
            </div>
          </Row>
        </Section>
      </motion.div>

      <motion.div {...fadeUp}>
        <Section icon={IconBrain} title="Forecast Defaults" description="Default forecast horizon used across the terminal.">
          <Row label="Default horizon" hint="Initial value for the horizon switcher">
            <Select value={prefs.horizon} onChange={(e) => updatePrefs({ horizon: e.target.value })}>
              {HORIZONS.map((h) => <option key={h.value} value={h.value}>{h.label} — {h.description}</option>)}
            </Select>
          </Row>
        </Section>
      </motion.div>

      <motion.div {...fadeUp}>
        <Section icon={IconStar} title="Watchlist" description="Tickers shown in the sidebar and used as the default portfolio universe.">
          <Row label="Tickers" hint={`${watchlist.length} tracked`}>
            <Button size="sm" variant="ghost" onClick={() => setWatchlist([])}>Clear watchlist</Button>
          </Row>
          <div className="flex flex-wrap gap-2 pt-2">
            {watchlist.length === 0
              ? <span className="text-xs text-ink-4">No tickers yet. Add some from the screener.</span>
              : watchlist.map((t) => (
                <span key={t} className="inline-flex items-center h-7 px-2.5 rounded-md bg-bg-2 border border-line-muted text-xs font-medium text-ink-2">
                  {t.replace('.NS', '')}
                </span>
              ))}
          </div>
        </Section>
      </motion.div>

      <div className="text-2xs text-ink-5 pt-2">
        Your watchlist and preferences are saved to your account and sync wherever you sign in.
      </div>
    </div>
  );
};

export default Settings;
