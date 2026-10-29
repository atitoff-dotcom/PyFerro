let toasts = $state([]);
let nextId = 1;

export function addToast(message, type = "success", duration = 3500) {
  const id = nextId++;
  const toastItem = { id, message, type };
  toasts.push(toastItem);

  if (duration > 0) {
    setTimeout(() => {
      removeToast(id);
    }, duration);
  }
  return id;
}

export function removeToast(id) {
  const idx = toasts.findIndex((t) => t.id === id);
  if (idx !== -1) {
    toasts.splice(idx, 1);
  }
}

export const toast = {
  success: (msg, dur = 3500) => addToast(msg, "success", dur),
  error: (msg, dur = 4500) => addToast(msg, "danger", dur),
  warning: (msg, dur = 4000) => addToast(msg, "warning", dur),
  info: (msg, dur = 3500) => addToast(msg, "info", dur),
};

export function getToasts() {
  return toasts;
}
