"""Vectorized discrete-time Markov chain simulator (guide 6.2).

Petri net: NOT in the PoC. approach1.md section 5.3.2 calls for a
generalized stochastic Petri net (GSPN) once Alice and Bob share resources
(a human review queue contending for latency and cost). With a single agent
and no shared resource, that GSPN collapses exactly to this Markov chain --
there is nothing for a Petri net to add in the single-agent PoC; it earns
its place only once phase 9's two-agent setting introduces a shared queue.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from change.contracts import BehavioralSnapshot, CanonicalAction

ALL_ACTIONS = [a.value for a in CanonicalAction]


@dataclass
class SimOutput:
    violation: np.ndarray  # shape (n_traj, horizon), 1.0/0.0
    success: np.ndarray  # shape (n_traj, horizon), 1.0/0.0
    cost: np.ndarray  # shape (n_traj, horizon)


def _categorical_sample(probs: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """probs: (n, k), rows sum to ~1. Returns (n,) sampled column indices."""
    cumsum = np.cumsum(probs, axis=1)
    u = rng.random(probs.shape[0])[:, None]
    idx = (cumsum < u).sum(axis=1)
    return np.clip(idx, 0, probs.shape[1] - 1)


class _SnapshotArrays:
    """Lookup arrays precomputed once from a BehavioralSnapshot (fixed for
    the whole simulation; only the twin model's p_action varies over t)."""

    def __init__(self, snapshot: BehavioralSnapshot):
        states = sorted(snapshot.p_action.keys())
        self.states = states
        self.state_idx = {s: i for i, s in enumerate(states)}
        k = len(states)
        n_actions = len(ALL_ACTIONS)
        if k == 0:
            raise ValueError("snapshot has no covered states to simulate from")

        p_initial = np.array([snapshot.p_initial.get(s, 0.0) for s in states])
        self.p_initial = p_initial / p_initial.sum() if p_initial.sum() > 0 else np.full(k, 1.0 / k)

        global_compliant = 1.0 - snapshot.violation_rate
        global_success = snapshot.success_rate
        p_compliant = np.full((k, n_actions), global_compliant)
        p_success = np.full((k, n_actions), global_success)

        for state, actions in snapshot.p_outcome.items():
            si = self.state_idx[state]
            counts = snapshot.n_action.get(state, {})
            total = sum(counts.values())
            if total > 0:
                marg_compliant = (
                    sum(actions[a]["compliant"] * counts.get(a, 0) for a in actions) / total
                )
                marg_success = (
                    sum(actions[a]["success"] * counts.get(a, 0) for a in actions) / total
                )
            else:
                marg_compliant, marg_success = global_compliant, global_success
            p_compliant[si, :] = marg_compliant
            p_success[si, :] = marg_success
            for action, cell in actions.items():
                ai = ALL_ACTIONS.index(action)
                p_compliant[si, ai] = cell["compliant"]
                p_success[si, ai] = cell["success"]

        self.p_compliant = p_compliant
        self.p_success = p_success
        self.mean_cost = snapshot.mean_cost

        # (state_idx, action_idx) -> (target_idx array, prob array); absent
        # means the action is terminal for that state -> resample S0.
        self.transitions: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
        for state, actions in snapshot.p_transition.items():
            si = self.state_idx.get(state)
            if si is None:
                continue
            for action, targets in actions.items():
                ai = ALL_ACTIONS.index(action)
                target_idx, probs = [], []
                for target_state, p in targets.items():
                    ti = self.state_idx.get(target_state)
                    if ti is None:
                        continue
                    target_idx.append(ti)
                    probs.append(p)
                if not target_idx:
                    continue
                probs_arr = np.array(probs)
                probs_arr = probs_arr / probs_arr.sum()
                self.transitions[(si, ai)] = (np.array(target_idx), probs_arr)


def simulate(
    model,
    snapshot: BehavioralSnapshot,
    n_traj: int,
    horizon: int,
    rng: np.random.Generator,
    patches: dict[str, dict[str, float]] | None = None,
) -> SimOutput:
    arrays = _SnapshotArrays(snapshot)
    k = len(arrays.states)
    n_actions = len(ALL_ACTIONS)
    t_start = snapshot.window_end_t

    current_state = _categorical_sample(np.tile(arrays.p_initial, (n_traj, 1)), rng)

    violation = np.zeros((n_traj, horizon))
    success = np.zeros((n_traj, horizon))
    cost = np.zeros((n_traj, horizon))

    for t in range(horizon):
        p_action_dict = model.predict_sample(t_start + t, rng)
        if patches:
            p_action_dict = {**p_action_dict, **patches}

        p_action_matrix = np.full((k, n_actions), 1.0 / n_actions)
        for si, state in enumerate(arrays.states):
            dist = p_action_dict.get(state)
            if dist is not None:
                p_action_matrix[si, :] = [dist.get(a, 0.0) for a in ALL_ACTIONS]

        action_idx = _categorical_sample(p_action_matrix[current_state], rng)

        p_compliant = arrays.p_compliant[current_state, action_idx]
        p_success = arrays.p_success[current_state, action_idx]
        compliant_draw = rng.random(n_traj) < p_compliant
        success_draw = rng.random(n_traj) < p_success

        violation[:, t] = (~compliant_draw).astype(float)
        success[:, t] = success_draw.astype(float)
        cost[:, t] = arrays.mean_cost

        next_state = np.full(n_traj, -1, dtype=int)
        pairs = np.stack([current_state, action_idx], axis=1)
        for si, ai in np.unique(pairs, axis=0):
            mask = (current_state == si) & (action_idx == ai)
            transition = arrays.transitions.get((int(si), int(ai)))
            if transition is None:
                continue  # terminal: resampled below
            target_idx, probs = transition
            n_in_cell = int(mask.sum())
            sampled = _categorical_sample(np.tile(probs, (n_in_cell, 1)), rng)
            next_state[mask] = target_idx[sampled]

        terminal_mask = next_state < 0
        n_terminal = int(terminal_mask.sum())
        if n_terminal > 0:
            next_state[terminal_mask] = _categorical_sample(
                np.tile(arrays.p_initial, (n_terminal, 1)), rng
            )
        current_state = next_state

    return SimOutput(violation=violation, success=success, cost=cost)
