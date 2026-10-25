// color: the category's map pin and legend color.
export const BUSINESS_TYPE_OPTIONS = [
  { value: 'coffee', label: 'Coffee Shops / Cafes', color: '#b45309' },
  { value: 'print', label: 'Print / Copy Centers', color: '#2563eb' },
  { value: 'laundry', label: 'Laundry Shops', color: '#0891b2' },
  { value: 'carwash', label: 'Car Washes', color: '#0d9488' },
  { value: 'kiosk', label: 'Food Kiosks / Stalls', color: '#f97316' },
  { value: 'water', label: 'Water Refilling Stations', color: '#38bdf8' },
  { value: 'bakery', label: 'Bakeries', color: '#eab308' },
  { value: 'pharmacy', label: 'Small Pharmacies', color: '#16a34a' },
  { value: 'barber', label: 'Barbershops / Salons', color: '#db2777' },
  { value: 'moto', label: 'Motorcycle Repair/Parts & Accessories', color: '#7c3aed' },
  { value: 'internet', label: 'Internet Cafes', color: '#c026d3' },
  { value: 'meat', label: 'Meat Shops', color: '#dc2626' },
  { value: 'hardware', label: 'Hardware / Construction Supplies', color: '#65a30d' }
];

export const DEFAULT_BUSINESS_TYPE_COLOR = '#ef4444';

export const BUSINESS_TYPE_DEFAULT = BUSINESS_TYPE_OPTIONS[0]?.value || '';

export const BUSINESS_TYPE_LABEL_BY_VALUE = BUSINESS_TYPE_OPTIONS.reduce((accumulator, option) => {
  accumulator[option.value] = option.label;
  return accumulator;
}, {});

export const BUSINESS_TYPE_VALUE_BY_LABEL = BUSINESS_TYPE_OPTIONS.reduce((accumulator, option) => {
  accumulator[option.label.toLowerCase()] = option.value;
  return accumulator;
}, {});

export const getBusinessTypeLabel = (value) => BUSINESS_TYPE_LABEL_BY_VALUE[String(value || '').trim().toLowerCase()] || value || '';

export const getBusinessTypeKey = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (!normalized) return '';
  if (BUSINESS_TYPE_LABEL_BY_VALUE[normalized]) return normalized;
  return BUSINESS_TYPE_VALUE_BY_LABEL[normalized] || normalized;
};

const BUSINESS_TYPE_COLOR_BY_VALUE = BUSINESS_TYPE_OPTIONS.reduce((accumulator, option) => {
  accumulator[option.value] = option.color;
  return accumulator;
}, {});

// Accepts a key ("bakery") or a label ("Bakeries").
export const getBusinessTypeColor = (value) => BUSINESS_TYPE_COLOR_BY_VALUE[getBusinessTypeKey(value)] || DEFAULT_BUSINESS_TYPE_COLOR;
