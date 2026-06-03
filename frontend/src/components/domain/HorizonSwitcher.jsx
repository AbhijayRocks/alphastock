import React from 'react';
import { SegmentedControl } from '../ui/Tabs.jsx';
import { HORIZONS } from '../../data/universe.js';

export const HorizonSwitcher = ({ value, onChange, size = 'md', className }) => (
  <SegmentedControl
    value={value}
    onChange={onChange}
    size={size}
    className={className}
    options={HORIZONS.map((h) => ({ value: h.value, label: h.label }))}
  />
);
