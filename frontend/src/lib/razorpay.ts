import type { CheckoutResponse, PaymentVerification } from "@/lib/types";

const SCRIPT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

export interface RazorpayCheckoutOptions {
  key: string;
  subscription_id: string;
  name: string;
  description: string;
  prefill?: { name?: string; email?: string };
  theme?: { color?: string };
  handler?: (response: PaymentVerification) => void;
  modal?: { ondismiss?: () => void };
}

export interface RazorpayInstance {
  open: () => void;
  on: (event: string, handler: (...args: unknown[]) => void) => void;
  close: () => void;
}

type RazorpayConstructor = new (options: RazorpayCheckoutOptions) => RazorpayInstance;

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor;
  }
}

let loader: Promise<RazorpayConstructor> | null = null;

export function loadRazorpay(): Promise<RazorpayConstructor> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Razorpay checkout requires a browser"));
  }
  if (window.Razorpay) {
    return Promise.resolve(window.Razorpay);
  }
  if (loader) return loader;

  loader = new Promise<RazorpayConstructor>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    script.onload = () => {
      if (window.Razorpay) {
        resolve(window.Razorpay);
      } else {
        loader = null;
        reject(new Error("Razorpay checkout failed to initialise"));
      }
    };
    script.onerror = () => {
      loader = null;
      script.remove();
      reject(new Error("Could not load Razorpay checkout"));
    };
    document.body.appendChild(script);
  });

  return loader;
}

export interface CheckoutHandlers {
  onSuccess: (response: PaymentVerification) => void;
  onDismiss?: () => void;
}

/**
 * Opens the hosted Razorpay checkout for a server-created subscription.
 *
 * The subscription id and key id always come from our API so the browser can
 * never pick its own plan or amount. If the checkout script is blocked (an
 * aggressive ad blocker, an offline preview) we fall back to the provider's
 * short link so the payment can still complete.
 */
export async function openCheckout(
  session: CheckoutResponse,
  handlers: CheckoutHandlers,
  prefill: { name?: string; email?: string } = {},
): Promise<void> {
  let Razorpay: RazorpayConstructor;
  try {
    Razorpay = await loadRazorpay();
  } catch (error) {
    if (session.short_url) {
      window.location.href = session.short_url;
      return;
    }
    throw error;
  }

  const checkout = new Razorpay({
    key: session.key_id,
    subscription_id: session.subscription_id,
    name: session.name,
    description: session.description,
    prefill,
    theme: { color: "#2dd4bf" },
    handler: handlers.onSuccess,
    modal: handlers.onDismiss ? { ondismiss: handlers.onDismiss } : undefined,
  });

  checkout.on("payment.failed", () => {
    handlers.onDismiss?.();
  });

  checkout.open();
}
