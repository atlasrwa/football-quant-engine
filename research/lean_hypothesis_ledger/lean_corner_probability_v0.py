#!/usr/bin/env python3
"""Lean corner probability v0.

Offline-only deterministic research helper.
Inputs are externally supplied summary statistics. It does not call providers.

Method:
1. recent_rate = team corners-for summary rate.
2. context_rate = mean(team venue corners-for, opponent venue corners-against).
3. effective context sample = min(n_team_venue, n_opp_venue) to avoid double counting.
4. lambda = sample-size-weighted blend of recent_rate and context_rate.
5. Market probability from Poisson(lambda).

This is an experimental lean baseline, NOT CHAMPION p_model.
"""
import argparse, math

def poisson_over_half(lam: float, line: float) -> float:
    threshold = math.floor(line) + 1
    cdf = sum(math.exp(-lam) * lam**k / math.factorial(k) for k in range(threshold))
    return 1.0 - cdf

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--recent-rate",type=float,required=True)
    p.add_argument("--recent-n",type=int,required=True)
    p.add_argument("--venue-for",type=float,required=True)
    p.add_argument("--venue-for-n",type=int,required=True)
    p.add_argument("--opp-venue-against",type=float,required=True)
    p.add_argument("--opp-venue-against-n",type=int,required=True)
    p.add_argument("--line",type=float,required=True)
    args=p.parse_args()
    context=(args.venue_for+args.opp_venue_against)/2.0
    context_n=min(args.venue_for_n,args.opp_venue_against_n)
    lam=(args.recent_rate*args.recent_n+context*context_n)/(args.recent_n+context_n)
    prob=poisson_over_half(lam,args.line)
    print(f"context_rate={context:.6f}")
    print(f"context_effective_n={context_n}")
    print(f"lambda={lam:.6f}")
    print(f"p_over={prob:.6f}")

if __name__=="__main__":
    main()
