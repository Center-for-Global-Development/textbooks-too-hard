"""Comparative judgement: put passages on one difficulty scale from paired judgements.

A judge (TypeSafe's Jev) says, for a pair of passages, the probability that the first is the
harder for a beginning reader. A Bradley-Terry model, P(i harder than j) = 1 / (1 + exp(theta_j
- theta_i)), is fitted to those soft judgements by Newton's method with a small ridge (so a
passage that wins every comparison stays finite), and the scale is centred on zero. Test
passages and book passages are judged against each other, so a book passage's theta can be read
against its country's test story. Lee, 2026-11-01 (the comparative judgement pilot).
"""
from __future__ import annotations

import random

import numpy as np

RIDGE = 0.05      # prior precision on each theta (a N(0, 20) prior: weak)


def fit(n: int, judged: list[tuple[int, int, float]], ridge: float = RIDGE) -> list[float]:
    """theta for items 0..n-1 from (i, j, p) with p = P(i is harder than j)."""
    i = np.array([a for a, _, _ in judged], dtype=int)
    j = np.array([b for _, b, _ in judged], dtype=int)
    p = np.array([c for _, _, c in judged], dtype=float)
    theta = np.zeros(n)
    for _ in range(100):
        q = 1 / (1 + np.exp(-(theta[i] - theta[j])))
        r = p - q                                    # gradient of the log likelihood
        g = np.bincount(i, r, n) - np.bincount(j, r, n) - ridge * theta
        w = q * (1 - q)
        h = np.diag(np.bincount(i, w, n) + np.bincount(j, w, n) + ridge)
        np.add.at(h, (i, j), -w)
        np.add.at(h, (j, i), -w)
        step = np.linalg.solve(h, g)
        theta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    theta -= theta.mean()
    return theta.tolist()


def design(ids: list, is_test: dict, per: int = 10, min_tests: int = 3,
           rng: random.Random | None = None) -> list[tuple]:
    """Pairs to judge: each non-test passage against `min_tests` test passages, then random
    partners until each passage has about `per` comparisons. No pair twice."""
    rng = rng or random.Random(0)
    tests = [x for x in ids if is_test[x]]
    seen, pairs = set(), []
    degree = {x: 0 for x in ids}

    def add(a, b):
        k = frozenset((a, b))
        if a == b or k in seen:
            return False
        seen.add(k)
        pairs.append((a, b) if rng.random() < 0.5 else (b, a))
        degree[a] += 1
        degree[b] += 1
        return True

    for x in ids:
        if not is_test[x]:
            for t in rng.sample(tests, min(min_tests, len(tests))):
                add(x, t)
    order = list(ids)
    for _ in range(per * 4):
        rng.shuffle(order)
        need = [x for x in order if degree[x] < per]
        if len(need) < 2:
            break
        for a in need:
            if degree[a] >= per:
                continue
            for b in rng.sample(ids, min(len(ids), 20)):
                if degree[b] < per + 2 and add(a, b):
                    break
    return pairs


def spearman(x, y) -> float:
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx, ry)[0, 1])
