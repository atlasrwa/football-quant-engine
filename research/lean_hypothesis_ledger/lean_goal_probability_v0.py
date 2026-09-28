#!/usr/bin/env python3
"""Lean goal probability v0.

Offline-only deterministic research helper.

This v0 intentionally separates two steps:
1. fixture-specific scoring intensities (lambda_home, lambda_away) are supplied by
   the pre-match evidence/shrinkage layer and frozen in the hypothesis record;
2. this module converts those intensities into coherent Poisson probabilities for
   total goals, BTTS, team-to-score, and 1X2.

It is NOT CHAMPION p_model.
"""
import argparse, math

def pois_pmf(lam, k):
    return math.exp(-lam) * lam**k / math.factorial(k)

def over_half(total_lambda, line):
    threshold = math.floor(line) + 1
    return 1.0 - sum(pois_pmf(total_lambda, k) for k in range(threshold))

def btts_yes(lh, la):
    return 1.0 - math.exp(-lh) - math.exp(-la) + math.exp(-(lh+la))

def one_x_two(lh, la, max_goals=15):
    hp=[pois_pmf(lh,k) for k in range(max_goals+1)]
    ap=[pois_pmf(la,k) for k in range(max_goals+1)]
    home=draw=away=0.0
    for i,pi in enumerate(hp):
        for j,pj in enumerate(ap):
            p=pi*pj
            if i>j: home += p
            elif i==j: draw += p
            else: away += p
    z=home+draw+away
    return home/z, draw/z, away/z

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--lambda-home",type=float,required=True)
    p.add_argument("--lambda-away",type=float,required=True)
    p.add_argument("--line",type=float,default=2.5)
    args=p.parse_args()
    total=args.lambda_home+args.lambda_away
    h,d,a=one_x_two(args.lambda_home,args.lambda_away)
    print(f"lambda_total={total:.6f}")
    print(f"p_over_{args.line:.1f}={over_half(total,args.line):.6f}")
    print(f"p_btts_yes={btts_yes(args.lambda_home,args.lambda_away):.6f}")
    print(f"p_home_win={h:.6f}")
    print(f"p_draw={d:.6f}")
    print(f"p_away_win={a:.6f}")

if __name__=="__main__":
    main()
