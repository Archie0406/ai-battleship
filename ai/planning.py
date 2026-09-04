"""
ai/planning.py
===============
A real, state-based tactical planner: SEARCH -> TARGET -> DESTROY -> SEARCH.

This is not a cosmetic label. compute_tactical_state() derives the
AI's current tactical state fresh, every call, purely by inspecting the
tracking grid -- there is no stored flag that could drift out of sync
with reality. Whatever agent asks "what state am I in?" gets an answer
computed from the same ground truth the rest of the AI sees.

State definitions
------------------
    SEARCH
        No active (unsunk) HIT cells exist anywhere on the board. The
        AI has no lead to follow, so it should scan broadly for a new
        contact.

    TARGET
        Exactly one active HIT cell exists in the current cluster, and
        its orientation (horizontal/vertical) is not yet known. Because
        Battleship's no-touch rule means two different ships can never
        be adjacent, any second HIT next to this one is guaranteed to
        belong to the SAME ship -- so the moment a second adjacent HIT
        appears, the state below (DESTROY) becomes reachable. Until
        then, the AI should investigate the hit's orthogonal neighbors
        to find that second hit and establish a direction.

    DESTROY
        Two or more active HIT cells in the same cluster are colinear
        (same row or same column). The ship's orientation is now known;
        the AI should keep firing along that line's two open ends until
        the ship is confirmed SUNK.

A "cluster" here means a maximal set of orthogonally-connected active
HIT cells (SUNK cells are excluded -- once a ship is fully sunk it can
no longer be the thing driving TARGET/DESTROY behaviour, which is
exactly how "SHIP DESTROYED -> return to SEARCH" happens: the moment
every HIT cell belonging to that ship flips to SUNK, compute_tactical_state()
naturally finds no active HIT cells left and reports SEARCH again,
with zero special-casing required).
"""

SEARCH = "SEARCH"
TARGET = "TARGET"
DESTROY = "DESTROY"

UNKNOWN = "unknown"
MISS = "miss"
HIT = "hit"
SUNK = "sunk"

ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _in_bounds(r, c, size):
    return 0 <= r < size and 0 <= c < size


def find_active_hit_clusters(tracking, size):
    """
    Every maximal orthogonally-connected group of active (unsunk) HIT
    cells on the board, as a list of cell-lists. SUNK cells never join a
    cluster, so a fully-sunk ship simply produces no cluster at all.
    """
    seen = set()
    clusters = []
    for r in range(size):
        for c in range(size):
            if tracking[r][c] != HIT or (r, c) in seen:
                continue
            # flood-fill this cluster
            stack = [(r, c)]
            cluster = []
            seen.add((r, c))
            while stack:
                cr, cc = stack.pop()
                cluster.append((cr, cc))
                for dr, dc in ORTHOGONAL:
                    nr, nc = cr + dr, cc + dc
                    if _in_bounds(nr, nc, size) and (nr, nc) not in seen and tracking[nr][nc] == HIT:
                        seen.add((nr, nc))
                        stack.append((nr, nc))
            clusters.append(cluster)
    return clusters


def _cluster_orientation(cluster):
    """'horizontal' | 'vertical' | None (single cell, orientation unknown)."""
    if len(cluster) < 2:
        return None
    rows = {r for r, c in cluster}
    cols = {c for r, c in cluster}
    if len(rows) == 1:
        return "horizontal"
    if len(cols) == 1:
        return "vertical"
    return None  # shouldn't happen given the no-touch rule, but stay safe


def compute_tactical_state(tracking, size):
    """
    Returns (state, active_cluster) where state is SEARCH/TARGET/DESTROY
    and active_cluster is the cluster driving that state (None for SEARCH,
    otherwise the largest active-hit cluster -- ties broken by the one
    discovered first, which is deterministic given row-major scanning).
    """
    clusters = find_active_hit_clusters(tracking, size)
    if not clusters:
        return SEARCH, None

    clusters.sort(key=len, reverse=True)
    best = clusters[0]
    if len(best) >= 2 and _cluster_orientation(best) is not None:
        return DESTROY, best
    return TARGET, best


def investigate_targets(cluster, tracking, size):
    """
    TARGET-state candidate cells: the untried orthogonal neighbors of a
    single confirmed hit, in priority order. This is exactly "look at
    nearby cells after a hit" -- no ship orientation is assumed yet.
    """
    (hr, hc) = cluster[0]
    candidates = []
    for dr, dc in ORTHOGONAL:
        nr, nc = hr + dr, hc + dc
        if _in_bounds(nr, nc, size) and tracking[nr][nc] == UNKNOWN:
            candidates.append((nr, nc))
    return candidates


def destroy_targets(cluster, tracking, size):
    """
    DESTROY-state candidate cells: the next untried cell extending the
    established line at each open end, in priority order. Firing here
    is how the AI "continues attacking that ship" once its direction is
    known, per both open ends of the line until one is blocked by a
    MISS/board edge.
    """
    orientation = _cluster_orientation(cluster)
    if orientation is None:
        return []

    rows = [r for r, c in cluster]
    cols = [c for r, c in cluster]
    candidates = []

    if orientation == "horizontal":
        row = rows[0]
        min_c, max_c = min(cols), max(cols)
        if _in_bounds(row, min_c - 1, size) and tracking[row][min_c - 1] == UNKNOWN:
            candidates.append((row, min_c - 1))
        if _in_bounds(row, max_c + 1, size) and tracking[row][max_c + 1] == UNKNOWN:
            candidates.append((row, max_c + 1))
    else:  # vertical
        col = cols[0]
        min_r, max_r = min(rows), max(rows)
        if _in_bounds(min_r - 1, col, size) and tracking[min_r - 1][col] == UNKNOWN:
            candidates.append((min_r - 1, col))
        if _in_bounds(max_r + 1, col, size) and tracking[max_r + 1][col] == UNKNOWN:
            candidates.append((max_r + 1, col))

    return candidates


def plan_candidates(tracking, size):
    """
    The single public entry point: computes the real tactical state from
    the tracking grid, and returns (state, cluster, candidate_cells) --
    candidate_cells is state-appropriate (TARGET -> orthogonal
    neighbours of the lone hit; DESTROY -> the line's open ends; SEARCH
    -> empty, since broad scanning is delegated to a probability/search
    strategy rather than duplicated here).
    """
    state, cluster = compute_tactical_state(tracking, size)
    if state == TARGET:
        return state, cluster, investigate_targets(cluster, tracking, size)
    if state == DESTROY:
        candidates = destroy_targets(cluster, tracking, size)
        if not candidates:
            # Both ends of the line are blocked (e.g. board edge + a
            # miss) -- fall back to investigating every active hit's
            # neighbours so the AI is never left with nothing to try.
            candidates = []
            for cell in cluster:
                candidates.extend(investigate_targets([cell], tracking, size))
            candidates = list(dict.fromkeys(candidates))  # dedupe, keep order
        return state, cluster, candidates
    return state, None, []
