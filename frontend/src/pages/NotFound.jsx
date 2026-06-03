import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button.jsx';
import { Card } from '../components/ui/Card.jsx';
import { IconHome, IconCompass } from '../components/shell/Icons.jsx';

const NotFound = () => {
  const nav = useNavigate();
  return (
    <div className="grid place-items-center min-h-[60vh]">
      <Card className="max-w-md text-center px-8 py-10">
        <div className="text-alpha-gradient font-display font-bold text-4xl">404</div>
        <h2 className="font-display font-semibold text-md text-ink-1 mt-3">Page not found</h2>
        <p className="text-sm text-ink-3 mt-1.5 max-w-xs mx-auto">
          That route doesn't exist in the terminal. Jump back to the overview or use the command palette.
        </p>
        <div className="flex items-center justify-center gap-2 mt-5">
          <Button variant="primary" leadingIcon={IconHome} onClick={() => nav('/')}>Overview</Button>
          <Button variant="surface" leadingIcon={IconCompass} onClick={() => nav('/screener')}>Open Screener</Button>
        </div>
      </Card>
    </div>
  );
};

export default NotFound;
