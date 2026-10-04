import { BuildingStorefrontIcon, HomeModernIcon, MapIcon, UsersIcon } from '@heroicons/react/24/outline';

// The admin console's pages, shared by the desktop sidebar and the mobile tab bar.
export const ADMIN_NAV_ITEMS = [
  { id: 'msmes', label: 'MSMEs', icon: BuildingStorefrontIcon },
  { id: 'users', label: 'Users', icon: UsersIcon },
  { id: 'spaces', label: 'Spaces', icon: HomeModernIcon },
  { id: 'flood', label: 'Map Layers', icon: MapIcon }
];

export const DEFAULT_ADMIN_TAB = 'msmes';

export const isAdminTab = (tabId) => ADMIN_NAV_ITEMS.some((item) => item.id === tabId);
