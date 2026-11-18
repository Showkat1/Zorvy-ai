"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  Check,
  CreditCard,
  Infinity as InfinityIcon,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { openCheckout } from "@/lib/razorpay";
import type {
  CheckoutResponse,
  PlanId,
  PlanLimits,
  PlansResponse,
  SubscriptionState,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";

const PLAN_ORDER: PlanId[] = ["free", "pro", "standard"];

export function formatInr(value: number): string {
  return `₹${value.toLocaleString("en-IN")}`;
}

function planFeatures(plan: PlanLimits): string[] {
  const investigations =
    plan.investigations_per_month === null
      ? "Unlimited investigations"
      : `${plan.investigations_per_month} investigations / month`;
  const scans =
    plan.device_scans_per_month === null
      ? "Unlimited device scans"
      : `${plan.device_scans_per_month} device scans / month`;

  const features = [investigations, scans];
  features.push(plan.exports ? "Report export (JSON)" : "No report export");
  if (plan.api_access) features.push("API access");
  return features;
}

function usageLabel(used: number, limit: number | null): string {
  if (limit === null) return `${used} this period · unlimited`;
  return `${used} of ${limit} used`;
}

export function BillingCard() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [checkoutPlan, setCheckoutPlan] = useState<PlanId | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);

  const subscription = useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: () => api.get<SubscriptionState>("/api/v1/billing/subscription"),
  });

  const plans = useQuery({
    queryKey: ["billing", "plans"],
    queryFn: () => api.get<PlansResponse>("/api/v1/billing/plans", { auth: false }),
    staleTime: 10 * 60_000,
  });

  function invalidateBilling() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ["billing", "subscription"] }),
      queryClient.invalidateQueries({ queryKey: ["overview"] }),
      queryClient.invalidateQueries({ queryKey: ["investigations"] }),
      queryClient.invalidateQueries({ queryKey: ["device-scans"] }),
    ]);
  }

  const verify = useMutation({
    mutationFn: (payload: {
      razorpay_payment_id: string;
      razorpay_subscription_id: string;
      razorpay_signature: string;
    }) => api.post<SubscriptionState>("/api/v1/billing/verify", payload),
    onSuccess: async (state) => {
      toast.success(`You're on ${state.name}. Enjoy the upgrade.`);
      await invalidateBilling();
    },
    onError: (error) => {
      toast.error(errorMessage(error));
      void invalidateBilling();
    },
  });

  const startCheckout = useMutation({
    mutationFn: (plan: PlanId) =>
      api.post<CheckoutResponse>("/api/v1/billing/checkout", { plan }),
    onMutate: (plan) => {
      setCheckoutPlan(plan);
    },
    onSuccess: async (session) => {
      try {
        await openCheckout(
          session,
          {
            onSuccess: (response) => verify.mutate(response),
            onDismiss: () => toast.info("Checkout closed. Nothing was charged."),
          },
          { name: user?.full_name, email: user?.email },
        );
      } catch (error) {
        toast.error(errorMessage(error));
      }
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "billing_not_configured") {
        toast.error("Billing is not configured on this deployment yet.");
        return;
      }
      toast.error(errorMessage(error));
    },
    onSettled: () => setCheckoutPlan(null),
  });

  const cancel = useMutation({
    mutationFn: () => api.post<SubscriptionState>("/api/v1/billing/cancel"),
    onSuccess: async (state) => {
      setConfirmCancel(false);
      toast.success(
        state.cancel_at_period_end
          ? `Your plan stays active until ${formatDate(state.current_period_end)}.`
          : "Subscription cancelled.",
      );
      await invalidateBilling();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const state = subscription.data;
  const catalog = plans.data;
  const plansById = new Map((catalog?.plans ?? []).map((plan) => [plan.id, plan]));
  const billingEnabled = state?.billing_enabled ?? catalog?.billing_enabled ?? false;
  const currentPlan = state?.limits;
  const isPaid = state ? state.plan !== "free" : false;

  return (
    <Card id="billing" className="scroll-mt-24">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <CreditCard className="size-4 text-teal-300" />
            Billing &amp; plan
          </CardTitle>
          {state ? (
            <Badge tone={isPaid ? "emerald" : "neutral"}>
              {isPaid ? <Sparkles className="size-3" /> : <ShieldCheck className="size-3" />}
              {state.name} plan
            </Badge>
          ) : null}
        </div>
        <CardDescription>
          Every account starts on Free. Upgrade for unlimited investigations, more device
          scans and report export.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {subscription.isLoading ? (
          <p className="text-xs text-faint">Loading your plan…</p>
        ) : subscription.isError ? (
          <p className="text-xs text-rose-300">{errorMessage(subscription.error)}</p>
        ) : state ? (
          <div className="space-y-4 rounded-xl border border-border bg-surface/60 p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-foreground">
                  {state.name}
                  <span className="ml-2 font-mono text-xs text-faint">
                    {formatInr(state.limits.price_inr)}/mo
                  </span>
                </p>
                <p className="mt-0.5 text-[11px] text-muted">
                  {isPaid
                    ? state.cancel_at_period_end
                      ? `Cancels on ${formatDate(state.current_period_end)}`
                      : `Renews on ${formatDate(state.current_period_end)}`
                    : "No card required. Resets on the 1st of each month."}
                </p>
              </div>
              {isPaid && !state.cancel_at_period_end ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmCancel(true)}
                  loading={cancel.isPending}
                >
                  Cancel plan
                </Button>
              ) : null}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-muted">Investigations</span>
                  <span className="font-mono text-faint">
                    {usageLabel(
                      state.usage.investigations,
                      state.limits.investigations_per_month,
                    )}
                  </span>
                </div>
                <Progress
                  value={
                    state.limits.investigations_per_month === null
                      ? 0
                      : Math.min(
                          100,
                          (state.usage.investigations /
                            state.limits.investigations_per_month) *
                            100,
                        )
                  }
                  indicatorClassName={
                    state.limits.investigations_per_month !== null &&
                    state.usage.investigations >= state.limits.investigations_per_month
                      ? "bg-rose-400"
                      : undefined
                  }
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-muted">Device scans</span>
                  <span className="font-mono text-faint">
                    {usageLabel(state.usage.device_scans, state.limits.device_scans_per_month)}
                  </span>
                </div>
                <Progress
                  value={
                    state.limits.device_scans_per_month === null
                      ? 0
                      : Math.min(
                          100,
                          (state.usage.device_scans / state.limits.device_scans_per_month) *
                            100,
                        )
                  }
                  indicatorClassName={
                    state.limits.device_scans_per_month !== null &&
                    state.usage.device_scans >= state.limits.device_scans_per_month
                      ? "bg-rose-400"
                      : undefined
                  }
                />
              </div>
            </div>
          </div>
        ) : null}

        {!billingEnabled ? (
          <p className="rounded-lg border border-amber-400/25 bg-amber-400/5 px-3 py-2 text-[11px] leading-relaxed text-amber-200">
            Online payments are not configured on this deployment yet. Plans below describe the
            intended pricing; upgrade buttons stay disabled until Razorpay keys and plan IDs are
            set.
          </p>
        ) : null}

        <div className="grid gap-3 lg:grid-cols-3">
          {PLAN_ORDER.map((planId) => {
            const plan = plansById.get(planId);
            if (!plan) return null;

            const isCurrent = currentPlan?.id === plan.id;
            const canBuy = billingEnabled && !isCurrent && plan.id !== "free";
            const isBusy = checkoutPlan === plan.id || (isCurrent && verify.isPending);

            return (
              <div
                key={plan.id}
                className={`flex flex-col rounded-xl border p-4 ${
                  isCurrent
                    ? "border-teal-400/40 bg-teal-400/[0.06]"
                    : "border-border bg-surface/40"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-foreground">{plan.name}</p>
                  {isCurrent ? (
                    <Badge tone="teal">
                      <BadgeCheck className="size-3" />
                      Current
                    </Badge>
                  ) : plan.api_access ? (
                    <Badge tone="violet">Teams</Badge>
                  ) : null}
                </div>
                <p className="mt-1 text-lg font-semibold tracking-tight text-foreground">
                  {plan.price_inr === 0 ? "Free" : `${formatInr(plan.price_inr)}`}
                  {plan.price_inr > 0 ? (
                    <span className="text-xs font-normal text-faint"> /month</span>
                  ) : null}
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-muted">{plan.tagline}</p>

                <ul className="mt-3 space-y-1.5">
                  {planFeatures(plan).map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted"
                    >
                      <Check className="mt-0.5 size-3 shrink-0 text-teal-400" />
                      {feature}
                    </li>
                  ))}
                </ul>

                <div className="mt-auto pt-4">
                  {isCurrent ? (
                    <Button variant="secondary" size="sm" className="w-full" disabled>
                      {verify.isPending ? "Activating…" : "Your plan"}
                    </Button>
                  ) : plan.id === "free" ? (
                    <Button variant="ghost" size="sm" className="w-full" disabled>
                      Included for everyone
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant={plan.id === "pro" ? "primary" : "secondary"}
                      className="w-full"
                      loading={isBusy}
                      disabled={!canBuy}
                      onClick={() => startCheckout.mutate(plan.id)}
                    >
                      {plan.id === "pro" ? (
                        <Sparkles className="size-3.5" />
                      ) : (
                        <InfinityIcon className="size-3.5" />
                      )}
                      {isPaid ? `Switch to ${plan.name}` : `Upgrade to ${plan.name}`}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <p className="text-[11px] leading-relaxed text-faint">
          Payments are processed by Razorpay. Prices are in Indian rupees and include applicable
          taxes where shown at checkout. Cancel any time — access continues until the end of the
          paid period.
        </p>
      </CardContent>

      <Dialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel your subscription?</DialogTitle>
            <DialogDescription>
              You keep {state?.name} features until{" "}
              {formatDate(state?.current_period_end)}. After that the account returns to the Free
              plan and its monthly limits.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirmCancel(false)}>
              Keep plan
            </Button>
            <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel subscription
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
