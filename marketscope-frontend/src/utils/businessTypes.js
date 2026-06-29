export const BUSINESS_TYPE_OPTIONS = [
  { value: 'coffee', label: 'Coffee Shops / Cafes' },
  { value: 'print', label: 'Print / Copy Centers' },
  { value: 'laundry', label: 'Laundry Shops' },
  { value: 'carwash', label: 'Car Washes' },
  { value: 'kiosk', label: 'Food Kiosks / Stalls' },
  { value: 'water', label: 'Water Refilling Stations' },
  { value: 'bakery', label: 'Bakeries' },
  { value: 'pharmacy', label: 'Small Pharmacies' },
  { value: 'barber', label: 'Barbershops / Salons' },
  { value: 'moto', label: 'Motorcycle Repair Shops' },
  { value: 'internet', label: 'Internet Cafes' },
  { value: 'meat', label: 'Meat Shops' },
  { value: 'hardware', label: 'Hardware / Construction Supplies' }
];

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
