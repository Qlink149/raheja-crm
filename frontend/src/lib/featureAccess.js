export const LOCKED_FEATURES = {
  virtualCustomer: "preview",
  salesDashboard: true,
  marketingDashboard: true,
  notifications: true,
};

export const LOCKED_PATHS = {
  "/virtual-customer": "virtualCustomer",
  "/sales-dashboard": "salesDashboard",
  "/marketing-dashboard": "marketingDashboard",
  "/notifications": "notifications",
};

export const SHOW_PROJECT_DISTRIBUTION = false;

export const isVcPreviewMode = () => LOCKED_FEATURES.virtualCustomer === "preview";

export const isVcFullyLocked = () => LOCKED_FEATURES.virtualCustomer === true;

export const isFeatureLocked = (key) => {
  if (key === "virtualCustomer" && isVcPreviewMode()) {
    return false;
  }
  return LOCKED_FEATURES[key] === true;
};

export const isPathLocked = (path) => {
  if (path === "/virtual-customer" && isVcPreviewMode()) {
    return false;
  }
  const key = LOCKED_PATHS[path];
  return key ? isFeatureLocked(key) : false;
};

export const isPathPreview = (path) =>
  path === "/virtual-customer" && isVcPreviewMode();
