import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../context/AuthContext.jsx';
import { useToast } from '../components/ui/Toast.jsx';
import { Logo, LogoLockup } from '../components/shell/Logo.jsx';
import { Button } from '../components/ui/Button.jsx';
import { Input } from '../components/ui/Input.jsx';
import {
  IconMail, IconLock, IconUser, IconEye, IconEyeOff, IconArrowRight,
  IconBrain, IconShield, IconActivity,
} from '../components/shell/Icons.jsx';
import { cn } from '../lib/utils.js';

const HIGHLIGHTS = [
  { icon: IconBrain,    title: 'Predictive market signals', body: 'Direction, expected return & confidence across 1D / 5D / 20D horizons for the NIFTY 50.' },
  { icon: IconActivity, title: 'Regime-aware insights',     body: 'Bull, bear, sideways & crisis detection adapts every signal to current market conditions.' },
  { icon: IconShield,   title: 'Transparent by design',     body: 'Every signal comes with the key factors behind it — full visibility, no black boxes.' },
];

const FieldLabel = ({ children }) => (
  <label className="block text-xs font-medium text-ink-3 mb-1.5">{children}</label>
);

// ── Left brand panel ─────────────────────────────────────────────────────────────
const BrandPanel = () => (
  <div className="relative hidden lg:flex flex-col justify-between overflow-hidden bg-bg-1 border-r border-line-faint p-12 xl:p-16">
    {/* ambient gold wash + grid */}
    <div className="absolute inset-0 bg-alpha-radial opacity-70 pointer-events-none" />
    <div className="absolute inset-0 bg-grid-faint bg-grid-32 opacity-[0.5] pointer-events-none" />

    <div className="relative z-10">
      <LogoLockup size={40} />
    </div>

    <div className="relative z-10 max-w-md">
      <div className="eyebrow mb-4">Quant intelligence · NIFTY 50</div>
      <h1 className="font-display font-bold text-4xl text-ink-1 leading-[1.1] tracking-tight">
        Trade with an
        <span className="text-alpha-gradient"> analytical edge.</span>
      </h1>
      <p className="text-md text-ink-3 mt-5 leading-relaxed">
        AlphaStock Terminal turns a decade of NSE data into clear, explainable signals —
        built for investors, traders and portfolio managers who demand more than gut feel.
      </p>

      <div className="mt-10 space-y-5">
        {HIGHLIGHTS.map((h) => (
          <div key={h.title} className="flex gap-3.5">
            <div className="w-9 h-9 rounded-lg bg-bg-2 border border-line-muted grid place-items-center shrink-0 text-alpha">
              <h.icon className="w-4.5 h-4.5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-ink-1">{h.title}</div>
              <div className="text-xs text-ink-4 mt-0.5 leading-relaxed">{h.body}</div>
            </div>
          </div>
        ))}
      </div>
    </div>

    <div className="relative z-10 flex items-center gap-2 text-2xs text-ink-5">
      <span className="live-dot" />
      Built on a decade of NSE market history
    </div>
  </div>
);

// ── Auth form ────────────────────────────────────────────────────────────────────
const AuthForm = () => {
  const { login, register } = useAuth();
  const toast = useToast();

  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const isRegister = mode === 'register';

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!email.trim() || !password) { setError('Please fill in all fields.'); return; }
    if (isRegister && password.length < 8) { setError('Password must be at least 8 characters.'); return; }

    setBusy(true);
    try {
      if (isRegister) {
        const s = await register({ email, password, displayName: name });
        toast.success({ title: `Welcome, ${s.user.display_name}`, description: 'Your account is ready.' });
      } else {
        const s = await login({ email, password });
        toast.success({ title: `Welcome back, ${s.user.display_name}`, description: 'Signed in successfully.' });
      }
      // AuthGate swaps in the app automatically once authenticated.
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (next) => { setMode(next); setError(''); };

  return (
    <div className="flex flex-col items-center justify-center px-5 py-10 sm:px-10">
      <div className="w-full max-w-[400px]">
        {/* Mobile logo */}
        <div className="lg:hidden flex justify-center mb-8">
          <LogoLockup size={36} />
        </div>

        <div className="mb-7">
          <h2 className="font-display font-bold text-2xl text-ink-1 tracking-tight">
            {isRegister ? 'Create your account' : 'Sign in to your terminal'}
          </h2>
          <p className="text-sm text-ink-4 mt-1.5">
            {isRegister
              ? 'Set up a personalised workspace in seconds.'
              : 'Welcome back. Your watchlist is waiting.'}
          </p>
        </div>

        {/* Segmented mode toggle */}
        <div className="grid grid-cols-2 gap-1 p-1 rounded-lg bg-bg-1 border border-line-muted mb-6">
          {['login', 'register'].map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => switchMode(m)}
              className={cn(
                'relative h-8 rounded-md text-sm font-medium transition-colors',
                mode === m ? 'text-bg-0' : 'text-ink-3 hover:text-ink-1',
              )}
            >
              {mode === m && (
                <motion.span
                  layoutId="auth-seg"
                  className="absolute inset-0 bg-alpha rounded-md shadow-soft"
                  transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                />
              )}
              <span className="relative z-10">{m === 'login' ? 'Sign in' : 'Create account'}</span>
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-4" noValidate>
          <AnimatePresence initial={false} mode="popLayout">
            {isRegister && (
              <motion.div
                key="name"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
              >
                <FieldLabel>Full name</FieldLabel>
                <Input
                  size="lg" leadingIcon={IconUser} value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Aarav Sharma" autoComplete="name"
                />
              </motion.div>
            )}
          </AnimatePresence>

          <div>
            <FieldLabel>Email address</FieldLabel>
            <Input
              size="lg" type="email" leadingIcon={IconMail} value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com" autoComplete="email" required
            />
          </div>

          <div>
            <FieldLabel>Password</FieldLabel>
            <Input
              size="lg" type={showPw ? 'text' : 'password'} leadingIcon={IconLock} value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isRegister ? 'At least 8 characters' : '••••••••'}
              autoComplete={isRegister ? 'new-password' : 'current-password'} required
              trailing={
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  className="w-7 h-7 grid place-items-center rounded-md text-ink-4 hover:text-ink-2 transition-colors"
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                  tabIndex={-1}
                >
                  {showPw ? <IconEyeOff className="w-4 h-4" /> : <IconEye className="w-4 h-4" />}
                </button>
              }
            />
          </div>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="flex items-start gap-2 px-3 py-2 rounded-lg bg-bear/10 border border-bear/30 text-bear text-xs"
              >
                <span className="mt-px">⚠</span><span>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          <Button
            type="submit" variant="primary" size="lg" loading={busy}
            trailingIcon={busy ? undefined : IconArrowRight}
            className="w-full mt-2"
          >
            {isRegister ? 'Create account' : 'Sign in'}
          </Button>
        </form>

        <p className="text-2xs text-ink-5 text-center mt-6 leading-relaxed">
          {isRegister
            ? 'By creating an account you agree to our Terms of Service and Privacy Policy.'
            : 'Secure sign-in · Your session is encrypted end-to-end.'}
        </p>
      </div>
    </div>
  );
};

const Login = () => (
  <div className="min-h-screen grid lg:grid-cols-2 bg-bg-0 text-ink-1">
    <BrandPanel />
    <AuthForm />
  </div>
);

export default Login;
