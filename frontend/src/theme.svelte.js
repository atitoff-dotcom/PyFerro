let currentTheme = $state(
  typeof window !== "undefined"
    ? localStorage.getItem("pyferro_admin_theme") ||
      (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
    : "dark"
);

export function getTheme() {
  return currentTheme;
}

export function isDark() {
  return currentTheme === "dark";
}

export function setTheme(theme) {
  currentTheme = theme;
  if (typeof window !== "undefined") {
    localStorage.setItem("pyferro_admin_theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
  }
}

export function toggleTheme() {
  setTheme(currentTheme === "dark" ? "light" : "dark");
}

export function initTheme() {
  if (typeof window !== "undefined") {
    const saved = localStorage.getItem("pyferro_admin_theme");
    const theme =
      saved ||
      (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    currentTheme = theme;
    document.documentElement.setAttribute("data-theme", theme);
  }
}
