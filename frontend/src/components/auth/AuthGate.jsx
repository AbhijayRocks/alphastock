import React, { lazy, Suspense } from 'react';
import { useAuth } from '../../context/AuthContext.jsx';
import { Logo } from '../shell/Logo.jsx';

const Login = lazy(() => import('../../pages/Login.jsx'));

// Full-screen splash shown while we restore a stored session.
const BootSplash = () => (
  <div className="min-h-screen grid place-items-center bg-bg-0">
    <div className="flex flex-col items-center gap-4">
      <Logo size={48} />
      <div className="w-5 h-5 rounded-full border-2 border-line-muted border-t-alpha animate-spin" />
      <div className="text-2xs font-medium tracking-[0.2em] uppercase text-ink-5">AlphaStock Terminal</div>
    </div>
  </div>
);

// Gates the entire application behind authentication. Renders the app only for
// signed-in users; everyone else gets the login experience.
export const AuthGate = ({ children }) => {
  const { isAuthenticated, booting } = useAuth();

  if (booting) return <BootSplash />;

  if (!isAuthenticated) {
    return (
      <Suspense fallback={<BootSplash />}>
        <Login />
      </Suspense>
    );
  }

  return children;
};
