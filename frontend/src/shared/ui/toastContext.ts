import { createContext, useContext } from 'react';

export type ToastTone = 'ok' | 'error';
export type ShowToast = (message: string, tone?: ToastTone) => void;

export const ToastContext = createContext<ShowToast | null>(null);

export function useToast(): ShowToast {
  const show = useContext(ToastContext);
  if (!show) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  return show;
}
